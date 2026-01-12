#Requires -Version 5.1

<#
.SYNOPSIS
    Клонирует справочник 1C "Предметы" в "УТО_Тест" с полной целостностью метаданных
.DESCRIPTION
    Выполняет хирургическое внедрение XML согласно правилам структуры метаданных 8.3.25
.PARAMETER ConfigPath
    Путь к каталогу Configuration (по умолчанию .\Configuration)
.EXAMPLE
    .\Clone-1CCatalog.ps1 -ConfigPath "C:\Projects\MyConfig\Configuration"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$ConfigPath = ".\Configuration"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================

function New-RandomGuid {
    [guid]::NewGuid().ToString()
}

function Write-Step {
    param([string]$Message)
    Write-Host "`n[*] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[+] $Message" -ForegroundColor Green
}

function Write-ErrorMsg {
    param([string]$Message)
    Write-Host "[!] $Message" -ForegroundColor Red
}

# ============================================================================
# ФУНКЦИИ РАБОТЫ С XML
# ============================================================================

function Get-XmlContent {
    param([string]$Path)
    
    if (-not (Test-Path $Path)) {
        throw "Файл не найден: $Path"
    }
    
    [xml](Get-Content -Path $Path -Encoding UTF8 -Raw)
}

function Save-XmlContent {
    param(
        [xml]$XmlDoc,
        [string]$Path
    )
    
    $settings = New-Object System.Xml.XmlWriterSettings
    $settings.Encoding = [System.Text.Encoding]::UTF8
    $settings.Indent = $true
    $settings.IndentChars = "`t"
    $settings.NewLineChars = "`r`n"
    $settings.OmitXmlDeclaration = $false
    
    $writer = [System.Xml.XmlWriter]::Create($Path, $settings)
    try {
        $XmlDoc.Save($writer)
    }
    finally {
        $writer.Close()
    }
}

function Clone-CatalogMetadata {
    param(
        [string]$SourcePath,
        [string]$TargetPath,
        [string]$SourceName,
        [string]$TargetName
    )
    
    Write-Step "Загрузка донорского справочника: $SourceName"
    $content = Get-Content -Path $SourcePath -Encoding UTF8 -Raw
    
    Write-Step "Выполнение генетической замены: $SourceName -> $TargetName"
    # Замена внутренних ссылок (точечная нотация)
    $content = $content -replace "\.$SourceName", ".$TargetName"
    # Замена содержимого тегов
    $content = $content -replace ">$SourceName<", ">$TargetName<"
    
    Write-Step "Регенерация UUID генома"
    [xml]$xmlDoc = $content
    
    # Создаём namespace manager для работы с XML
    $nsmgr = New-Object System.Xml.XmlNamespaceManager($xmlDoc.NameTable)
    $nsmgr.AddNamespace("xr", "http://v8.1c.ru/8.3/xcf/readable")
    $nsmgr.AddNamespace("cfg", "http://v8.1c.ru/8.1/data/enterprise/current-config")
    
    # Назначаем новый корневой UUID
    $catalogNode = $xmlDoc.SelectSingleNode("//cfg:Catalog", $nsmgr)
    if ($catalogNode) {
        $newRootUuid = New-RandomGuid
        $catalogNode.SetAttribute("uuid", $newRootUuid)
        Write-Success "Корневой UUID: $newRootUuid"
    }
    
    # Регенерация всех TypeId и ValueId UUID в InternalInfo
    # КРИТИЧНО для 8.3.25: используем sub-nodes <xr:TypeId> и <xr:ValueId>, НЕ атрибут uuid
    $generatedTypes = $xmlDoc.SelectNodes("//xr:GeneratedType", $nsmgr)
    $regeneratedCount = 0
    
    foreach ($genType in $generatedTypes) {
        $typeIdNode = $genType.SelectSingleNode("xr:TypeId", $nsmgr)
        $valueIdNode = $genType.SelectSingleNode("xr:ValueId", $nsmgr)
        
        if ($typeIdNode) {
            $typeIdNode.InnerText = New-RandomGuid
            $regeneratedCount++
        }
        if ($valueIdNode) {
            $valueIdNode.InnerText = New-RandomGuid
            $regeneratedCount++
        }
    }
    
    Write-Success "Регенерировано UUID: $regeneratedCount узлов"
    Save-XmlContent -XmlDoc $xmlDoc -Path $TargetPath
}

function Remove-ExistingMetadata {
    param(
        [string]$ConfigPath,
        [string]$CatalogName
    )
    
    Write-Step "Удаление существующих следов $CatalogName (идемпотентность)"
    
    # Удаление каталога справочника
    $catalogDir = Join-Path $ConfigPath "Catalogs\$CatalogName"
    if (Test-Path $catalogDir) {
        Remove-Item -Path $catalogDir -Recurse -Force
        Write-Success "Удалён каталог: $catalogDir"
    }
    
    # Удаление XML файла справочника
    $catalogFile = Join-Path $ConfigPath "Catalogs\$CatalogName.xml"
    if (Test-Path $catalogFile) {
        Remove-Item -Path $catalogFile -Force
        Write-Success "Удалён файл: $catalogFile"
    }
}

function Inject-IntoConfiguration {
    param(
        [string]$ConfigurationXmlPath,
        [string]$CatalogName
    )
    
    Write-Step "Внедрение в Configuration.xml (топологический порядок)"
    
    [xml]$configXml = Get-XmlContent -Path $ConfigurationXmlPath
    
    $nsmgr = New-Object System.Xml.XmlNamespaceManager($configXml.NameTable)
    $nsmgr.AddNamespace("cfg", "http://v8.1c.ru/8.1/data/enterprise/current-config")
    
    # Находим узел ChildObjects
    $childObjects = $configXml.SelectSingleNode("//cfg:Configuration/cfg:ChildObjects", $nsmgr)
    if (-not $childObjects) {
        throw "Узел ChildObjects не найден в Configuration.xml"
    }
    
    # Удаляем существующую ссылку на справочник, если есть
    $existingCatalog = $childObjects.SelectSingleNode("cfg:Catalog[text()='$CatalogName']", $nsmgr)
    if ($existingCatalog) {
        [void]$childObjects.RemoveChild($existingCatalog)
        Write-Success "Удалена существующая ссылка"
    }
    
    # Находим последний узел Catalog для вставки после него
    $catalogNodes = $childObjects.SelectNodes("cfg:Catalog", $nsmgr)
    $lastCatalog = $catalogNodes | Select-Object -Last 1
    
    # Создаём новый узел справочника
    $newCatalog = $configXml.CreateElement("Catalog", $nsmgr.LookupNamespace("cfg"))
    $newCatalog.InnerText = $CatalogName
    
    if ($lastCatalog) {
        [void]$childObjects.InsertAfter($newCatalog, $lastCatalog)
        Write-Success "Вставлено после последнего Catalog"
    } else {
        # Справочников нет, вставляем перед Documents
        $firstDocument = $childObjects.SelectSingleNode("cfg:Document", $nsmgr)
        if ($firstDocument) {
            [void]$childObjects.InsertBefore($newCatalog, $firstDocument)
        } else {
            [void]$childObjects.AppendChild($newCatalog)
        }
        Write-Success "Вставлено как первый Catalog"
    }
    
    Save-XmlContent -XmlDoc $configXml -Path $ConfigurationXmlPath
}

function Inject-IntoConfigDumpInfo {
    param(
        [string]$ConfigDumpInfoPath,
        [string]$CatalogName
    )
    
    Write-Step "Внедрение в ConfigDumpInfo.xml"
    
    [xml]$dumpInfoXml = Get-XmlContent -Path $ConfigDumpInfoPath
    
    $nsmgr = New-Object System.Xml.XmlNamespaceManager($dumpInfoXml.NameTable)
    $nsmgr.AddNamespace("xr", "http://v8.1c.ru/8.3/xcf/readable")
    
    # Находим корневой узел ConfigDumpInfo
    $configDumpInfo = $dumpInfoXml.SelectSingleNode("//xr:ConfigDumpInfo", $nsmgr)
    if (-not $configDumpInfo) {
        throw "Узел ConfigDumpInfo не найден"
    }
    
    # Удаляем существующую запись метаданных, если есть
    $existingMetadata = $configDumpInfo.SelectSingleNode("xr:Metadata[@name='Catalog.$CatalogName']", $nsmgr)
    if ($existingMetadata) {
        [void]$configDumpInfo.RemoveChild($existingMetadata)
        Write-Success "Удалена существующая запись метаданных"
    }
    
    # Находим последнюю запись метаданных Catalog.*
    $catalogMetadataNodes = $configDumpInfo.SelectNodes("xr:Metadata[starts-with(@name, 'Catalog.')]", $nsmgr)
    $lastCatalogMetadata = $catalogMetadataNodes | Select-Object -Last 1
    
    # Создаём новый узел метаданных
    $newMetadata = $dumpInfoXml.CreateElement("Metadata", $nsmgr.LookupNamespace("xr"))
    $newMetadata.SetAttribute("name", "Catalog.$CatalogName")
    $newMetadata.SetAttribute("id", (New-RandomGuid))
    $newMetadata.SetAttribute("configVersion", ([guid]::Empty.ToString()))
    
    if ($lastCatalogMetadata) {
        [void]$configDumpInfo.InsertAfter($newMetadata, $lastCatalogMetadata)
        Write-Success "Вставлено после последней записи Catalog.*"
    } else {
        [void]$configDumpInfo.AppendChild($newMetadata)
        Write-Success "Вставлено как первая запись Catalog.*"
    }
    
    Save-XmlContent -XmlDoc $dumpInfoXml -Path $ConfigDumpInfoPath
}

# ============================================================================
# ОСНОВНОЕ ВЫПОЛНЕНИЕ
# ============================================================================

try {
    Write-Host "`n╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Yellow
    Write-Host "║  ХИРУРГИЧЕСКОЕ КЛОНИРОВАНИЕ МЕТАДАННЫХ 1C - БОЕВОЙ РЕЖИМ      ║" -ForegroundColor Yellow
    Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Yellow
    
    # Проверка пути конфигурации
    if (-not (Test-Path $ConfigPath)) {
        throw "Путь конфигурации не найден: $ConfigPath"
    }
    
    # Определение путей
    $sourceCatalog = "Предметы"
    $targetCatalog = "УТО_Тест"
    
    $sourceCatalogPath = Join-Path $ConfigPath "Catalogs\$sourceCatalog.xml"
    $targetCatalogPath = Join-Path $ConfigPath "Catalogs\$targetCatalog.xml"
    $configurationXmlPath = Join-Path $ConfigPath "Configuration.xml"
    $configDumpInfoPath = Join-Path $ConfigPath "ConfigDumpInfo.xml"
    
    # Проверка существования исходных файлов
    if (-not (Test-Path $sourceCatalogPath)) {
        throw "Исходный справочник не найден: $sourceCatalogPath"
    }
    if (-not (Test-Path $configurationXmlPath)) {
        throw "Configuration.xml не найден: $configurationXmlPath"
    }
    if (-not (Test-Path $configDumpInfoPath)) {
        throw "ConfigDumpInfo.xml не найден: $configDumpInfoPath"
    }
    
    # Фаза 1: Удаление существующих метаданных (идемпотентность)
    Remove-ExistingMetadata -ConfigPath $ConfigPath -CatalogName $targetCatalog
    
    # Фаза 2: Клонирование метаданных справочника
    Clone-CatalogMetadata `
        -SourcePath $sourceCatalogPath `
        -TargetPath $targetCatalogPath `
        -SourceName $sourceCatalog `
        -TargetName $targetCatalog
    
    # Фаза 3: Внедрение в Configuration.xml
    Inject-IntoConfiguration `
        -ConfigurationXmlPath $configurationXmlPath `
        -CatalogName $targetCatalog
    
    # Фаза 4: Внедрение в ConfigDumpInfo.xml
    Inject-IntoConfigDumpInfo `
        -ConfigDumpInfoPath $configDumpInfoPath `
        -CatalogName $targetCatalog
    
    Write-Host "`n╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║  ХИРУРГИЧЕСКОЕ ВНЕДРЕНИЕ ЗАВЕРШЕНО - ГОТОВО К ЗАГРУЗКЕ        ║" -ForegroundColor Green
    Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Green
    
    Write-Host "`nСледующие шаги:" -ForegroundColor Yellow
    Write-Host "1. Выполните: 1cv8.exe CREATEINFOBASE File=`"<путь>`"" -ForegroundColor Gray
    Write-Host "2. Выполните: 1cv8.exe DESIGNER /F <путь> /LoadConfigFromFiles `"$ConfigPath`" /UpdateDBCfg" -ForegroundColor Gray
    
} catch {
    Write-ErrorMsg "КРИТИЧЕСКАЯ ОШИБКА: $($_.Exception.Message)"
    Write-Host $_.ScriptStackTrace -ForegroundColor Red
    exit 1
}