# PowerShell скрипт для клонирования каталога Предметы в УТО_Тест в 1C конфигурации
# Версия 1C: 8.3.25, XML dump v2.18

param (
    [string]$ConfigPath = $PSScriptRoot
)

# Функция для генерации нового UUID
function New-UUID {
    return [guid]::NewGuid().ToString()
}

# Пути к файлам
$PredmetyXml = Join-Path $ConfigPath "Catalogs\Предметы.xml"
$UtoTestXml = Join-Path $ConfigPath "Catalogs\УТО_Тест.xml"
$ConfigurationXml = Join-Path $ConfigPath "Configuration.xml"
$ConfigDumpInfoXml = Join-Path $ConfigPath "ConfigDumpInfo.xml"

# Шаг 1: Загрузить и клонировать Предметы.xml
if (-not (Test-Path $PredmetyXml)) {
    Write-Error "Файл $PredmetyXml не найден."
    exit 1
}

[xml]$xml = Get-Content $PredmetyXml -Encoding UTF8

# Заменить имя в Properties
$xml.Catalog.Properties.Name = "УТО_Тест"
$xml.Catalog.Properties.Synonym.'v8:item'.'v8:content' = "УТО_Тест"

# Заменить в InternalInfo: имена типов
foreach ($genType in $xml.Catalog.InternalInfo.'xr:GeneratedType') {
    $genType.name = $genType.name -replace "Предметы", "УТО_Тест"
}

# Сгенерировать новые UUID для всех xr:TypeId и xr:ValueId
foreach ($genType in $xml.Catalog.InternalInfo.'xr:GeneratedType') {
    $genType.'xr:TypeId' = New-UUID
    $genType.'xr:ValueId' = New-UUID
}

# Новый UUID для корневого Catalog
$xml.Catalog.uuid = New-UUID

# Сохранить новый файл
$xml.Save($UtoTestXml)
Write-Host "Создан файл $UtoTestXml"

# Шаг 2: Обновить Configuration.xml
[xml]$configXml = Get-Content $ConfigurationXml -Encoding UTF8

# Найти ChildObjects
$childObjects = $configXml.Configuration.ChildObjects

# Удалить существующий УТО_Тест, если есть
$existing = $childObjects.Catalog | Where-Object { $_ -eq "УТО_Тест" }
if ($existing) {
    $childObjects.RemoveChild($existing)
}

# Вставить после последнего Catalog (Предметы)
$catalogs = $childObjects.Catalog
$lastCatalog = $catalogs | Select-Object -Last 1
$newCatalog = $configXml.CreateElement("Catalog")
$newCatalog.InnerText = "УТО_Тест"
$childObjects.InsertAfter($newCatalog, $lastCatalog)

$configXml.Save($ConfigurationXml)
Write-Host "Обновлен $ConfigurationXml"

# Шаг 3: Обновить ConfigDumpInfo.xml
[xml]$dumpXml = Get-Content $ConfigDumpInfoXml -Encoding UTF8

$configVersions = $dumpXml.ConfigDumpInfo.ConfigVersions

# Удалить существующий УТО_Тест, если есть
$existingMeta = $configVersions.Metadata | Where-Object { $_.name -eq "Catalog.УТО_Тест" }
if ($existingMeta) {
    $configVersions.RemoveChild($existingMeta)
}

# Найти последний Catalog
$catalogMetas = $configVersions.Metadata | Where-Object { $_.name -like "Catalog.*" }
$lastCatalogMeta = $catalogMetas | Select-Object -Last 1

# Создать новый Metadata для УТО_Тест
$newMeta = $dumpXml.CreateElement("Metadata")
$newMeta.SetAttribute("name", "Catalog.УТО_Тест")
$newMeta.SetAttribute("id", $xml.Catalog.uuid)
$newMeta.SetAttribute("configVersion", "0000000000000000000000000000000000000000")  # Пустой configVersion для нового

# Добавить атрибуты, если есть в оригинале
$originalMeta = $configVersions.Metadata | Where-Object { $_.name -eq "Catalog.Предметы" }
foreach ($child in $originalMeta.ChildNodes) {
    $newChild = $dumpXml.CreateElement("Metadata")
    $newChild.SetAttribute("name", $child.name -replace "Предметы", "УТО_Тест")
    $newChild.SetAttribute("id", New-UUID)
    $newMeta.AppendChild($newChild)
}

$configVersions.InsertAfter($newMeta, $lastCatalogMeta)

$dumpXml.Save($ConfigDumpInfoXml)
Write-Host "Обновлен $ConfigDumpInfoXml"

Write-Host "Клонирование завершено успешно."