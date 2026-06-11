#define MyAppName "Go2 Height Control"
#define MyAppVersion "0.1.0"
#define MyAppExeName "go2-height-control.exe"

[Setup]
AppId={{8C779312-3CB0-4E5B-AF7A-2D89265B800F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\Go2 Height Control
DefaultGroupName=Go2 Height Control
DisableProgramGroupPage=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=go2-height-control-setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\go2-height-control\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Go2 Height Control"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Go2 Height Control"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 Go2 Height Control"; Flags: nowait postinstall skipifsilent
