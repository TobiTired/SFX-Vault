#ifndef AppVersion
  #define AppVersion "0.7.0"
#endif
#ifndef AppSource
  #define AppSource "..\dist\SFX Vault"
#endif
#ifndef ReleaseOutput
  #define ReleaseOutput "..\release"
#endif
#ifdef TestBuild
  #define ProductName "SFX Vault Update Test"
  #define ProductId "{{A14918D4-8679-488D-A7EB-004D76691DCF}"
  #define ProductMutex "SFXVault.UpdateTest"
#else
  #define ProductName "SFX Vault"
  #define ProductId "{{68CA1EB5-03FB-4754-A022-7CCAE5C56534}"
  #define ProductMutex "SFXVault.Desktop"
#endif
[Setup]
AppId={#ProductId}
AppName={#ProductName}
AppVersion={#AppVersion}
AppVerName={#ProductName} {#AppVersion}
AppPublisher=SFX Vault
DefaultDirName={localappdata}\Programs\{#ProductName}
DefaultGroupName={#ProductName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ReleaseOutput}
OutputBaseFilename=SFX-Vault-Setup-{#AppVersion}
SetupIconFile=..\sfx_vault\assets\sfx-vault.ico
UninstallDisplayIcon={app}\SFX Vault.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
AppMutex={#ProductMutex}
CloseApplications=no
RestartApplications=no
SetupLogging=yes
InfoAfterFile=data-retention.txt
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{userprograms}\{#ProductName}"; Filename: "{app}\SFX Vault.exe"; WorkingDir: "{app}"; IconFilename: "{app}\_internal\sfx_vault\assets\sfx-vault.ico"
Name: "{userdesktop}\{#ProductName}"; Filename: "{app}\SFX Vault.exe"; WorkingDir: "{app}"; Tasks: desktopicon; IconFilename: "{app}\_internal\sfx_vault\assets\sfx-vault.ico"
[Run]
Filename: "{app}\SFX Vault.exe"; Description: "Launch {#ProductName}"; Flags: nowait postinstall skipifsilent
; No AppData files are installed or deleted. No UninstallDelete section.
