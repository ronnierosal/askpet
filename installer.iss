; PromptMate Windows installer (Inno Setup)
;
; Per-user install: no admin rights needed, deployable via Intune in user
; context. Supports silent install:  PromptMate-Setup.exe /VERYSILENT /NORESTART
; Installs over an existing version; user data in %LOCALAPPDATA%\PromptMate
; is never touched (and is preserved on uninstall).

#define AppName "PromptMate"
#define AppVersion "0.8.0"
#define AppPublisher "SLDD IT"
#define AppExeName "PromptMate.exe"

[Setup]
AppId={{A87EFF63-539B-4486-A445-8C0622F20915}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=PromptMate-Setup-{#AppVersion}
SetupIconFile=assets\promptmate.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Close a running PromptMate during upgrade, restart it after.
CloseApplications=yes
RestartApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start PromptMate when I sign in"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "dist\PromptMate\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
; Tkinter apps don't register with Restart Manager, so RestartApplications
; can't bring the pet back after a silent upgrade — relaunch it explicitly.
Filename: "{app}\{#AppExeName}"; Flags: nowait; Check: WizardSilent
