[Setup]

AppName=Assistant
AppVersion=1.0
AppPublisher=Assistant

DefaultDirName={autopf}\Assistant
DefaultGroupName=Assistant

OutputDir=Output
OutputBaseFilename=Assistant_Setup

Compression=lzma
SolidCompression=yes

WizardStyle=modern
PrivilegesRequired=admin

ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64

UninstallDisplayIcon={app}\Assistant.exe


[Files]

Source: "dist\Assistant.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "config.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "memory.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "tasks.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "conversation.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "install_ollama.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "setup_model.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "ollama_installer.exe"; DestDir: "{app}"; Flags: ignoreversion


[Icons]

Name: "{group}\Assistant"; Filename: "{app}\Assistant.exe"
Name: "{commondesktop}\Assistant"; Filename: "{app}\Assistant.exe"


[Run]

Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\install_ollama.ps1"""; StatusMsg: "Installing Ollama..."; Flags: runhidden waituntilterminated

Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\setup_model.ps1"""; StatusMsg: "Setting up AI model..."; Flags: runhidden waituntilterminated

Filename: "{app}\Assistant.exe"; Description: "Launch Assistant"; Flags: nowait postinstall skipifsilent


[UninstallRun]

Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""ollama list | Select-Object -Skip 1 | ForEach-Object {{ $name = ($_ -split '\s+')[0]; if ($name) {{ ollama rm $name }} }}"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoveOllamaModels"

Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""Start-Process -FilePath '$env:LOCALAPPDATA\Programs\Ollama\unins000.exe' -ArgumentList '/SILENT' -Wait"""; Flags: runhidden waituntilterminated; RunOnceId: "UninstallOllama"

Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""Remove-Item -Recurse -Force '$env:LOCALAPPDATA\Ollama' -ErrorAction SilentlyContinue; Remove-Item -Recurse -Force '$env:USERPROFILE\.ollama' -ErrorAction SilentlyContinue"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoveOllamaFolders"