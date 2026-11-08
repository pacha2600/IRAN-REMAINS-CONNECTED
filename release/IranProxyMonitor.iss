#define MyAppName "IRAN REMAINS CONNECTED"
#define MyAppVersion "1.1"
#define MyAppExeName "IranRemainsConnected.exe"

[Setup]
AppId={{8A4D3798-43F5-4F4D-97E8-8A5B3D0D1FC2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=IRAN REMAINS CONNECTED Contributors
DefaultDirName={localappdata}\Programs\IRAN REMAINS CONNECTED
DefaultGroupName=IRAN REMAINS CONNECTED
OutputDir=..\release-output
OutputBaseFilename=IranRemainsConnected-Setup-v{#MyAppVersion}-win64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=..\assets\iran-remains-connected.ico
DisableProgramGroupPage=yes

[Files]
Source: "..\dist\IranRemainsConnected\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\IRAN REMAINS CONNECTED"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\IRAN REMAINS CONNECTED"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch IRAN REMAINS CONNECTED"; Flags: nowait postinstall skipifsilent
