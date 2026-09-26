$ErrorActionPreference = 'Stop'
$panelSource = $PSScriptRoot
$framework = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319'
$compiler = Join-Path $framework 'csc.exe'
if (!(Test-Path -LiteralPath $compiler)) { throw '.NET Framework compiler not found.' }
$output = Join-Path $panelSource 'bin'
New-Item -ItemType Directory -Path $output -Force | Out-Null
$references = @('System.dll','System.Core.dll','System.Drawing.dll','System.Windows.Forms.dll','System.Web.Extensions.dll','System.Xaml.dll','WPF\WindowsBase.dll','WPF\PresentationCore.dll','WPF\PresentationFramework.dll')
$arguments = @('/nologo','/target:winexe','/platform:x64','/optimize+',('/out:' + (Join-Path $output 'FridayPanel.exe')),('/win32icon:' + (Join-Path (Split-Path $panelSource) 'friday_icon.ico')),('/resource:' + (Join-Path $panelSource 'MainWindow.xaml') + ',MainWindow.xaml'))
foreach ($reference in $references) { $arguments += '/reference:' + (Join-Path $framework $reference) }
$arguments += Join-Path $panelSource 'App.cs'
$arguments += Join-Path $panelSource 'Appearance.cs'
$arguments += Join-Path $panelSource 'NativePages.cs'
& $compiler @arguments
if ($LASTEXITCODE -ne 0) { throw 'C# build failed.' }
Get-Item -LiteralPath (Join-Path $output 'FridayPanel.exe') | Select-Object FullName, Length
