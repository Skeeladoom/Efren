param(
    [string]$InstallDir = "$env:LOCALAPPDATA\EFREN-Lite",
    [string]$PackagePath = "",
    [switch]$CreateShortcut
)

$ErrorActionPreference = 'Stop'
$package = if ($PackagePath) { $PackagePath } else { Join-Path $PSScriptRoot 'EFREN-Lite.zip' }
if (-not (Test-Path -LiteralPath $package)) {
    throw "EFREN-Lite.zip was not found next to the installer."
}
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
# The portable archive is produced by Windows tar and can contain files that
# Expand-Archive rejects.  tar.exe is built into supported Windows versions.
& tar.exe -xf $package -C $InstallDir
if ($LASTEXITCODE -ne 0) { throw "Failed to extract EFREN-Lite.zip (exit code $LASTEXITCODE)." }

$target = Join-Path $InstallDir 'panel-wpf\bin\FridayPanel.exe'
if (-not (Test-Path -LiteralPath $target)) {
    throw "The panel executable was not found after extraction: $target"
}
if ($CreateShortcut) {
    $shell = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath('Desktop')
    $shortcut = $shell.CreateShortcut((Join-Path $desktop 'EFREN Lite.lnk'))
    $shortcut.TargetPath = $target
    $shortcut.WorkingDirectory = Split-Path $target
    $shortcut.Description = 'EFREN Lite control panel'
    $shortcut.Save()
}
Start-Process -FilePath $target -WorkingDirectory (Split-Path $target)
Write-Host "EFREN Lite was installed to $InstallDir"
