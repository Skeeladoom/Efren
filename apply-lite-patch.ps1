param(
    [Parameter(Mandatory=$true)][string]$Package,
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [Parameter(Mandatory=$true)][int]$WaitPid,
    [switch]$NoRestart
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
$archive = [IO.Path]::GetFullPath($Package)
if (!(Test-Path -LiteralPath $archive -PathType Leaf) -or !(Test-Path -LiteralPath $root -PathType Container)) { throw 'Package or EFREN directory not found.' }
try { Wait-Process -Id $WaitPid -Timeout 30 -ErrorAction SilentlyContinue } catch {}
$work = Join-Path $root ('updates\patch-' + [Guid]::NewGuid().ToString('N'))
$stage = Join-Path $work 'stage'
$rollback = Join-Path $work 'rollback'
New-Item -ItemType Directory -Path $stage,$rollback -Force | Out-Null
try {
    Expand-Archive -LiteralPath $archive -DestinationPath $stage -Force
    $manifestPath = Join-Path $stage 'patch-manifest.json'
    if (!(Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'patch-manifest.json is missing.' }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.format -ne 'EFREN-LITE-PATCH-1') { throw 'Unknown update package format.' }
    $protectedFiles = @('config.json','assistant_names.json','jarvis_settings.json','panel_theme.json','macro_phrases.json','macro_disabled.json','lite-auth.json')
    foreach ($item in $manifest.files) {
        $relative = ([string]$item.path).Replace('/', '\')
        if ($protectedFiles -contains $relative -or $relative -match '^(logs|backups|updates|rvc_models\\store|scenarios|\u0441\u0446\u0435\u043d\u0430\u0440\u0438\u0438)\\') { throw ('Package attempts to modify personal data: ' + $relative) }
        $source = [IO.Path]::GetFullPath((Join-Path $stage $relative))
        $target = [IO.Path]::GetFullPath((Join-Path $root $relative))
        if (!$source.StartsWith($stage + '\', [StringComparison]::OrdinalIgnoreCase) -or !$target.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe package path.' }
        $actual = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne ([string]$item.sha256).ToLowerInvariant()) { throw ('Damaged file: ' + $relative) }
        if (Test-Path -LiteralPath $target -PathType Leaf) {
            $old = Join-Path $rollback $relative
            New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($old)) -Force | Out-Null
            Copy-Item -LiteralPath $target -Destination $old -Force
        }
    }
    foreach ($item in $manifest.files) {
        $relative = ([string]$item.path).Replace('/', '\')
        $source = Join-Path $stage $relative
        $target = Join-Path $root $relative
        New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($target)) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $target -Force
    }
    if (!$NoRestart) { Start-Process -FilePath (Join-Path $root 'panel-wpf\bin\FridayPanel.exe') -WorkingDirectory $root }
} catch {
    Get-ChildItem -LiteralPath $rollback -File -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
        $relative = $_.FullName.Substring($rollback.Length + 1)
        $target = Join-Path $root $relative
        New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($target)) -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    }
    $message = $_.Exception.Message
    Set-Content -LiteralPath (Join-Path $root 'updates\last-patch-error.txt') -Value $message -Encoding UTF8
    throw
}
