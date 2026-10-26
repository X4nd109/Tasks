; ─────────────────────────────────────────────────────────────────────────────
; tasks.iss
; Inno Setup Script für den Tasks Installer
;
; Wird von build_installer.py automatisch befüllt (Defines werden vorne
; eingefügt: RecipientName, SourceDir, OutputDir, InstallerDir).
; ─────────────────────────────────────────────────────────────────────────────

#define AppName "Tasks"
#ifndef AppVersion
#define AppVersion "2.1.0"
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
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
; OutputDir ist absolut (via #define gesetzt von build_installer.py)
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
; Alle Programm-Dateien aus dem Build-Verzeichnis (rekursiv, inkl. fonts/)
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Offizieller Python 3.12 Installer (wird temporär entpackt und nach Setup gelöscht, falls nötig)
Source: "{#InstallerDir}\python_installer.exe"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall; Check: not IsPythonInstalled

[Icons]
; Startmenü: run.bat als primärer Starter (verwendet das richtige Python automatisch)
Name: "{group}\{#AppName} starten"; Filename: "{app}\run.bat"; WorkingDir: "{app}"; Comment: "Tasks starten"; IconFilename: "{app}\assets\app_icon.ico"
; Startmenü: setup.bat für Ersteinrichtung / Reparatur
Name: "{group}\{#AppName} Setup && Reparatur"; Filename: "{app}\setup.bat"; WorkingDir: "{app}"; Comment: "Python und Abhängigkeiten installieren"; IconFilename: "{app}\assets\app_icon.ico"
; Desktop (optional)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\run.bat"; WorkingDir: "{app}"; Comment: "Tasks starten"; Tasks: desktopicon; IconFilename: "{app}\assets\app_icon.ico"
; Deinstallation
Name: "{group}\{#AppName} deinstallieren"; Filename: "{uninstallexe}"

[Run]
; 1. Python silent installieren (während des Setups, NUR falls noch nicht installiert)
Filename: "{tmp}\python_installer.exe"; \
  Parameters: "/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1 Shortcuts=0"; \
  StatusMsg: "Installiere Python 3.12 (bitte kurz warten)..."; \
  Flags: waituntilterminated; \
  Check: not IsPythonInstalled

; 2. Abhängigkeiten (Pip + Playwright) installieren (als Checkbox auf Fertigstellen-Seite)
Filename: "{app}\setup.bat"; \
  WorkingDir: "{app}"; \
  Flags: postinstall shellexec; \
  Description: "Bibliotheken & Playwright installieren (empfohlen)"

; 3. Terminal-Befehl 'tasks' einrichten (als Checkbox auf Fertigstellen-Seite)
Filename: "{app}\scripts\setup_command.bat"; \
  WorkingDir: "{app}"; \
  Flags: postinstall shellexec; \
  Description: "Globalen Terminal-Befehl 'tasks' einrichten (empfohlen)"; \
  Check: ShouldSetupTasksCommand

; 4. Windows-Terminal-Profil mit Logo einrichten (als Checkbox auf Fertigstellen-Seite)
Filename: "{app}\scripts\setup_terminal_profile.bat"; \
  Parameters: "/silent"; \
  WorkingDir: "{app}"; \
  Flags: postinstall shellexec; \
  Description: "Windows-Terminal-Profil mit Logo einrichten (empfohlen)"; \
  Check: ShouldSetupTerminalProfile

; 5. Programm starten (optional)
Filename: "{app}\run.bat"; \
  WorkingDir: "{app}"; \
  Flags: postinstall shellexec nowait skipifsilent unchecked; \
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
  // Überspringen, wenn Setup mit /NOTASKS=1 oder /UPDATE=1 aufgerufen wird
  Result := (ExpandConstant('{param:notasks|0}') <> '1') and (ExpandConstant('{param:update|0}') <> '1');
end;

function ShouldSetupTerminalProfile: Boolean;
begin
  Result := (ExpandConstant('{param:noterminal|0}') <> '1') and
            (ExpandConstant('{param:update|0}') <> '1') and
            (DirExists(ExpandConstant('{localappdata}\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe')) or
             FileExists(ExpandConstant('{localappdata}\Microsoft\Windows Terminal\settings.json')));
end;

function IsPythonInstalled: Boolean;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Programs\Python\Python312\python.exe')) or
            FileExists(ExpandConstant('{localappdata}\Programs\Python\Python311\python.exe')) or
            FileExists(ExpandConstant('{localappdata}\Programs\Python\Python310\python.exe')) or
            FileExists('C:\Python312\python.exe') or
            FileExists('C:\Python310\python.exe');
end;
