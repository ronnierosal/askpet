; AskPet Windows installer (Inno Setup)
;
; Per-user install: no admin rights needed, deployable via Intune in user
; context. Supports silent install:  AskPet-Setup.exe /VERYSILENT /NORESTART
; Installs over an existing version; user data in %LOCALAPPDATA%\AskPet
; is never touched (and is preserved on uninstall).

#define AppName "AskPet"
#define AppVersion "0.26.1"
#define AppPublisher "SLDD IT"
#define AppExeName "AskPet.exe"

[Setup]
AppId={{2A6A714C-C209-4444-9124-3C3B8A5252FF}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=AskPet-Setup-{#AppVersion}
SetupIconFile=assets\askpet.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Close a running AskPet during upgrade, restart it after.
CloseApplications=yes
RestartApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start AskPet when I sign in"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "dist\AskPet\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
; Tkinter apps don't register with Restart Manager, so RestartApplications
; can't bring the pet back after a silent upgrade ??? relaunch it explicitly.
Filename: "{app}\{#AppExeName}"; Flags: nowait; Check: WizardSilent
