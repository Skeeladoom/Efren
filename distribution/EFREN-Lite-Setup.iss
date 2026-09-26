#define MyAppName "EFREN Lite"
#define MyAppVersion "0.1.6"
#define MyAppPublisher "Skeeladoom"

[Setup]
AppId=EFREN-Lite
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
UninstallDisplayIcon={app}\panel-wpf\bin\FridayPanel.exe
DefaultDirName={localappdata}\EFREN-Lite
DefaultGroupName={#MyAppName}
OutputDir=.
OutputBaseFilename=EFREN-Lite-Setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
DisableWelcomePage=no
DisableDirPage=no
WizardStyle=modern

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Files]
; Personal state survives both reinstall and automatic update.
Source: "release-lite-clean\*"; DestDir: "{app}"; Excludes: "models\whisper-base\*,rvc_models\store\*,config.json,assistant_names.json,jarvis_settings.json,panel_theme.json,macro_phrases.json,macro_disabled.json,lite-auth.json,logs\*,scenarios\*,сценарии\*"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "release-lite-clean\config.json"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "release-lite-clean\assistant_names.json"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "release-lite-clean\jarvis_settings.json"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "release-lite-clean\panel_theme.json"; DestDir: "{app}"; Flags: onlyifdoesntexist skipifsourcedoesntexist
Source: "release-lite-clean\macro_phrases.json"; DestDir: "{app}"; Flags: onlyifdoesntexist skipifsourcedoesntexist
Source: "release-lite-clean\macro_disabled.json"; DestDir: "{app}"; Flags: onlyifdoesntexist skipifsourcedoesntexist

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык EFREN Lite на рабочем столе"; Flags: unchecked
Name: "startup"; Description: "Запускать EFREN Lite вместе с Windows"; Flags: unchecked

[Icons]
; This entry is intentionally mandatory: Windows Search discovers desktop apps
; through the user's Start Menu. Desktop and autostart shortcuts remain optional.
Name: "{userprograms}\EFREN Lite"; Filename: "{app}\panel-wpf\bin\FridayPanel.exe"; WorkingDir: "{app}"; IconFilename: "{app}\friday_icon.ico"
Name: "{autodesktop}\EFREN Lite"; Filename: "{app}\panel-wpf\bin\FridayPanel.exe"; WorkingDir: "{app}\panel-wpf\bin"; Tasks: desktopicon
Name: "{userstartup}\EFREN Lite"; Filename: "{app}\panel-wpf\bin\FridayPanel.exe"; WorkingDir: "{app}\panel-wpf\bin"; Tasks: startup

[Run]
Filename: "{app}\panel-wpf\bin\FridayPanel.exe"; Description: "Запустить EFREN Lite"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
