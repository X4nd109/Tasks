; ─────────────────────────────────────────────────────────────────────────────
; tasks.iss
; Inno Setup Script für den Tasks Installer
;
; Wird von build_installer.py automatisch befüllt (Defines werden vorne
; eingefügt: RecipientName, SourceDir, OutputDir, InstallerDir).
; ─────────────────────────────────────────────────────────────────────────────

#define AppName "Tasks"
#ifndef AppVersion
#define AppVersion "2.4.0"
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
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; Symbole explizit deklarieren (stellt sicher, dass PNG & ICO immer verpackt werden)
Source: "{#SourceDir}\assets\app_icon.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "{#SourceDir}\assets\app_icon.png"; DestDir: "{app}\assets"; Flags: ignoreversion
; Alle kompilierten Programm-Dateien aus dist\Tasks (rekursiv, inkl. _internal/ und fonts/)
Source: "{#SourceDir}\dist\Tasks\*"; DestDir: "{app}"; Excludes: "cache\*,data\*,config.json,*.log,skills\*"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Desktop shortcut (optional task)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Tasks.exe"; WorkingDir: "{app}"; Comment: "Open Tasks"; Tasks: desktopicon; IconFilename: "{app}\assets\app_icon.ico"
[Run]
; 1. Setup Playwright Chromium Browser silently (for Teams login)
Filename: "{app}\Tasks.exe"; \
  Parameters: "--install-playwright"; \
  StatusMsg: "Setting up browser components (please wait)..."; \
  Flags: runhidden waituntilterminated

; 2. Add 'tasks' command to PATH
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""$app = '{app}'; $p = [Environment]::GetEnvironmentVariable('Path', 'User'); if (-not $p) {{ $p = '' }}; $parts = $p.Split(';') | Where-Object {{ $_ -ne '' }}; if ($parts -notcontains $app) {{ [Environment]::SetEnvironmentVariable('Path', (($parts + $app) -join ';'), 'User') }}"""; \
  WorkingDir: "{app}"; \
  Flags: runhidden postinstall; \
  Description: "Add 'tasks' command to PATH"; \
  Check: ShouldSetupTasksCommand

; 3. Configure Windows Terminal profile
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""$app = '{app}'; $guid = '{{b4e2a1c3-7f8d-4a2e-9b1f-3c5d6e7a8b9c}}'; $candidates = @((Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json'), (Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe\LocalState\settings.json'), (Join-Path $env:LOCALAPPDATA 'Microsoft\Windows Terminal\settings.json')); $candidates | Where-Object {{ Test-Path $_ }} | ForEach-Object {{ $file = $_; try {{ $data = Get-Content $file -Raw -Encoding UTF8 | ConvertFrom-Json; $icon = Join-Path $app 'assets\app_icon.png'; if (-not (Test-Path $icon)) {{ $icon = Join-Path $app 'assets\app_icon.ico' }}; $entry = [ordered]@{{ guid = $guid; name = 'Tasks'; commandline = (Join-Path $app 'Tasks.exe'); startingDirectory = $app; icon = $icon; tabTitle = 'Tasks'; hidden = $false }}; if ($data.profiles.list) {{ $data.profiles.list = @($data.profiles.list | Where-Object {{ $_.guid -ne $guid -and $_.name -ne 'Tasks' -and $_.name -ne 'Aufgaben-Detector' }}) + [PSCustomObject]$entry }} elseif ($data.profiles -is [System.Array]) {{ $data.profiles = @($data.profiles | Where-Object {{ $_.guid -ne $guid -and $_.name -ne 'Tasks' -and $_.name -ne 'Aufgaben-Detector' }}) + [PSCustomObject]$entry }}; $json = $data | ConvertTo-Json -Depth 32; [System.IO.File]::WriteAllText($file, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false)) }} catch {{}} }}"""; \
  WorkingDir: "{app}"; \
  Flags: runhidden postinstall; \
  Description: "Configure Windows Terminal profile"; \
  Check: ShouldSetupTerminalProfile

; 4. Add Tasks to Start Menu
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""$ws = New-Object -ComObject WScript.Shell; $target = '{autoprograms}\{#AppName}.lnk'; $s = $ws.CreateShortcut($target); $s.TargetPath = '{app}\Tasks.exe'; $s.WorkingDirectory = '{app}'; $s.IconLocation = '{app}\assets\app_icon.ico,0'; $s.Description = 'Open Tasks'; $s.Save()"""; \
  WorkingDir: "{app}"; \
  Flags: runhidden postinstall; \
  Description: "Add Tasks to Start Menu"; \
  Check: ShouldSetupStartMenu

[UninstallRun]
; Vor dem Löschen der Dateien: Terminal-Befehl 'tasks' aus dem User-PATH entfernen
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""$app = '{app}'; $p = [Environment]::GetEnvironmentVariable('Path', 'User'); if ($p) {{ $parts = $p.Split(';') | Where-Object {{ $_ -ne '' -and $_.TrimEnd('\') -ne $app.TrimEnd('\') }}; [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User') }}"""; \
  Flags: runhidden; RunOnceId: "RemoveTasksCommand"

; Vor dem Löschen der Dateien: Windows-Terminal-Profil entfernen
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""$guid = '{{b4e2a1c3-7f8d-4a2e-9b1f-3c5d6e7a8b9c}'; $candidates = @((Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json'), (Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe\LocalState\settings.json'), (Join-Path $env:LOCALAPPDATA 'Microsoft\Windows Terminal\settings.json')); $candidates | Where-Object {{ Test-Path $_ }} | ForEach-Object {{ $file = $_; try {{ $data = Get-Content $file -Raw -Encoding UTF8 | ConvertFrom-Json; $changed = $false; if ($data.profiles.list) {{ $filtered = @($data.profiles.list | Where-Object {{ $_.guid -ne $guid -and $_.name -ne 'Tasks' -and $_.name -ne 'Aufgaben-Detector' }}); if ($filtered.Count -ne $data.profiles.list.Count) {{ $data.profiles.list = $filtered; $changed = $true; }} }} elseif ($data.profiles -is [System.Array]) {{ $filtered = @($data.profiles | Where-Object {{ $_.guid -ne $guid -and $_.name -ne 'Tasks' -and $_.name -ne 'Aufgaben-Detector' }}); if ($filtered.Count -ne $data.profiles.Count) {{ $data.profiles = $filtered; $changed = $true; }} }}; if ($changed) {{ $json = $data | ConvertTo-Json -Depth 32; [System.IO.File]::WriteAllText($file, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false)) }} }} catch {{}} }}"""; \
  Flags: runhidden; RunOnceId: "RemoveTerminalProfile"

[UninstallDelete]
; Clean up Start Menu shortcut if created
Type: files; Name: "{autoprograms}\{#AppName}.lnk"
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
  Result := (ExpandConstant('{param:notasks|0}') <> '1');
end;

function ShouldSetupStartMenu: Boolean;
begin
  Result := (ExpandConstant('{param:nostartmenu|0}') <> '1');
end;

function ShouldSetupTerminalProfile: Boolean;
begin
  Result := (ExpandConstant('{param:noterminal|0}') <> '1') and
            (DirExists(ExpandConstant('{localappdata}\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe')) or
             DirExists(ExpandConstant('{localappdata}\Packages\Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe')) or
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
      DelTree(AppDir + '\skills', True, True, True);
      DelTree(AppDir + '\__pycache__', True, True, True);
      DelTree(AppDir + '\assets\git-sync-tutorial', True, True, True);
      DelTree(AppDir + '\assets\icons', True, True, True);
      DeleteFile(AppDir + '\assets\default_courses.json');
      // Alten Startmenü-Unterordner aus Versionen <= 2.2.0 bereinigen
    // Startmenü-Verknüpfung und alte Unterordner restlos entfernen
    DeleteFile(ExpandConstant('{autoprograms}\{#AppName}.lnk'));
      DelTree(ExpandConstant('{autoprograms}\Tasks'), True, True, True);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDir: string;
  FallbackDir: string;
begin
  if CurUninstallStep = usUninstall then
  begin
    // Autostart Registry-Eintrag entfernen
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Tasks');
    // tasks:// URL-Protokoll & Toast-AppUserModelId entfernen
    RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\Classes\tasks');
    RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\Classes\AppUserModelId\Tasks');
  end;
  if CurUninstallStep = usPostUninstall then
  begin
    AppDir := ExpandConstant('{app}');
    // Restordner restlos entfernen, wenn kein Entwicklungsordner (.git)
    if not DirExists(AppDir + '\.git') then
    begin
      DelTree(AppDir, True, True, True);
    end;
    // Alten Startmenü-Unterordner aus Versionen <= 2.2.0 restlos entfernen
    // Startmenü-Verknüpfung und alte Unterordner restlos entfernen
    DeleteFile(ExpandConstant('{autoprograms}\{#AppName}.lnk'));
    DelTree(ExpandConstant('{autoprograms}\Tasks'), True, True, True);
    // Fallback AppData-Ordner (%LOCALAPPDATA%\Tasks) restlos entfernen, falls separat
    FallbackDir := ExpandConstant('{localappdata}\{#AppName}');
    if (FallbackDir <> '') and (AppDir <> FallbackDir) and not DirExists(FallbackDir + '\.git') then
    begin
      DelTree(FallbackDir, True, True, True);
    end;
  end;
end;
