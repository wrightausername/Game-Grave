; Game Grave Windows Installer - Inno Setup 6
; Build from source on Windows via build_installer.ps1.
; License/purchase activation is a separate service, not part of setup.
#define MyAppName "Game Grave"
#define MyAppVersion "2.4.0"
#define MyAppExeName "GameGrave.exe"

[Setup]
; Stable identity. Do not change for future in-place upgrades.
AppId={{7BF6C847-EE30-47BD-A0FA-81242DB48B0A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Game Grave
DefaultDirName={localappdata}\Programs\Game Grave
DefaultGroupName=Game Grave
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=GameGrave_Setup_v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no
MinVersion=10.0
; Preferences, Save Vault backups and license receipts live outside {app}.
; Uninstall intentionally preserves these user files, never removes game data.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\GameGrave\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Game Grave"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Game Grave"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Game Grave"; Flags: nowait postinstall skipifsilent
