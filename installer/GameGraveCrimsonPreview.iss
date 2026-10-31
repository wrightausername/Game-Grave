; Game Grave Crimson Command INTERNAL ENGINEERING PREVIEW
; This separate installer NEVER overwrites the classic Game Grave installation.
; UNSIGNED and NOT publicly released. Production Qt LGPL/redistribution, signing,
; payment and consumer Windows release acceptance remain open.
#define AppName "Game Grave Crimson Preview"
#define AppVersion "0.1.0"
#define AppExe "GameGrave-Crimson-Preview.exe"

[Setup]
AppId={{9C0B1A72-3B16-4FD3-80EA-7E944A4262FA}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Game Grave
DefaultDirName={localappdata}\Programs\Game Grave Crimson Preview
DefaultGroupName=Game Grave Crimson Preview
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename=GameGrave-Crimson-Preview-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayName={#AppName}
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupLogging=yes

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Game Grave Crimson Preview"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\Game Grave Crimson Preview"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; GroupDescription: "Optional shortcuts:"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch Crimson Command engineering preview"; Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
; Deliberately NO user data or app settings deletion here.
; This installer removes only installed application files.
