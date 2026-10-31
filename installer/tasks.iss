; ─────────────────────────────────────────────────────────────────────────────
; tasks.iss
; Inno Setup Script für den Tasks Installer
;
; Wird von build_installer.py automatisch befüllt (Defines werden vorne
; eingefügt: RecipientName, SourceDir, OutputDir, InstallerDir).
; ─────────────────────────────────────────────────────────────────────────────

#define AppName "Tasks"
#ifndef AppVersion
#define AppVersion "2.3.0"
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
Filename: "{app}\scripts\setup_command.bat"; \
  WorkingDir: "{app}"; \
  Flags: postinstall shellexec; \
  Description: "Globalen Terminal-Befehl 'tasks' einrichten (empfohlen)"; \
  Check: ShouldSetupTasksCommand

; 3. Windows-Terminal-Profil mit Logo einrichten (als Checkbox auf Fertigstellen-Seite)
Filename: "{app}\scripts\setup_terminal_profile.bat"; \
  Parameters: "/silent"; \
  WorkingDir: "{app}"; \
  Flags: postinstall shellexec; \
  Description: "Windows-Terminal-Profil mit Logo einrichten (empfohlen)"; \
  Check: ShouldSetupTerminalProfile

; 4. Programm starten (optional)
Filename: "{app}\Tasks.exe"; \
  WorkingDir: "{app}"; \
  Flags: postinstall nowait skipifsilent unchecked; \
  Description: "Tasks jetzt starten"

[UninstallRun]
; Vor dem Löschen der Dateien: Terminal-Befehl 'tasks' aus dem User-PATH entfernen
Filename: "{cmd}"; Parameters: "/c ""{app}\scripts\remove_command.bat /silent"""; Flags: runhidden; RunOnceId: "RemoveTasksCommand"
; Vor dem Löschen der Dateien: Windows-Terminal-Profil entfernen
Filename: "{cmd}"; Parameters: "/c ""{app}\scripts\remove_terminal_profile.bat /silent"""; Flags: runhidden; RunOnceId: "RemoveTerminalProfile"

[UninstallDelete]
; Beim Deinstallieren nur temporäre Caches entfernen (config.json und Aufgaben bleiben für Neuinstallationen erhalten)
Type: filesandordirs; Name: "{app}\cache"
Type: files; Name: "{app}\.first_run_completed"

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
      DelTree(AppDir + '\__pycache__', True, True, True);
      DelTree(AppDir + '\assets\git-sync-tutorial', True, True, True);
      // Alten Startmenü-Unterordner aus Versionen <= 2.2.0 bereinigen
      DelTree(ExpandConstant('{autoprograms}\Tasks'), True, True, True);
    end;
  end;
end;
