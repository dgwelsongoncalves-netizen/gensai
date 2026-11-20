#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

[Setup]
AppName=Gensai PDF
AppVersion={#MyAppVersion}
AppPublisher=Darllen Welson Gonçalves
AppPublisherURL=https://github.com/dgwelsongoncalves-netizen/gensai
DefaultDirName={autopf}\Gensai PDF
DefaultGroupName=Gensai PDF
LicenseFile=LICENSE
SetupIconFile=assets\gensai.ico
OutputDir=Instalador_Final
OutputBaseFilename=Instalador_Gensai
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\gensai.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Gensai PDF"; Filename: "{app}\gensai.exe"
Name: "{autodesktop}\Gensai PDF"; Filename: "{app}\gensai.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\gensai.exe"; Description: "{cm:LaunchProgram,Gensai PDF}"; Flags: nowait postinstall skipifsilent