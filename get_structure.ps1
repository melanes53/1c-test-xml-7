$Root = (Get-Location).ProviderPath

function Get-RelPath([string]$FullName) {
    if ($FullName.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $FullName.Substring($Root.Length).TrimStart('\')
    }
    return $FullName
}

# 1) dirs.txt — только папки (относительные пути)
$dirs = Get-ChildItem -LiteralPath $Root -Directory -Recurse -Force |
    ForEach-Object { Get-RelPath $_.FullName } |
    Sort-Object

Set-Content -LiteralPath (Join-Path $Root 'dirs.txt') -Value $dirs -Encoding utf8

# 2) files.txt — файлы (относительный путь + размер), без самих отчётов
$files = Get-ChildItem -LiteralPath $Root -File -Recurse -Force |
    Where-Object { $_.Name -notin @('dirs.txt','files.txt') } |
    ForEach-Object {
        [PSCustomObject]@{
            Path   = Get-RelPath $_.FullName
            Length = $_.Length
        }
    } | Sort-Object Path

$lines = @("Path`tLength") + ($files | ForEach-Object { "$($_.Path)`t$($_.Length)" })
Set-Content -LiteralPath (Join-Path $Root 'files.txt') -Value $lines -Encoding utf8
