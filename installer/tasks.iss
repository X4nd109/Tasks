; ─────────────────────────────────────────────────────────────────────────────
; tasks.iss
; Inno Setup Script für den Tasks Installer
;
; Wird von build_installer.py automatisch befüllt (Defines werden vorne
; eingefügt: RecipientName, SourceDir, OutputDir, InstallerDir).
; ─────────────────────────────────────────────────────────────────────────────

#define AppName "Tasks"
#ifndef AppVersion
#define AppVersion "2.3.1"
#endif
#define AppPublisher "Alexander Endl"
#define AppURL "https://github.com/X4nd109/Tasks"

#ifndef OutputBaseFilename
#define OutputBaseFilename "Tasks_Setup"
#endif

[Setup]
AppId={{B4E2A1C3-7F8D-4A2E-9B1F-3C5D6E7A8B9C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseFilename}
SetupIconFile={#SourceDir}\assets\app_icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

; Pfadauswahl IMMER anzeigen, auch bei wiederholter Installation
DisableDirPage=no
UsePreviousAppDir=no

; Keine Admin-Rechte nötig – installiert in %LOCALAPPDATA% wenn kein Admin
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Windows 10 minimum
MinVersion=10.0
CloseApplications=yes
CloseApplicationsFilter=Tasks.exe,TasksTray.exe

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknüpfung erstellen"; GroupDescription: "Zusätzliche Symbole:"

[Files]
; Symbole explizit deklarieren (stellt sicher, dass PNG & ICO immer verpackt werden)
Source: "{#SourceDir}\assets\app_icon.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "{#SourceDir}\assets\app_icon.png"; DestDir: "{app}\assets"; Flags: ignoreversion
; Alle kompilierten Programm-Dateien aus dist\Tasks (rekursiv, inkl. _internal/ und fonts/)
Source: "{#SourceDir}\dist\Tasks\*"; DestDir: "{app}"; Excludes: "cache\*,data\*,config.json,*.log"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Startmenü: Exakt EIN einziger Startmenü-Eintrag mit dem Namen "Tasks"
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\Tasks.exe"; WorkingDir: "{app}"; Comment: "Tasks öffnen"; IconFilename: "{app}\assets\app_icon.ico"
; Desktop-Verknüpfung
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Tasks.exe"; WorkingDir: "{app}"; Comment: "Tasks öffnen"; Tasks: desktopicon; IconFilename: "{app}\assets\app_icon.ico"

[Run]
; 1. Playwright Chromium Browser silent einrichten (für Teams-Login)
Filename: "{app}\Tasks.exe"; \
  Parameters: "--install-playwright"; \
  StatusMsg: "Richte Browser-Komponenten ein (bitte kurz warten)..."; \
  Flags: runhidden waituntilterminated

; 2. Terminal-Befehl 'tasks' einrichten (als Checkbox auf Fertigstellen-Seite)
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""$app = '{app}'; $p = [Environment]::GetEnvironmentVariable('Path', 'User'); if (-not $p) {{ $p = '' }}; $parts = $p.Split(';') | Where-Object {{ $_ -ne '' }}; if ($parts -notcontains $app) {{ [Environment]::SetEnvironmentVariable('Path', (($parts + $app) -join ';'), 'User') }}"""; \
  WorkingDir: "{app}"; \
  Flags: runhidden postinstall; \
  Description: "Globalen Terminal-Befehl 'tasks' einrichten (empfohlen)"; \
  Check: ShouldSetupTasksCommand

; 3. Windows-Terminal-Profil mit Logo einrichten (als Checkbox auf Fertigstellen-Seite)
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""$app = '{app}'; $guid = '{{b4e2a1c3-7f8d-4a2e-9b1f-3c5d6e7a8b9c}'; $candidates = @((Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json'), (Join-Path $env:LOCALAPPDATA 'Microsoft\Windows Terminal\settings.json')); $file = $candidates | Where-Object {{ Test-Path $_ }} | Select-Object -First 1; if ($file) {{ try {{ $data = Get-Content $file -Raw -Encoding UTF8 | ConvertFrom-Json; $icon = Join-Path $app 'assets\app_icon.png'; if (-not (Test-Path $icon)) {{ $icon = Join-Path $app 'assets\app_icon.ico' }}; $entry = [ordered]@{{ guid = $guid; name = 'Tasks'; commandline = (Join-Path $app 'Tasks.exe'); startingDirectory = $app; icon = $icon; tabTitle = 'Tasks'; hidden = $false }}; if ($data.profiles.list) {{ $data.profiles.list = @($data.profiles.list | Where-Object {{ $_.guid -ne $guid -and $_.name -ne 'Tasks' -and $_.name -ne 'Aufgaben-Detector' }}) + [PSCustomObject]$entry }} elseif ($data.profiles -is [System.Array]) {{ $data.profiles = @($data.profiles | Where-Object {{ $_.guid -ne $guid -and $_.name -ne 'Tasks' -and $_.name -ne 'Aufgaben-Detector' }}) + [PSCustomObject]$entry }}; $json = $data | ConvertTo-Json -Depth 32; [System.IO.File]::WriteAllText($file, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false)) }} catch {{}} }}"""; \
  WorkingDir: "{app}"; \
  Flags: runhidden postinstall; \
  Description: "Windows-Terminal-Profil mit Logo einrichten (empfohlen)"; \
  Check: ShouldSetupTerminalProfile

; 4. Programm starten (optional)
Filename: "{app}\Tasks.exe"; \
  WorkingDir: "{app}"; \
  Flags: postinstall nowait skipifsilent unchecked; \
  Description: "Tasks jetzt starten"

[UninstallRun]
; Vor dem Löschen der Dateien: Terminal-Befehl 'tasks' aus dem User-PATH entfernen
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""$app = '{app}'; $p = [Environment]::GetEnvironmentVariable('Path', 'User'); if ($p) {{ $parts = $p.Split(';') | Where-Object {{ $_ -ne '' -and $_.TrimEnd('\') -ne $app.TrimEnd('\') }}; [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User') }}"""; \
  Flags: runhidden; RunOnceId: "RemoveTasksCommand"

; Vor dem Löschen der Dateien: Windows-Terminal-Profil entfernen
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""$guid = '{{b4e2a1c3-7f8d-4a2e-9b1f-3c5d6e7a8b9c}'; $candidates = @((Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json'), (Join-Path $env:LOCALAPPDATA 'Microsoft\Windows Terminal\settings.json')); $file = $candidates | Where-Object {{ Test-Path $_ }} | Select-Object -First 1; if ($file) {{ try {{ $data = Get-Content $file -Raw -Encoding UTF8 | ConvertFrom-Json; if ($data.profiles.list) {{ $data.profiles.list = @($data.profiles.list | Where-Object {{ $_.guid -ne $guid -and $_.name -ne 'Tasks' -and $_.name -ne 'Aufgaben-Detector' }}) }} elseif ($data.profiles -is [System.Array]) {{ $data.profiles = @($data.profiles | Where-Object {{ $_.guid -ne $guid -and $_.name -ne 'Tasks' -and $_.name -ne 'Aufgaben-Detector' }}) }}; $json = $data | ConvertTo-Json -Depth 32; [System.IO.File]::WriteAllText($file, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false)) }} catch {{}} }}"""; \
  Flags: runhidden; RunOnceId: "RemoveTerminalProfile"

[UninstallDelete]
; Vollständige Bereinigung aller Runtime-Verzeichnisse und temporären Dateien
Type: filesandordirs; Name: "{app}\cache"
Type: filesandordirs; Name: "{app}\data"
Type: filesandordirs; Name: "{app}\skills"
Type: filesandordirs; Name: "{app}\scripts"
Type: filesandordirs; Name: "{app}\assets"
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\config.json"
Type: files; Name: "{app}\.first_run_completed"
Type: files; Name: "{app}\*.log"

[Code]
function ShouldSetupTasksCommand: Boolean;
begin
  Result := (ExpandConstant('{param:notasks|0}') <> '1') and (ExpandConstant('{param:update|0}') <> '1');
end;

function ShouldSetupTerminalProfile: Boolean;
begin
  Result := (ExpandConstant('{param:noterminal|0}') <> '1') and
            (ExpandConstant('{param:update|0}') <> '1') and
            (DirExists(ExpandConstant('{localappdata}\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe')) or
             FileExists(ExpandConstant('{localappdata}\Microsoft\Windows Terminal\settings.json')));
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  AppDir: string;
begin
  if CurStep = ssInstall then
  begin
    AppDir := ExpandConstant('{app}');
    // ABSOLUTER SCHUTZ: Wenn .git existiert, NIEMALS loeschen (Development-Ordner)
    if not DirExists(AppDir + '\.git') then
    begin
      DeleteFile(AppDir + '\main.py');
      DeleteFile(AppDir + '\setup.bat');
      DeleteFile(AppDir + '\run.bat');
      DeleteFile(AppDir + '\tasks.bat');
      DeleteFile(AppDir + '\requirements.txt');
      DelTree(AppDir + '\src', True, True, True);
      DelTree(AppDir + '\tests', True, True, True);
      DelTree(AppDir + '\scripts', True, True, True);
      DelTree(AppDir + '\__pycache__', True, True, True);
      DelTree(AppDir + '\assets\git-sync-tutorial', True, True, True);
      DelTree(AppDir + '\assets\icons', True, True, True);
      DeleteFile(AppDir + '\assets\default_courses.json');
      // Alten Startmenü-Unterordner aus Versionen <= 2.2.0 bereinigen
      DelTree(ExpandConstant('{autoprograms}\Tasks'), True, True, True);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDir: string;
begin
  if CurUninstallStep = usUninstall then
  begin
    // Autostart Registry-Eintrag entfernen
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Tasks');
  end;
  if CurUninstallStep = usPostUninstall then
  begin
    AppDir := ExpandConstant('{app}');
    // Restordner restlos entfernen, wenn kein Entwicklungsordner (.git)
    if not DirExists(AppDir + '\.git') then
    begin
      DelTree(AppDir, True, True, True);
    end;
  end;
end;
