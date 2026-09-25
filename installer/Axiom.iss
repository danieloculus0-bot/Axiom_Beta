#define MyAppName "Axiom"
#define MyAppVersion "1.0.0-beta"
#define MyAppPublisher "Axiom / EZ Fabricating"
#define MyAppExeName "Axiom.exe"

[Setup]
AppId={{7B784178-8FE6-47FA-A7E8-55071D2F9C1A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Axiom
DefaultGroupName=Axiom
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist-installer
OutputBaseFilename=Axiom_Setup_1.0.0-beta
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
UninstallDisplayName=Axiom
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; Flags: ignoreversion

[Icons]
Name: "{group}\Axiom"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\Axiom"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Axiom"; Flags: nowait postinstall skipifsilent

; Operational data lives outside {app}. The uninstaller intentionally does not
; remove Axiom databases, audit journals, attachments, integrations or user data.
