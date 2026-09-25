param(
    [string]$InstallDir = "$env:LOCALAPPDATA\EFREN-Lite"
)

$ErrorActionPreference = 'Stop'
$package = Join-Path $PSScriptRoot 'EFREN-Lite.zip'
if (-not (Test-Path -LiteralPath $package)) {
    throw "Не найден EFREN-Lite.zip рядом с установщиком."
}
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Expand-Archive -LiteralPath $package -DestinationPath $InstallDir -Force

$target = Join-Path $InstallDir 'panel-wpf\bin\FridayPanel.exe'
if (-not (Test-Path -LiteralPath $target)) {
    throw "В архиве не найден файл панели: $target"
}
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcut = $shell.CreateShortcut((Join-Path $desktop 'EFREN Lite.lnk'))
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = Split-Path $target
$shortcut.Description = 'Панель управления EFREN Lite'
$shortcut.Save()
Start-Process -FilePath $target -WorkingDirectory (Split-Path $target)
Write-Host "EFREN Lite установлен в $InstallDir"
