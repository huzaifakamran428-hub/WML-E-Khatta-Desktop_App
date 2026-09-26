; ============================================================
;  WML E-Khatta — Windows Installer Script (Inno Setup)
; ============================================================
;  Packages the PyInstaller output (dist\WML E-Khatta\) into a
;  normal Windows installer — Start Menu + Desktop shortcut,
;  and an Uninstaller. No Python or terminal needed to install.
;
;  Build steps (on Windows, with Inno Setup installed):
;    1. pip install -r requirements.txt
;    2. pyinstaller wml_ekhatta.spec
;    3. Open this .iss file in Inno Setup and click Compile
;       (or: iscc installer\WML_E-Khatta_Setup.iss)
; ============================================================

#define MyAppName "WML E-Khatta"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Waqare Medina Computers & Laptop"
#define MyAppExeName "WML E-Khatta.exe"
#define MyDistFolder "..\dist\WML E-Khatta"
#define MyIconFile "..\assets\WaqareMedina.ico"

[Setup]
AppId={{7C2E9C7A-4C19-4E8B-9B1E-WMLEKHATTA002}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=.
OutputBaseFilename=WML_E-Khatta_Setup
SetupIconFile={#MyIconFile}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#MyDistFolder}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent
