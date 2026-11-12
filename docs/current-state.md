# Current Project State & Session Handoff — Tasks

> **Last Updated**: 2026-11-12  
> **Active Milestone**: Release v2.5.1 (Released)

---

## 1. Completed Tasks & Milestones

- [x] **Playwright Standalone Exe & Multiprocessing Fixes für Tasks.exe (2026-11-12)**:
  - **Problem**: Nach der Umstellung auf `.exe` brach der Buch-Download (Digi4School) ab mit `Executable doesn't exist at ...\_internal\playwright\driver\package\.local-browsers\...`. Playwright setzte im PyInstaller-Modus hart `PLAYWRIGHT_BROWSERS_PATH="0"`, während der Inno Setup Installer Browser nach `%LOCALAPPDATA%\ms-playwright` installierte. Zudem fehlten Fallbacks auf System-Chrome/Edge, `freeze_support()` fehlte in `main.py` (OCR/Kompaktierung-Worker crashten mit `--multiprocessing-fork`), und `dependency_checker.py` versuchte `Tasks.exe -m playwright` aufzurufen.
  - **Lösung & Umsetzung**:
    - `main.py`: UTF-8 Console-Encoding für `stdout`/`stderr` auf Windows forciert (verhindert cp1252-Abstürze bei Box-Zeichen), `multiprocessing.freeze_support()` direkt beim Start aufgerufen und `PLAYWRIGHT_BROWSERS_PATH` auf `%LOCALAPPDATA%\ms-playwright` abgesichert.
    - `src/services/digi4school_service.py`: `_launch_playwright_browser` mit Fallback-Kaskade (`[Standard-Chromium, "chrome", "msedge"]`) in `inspect_book` und `download_book` integriert.
    - `src/services/moodle_service.py`: Moodle-Task-Details ebenfalls mit Channel-Fallback abgesichert.
    - `src/core/dependency_checker.py`: Im Frozen-Modus auf `Tasks.exe --install-playwright` umgestellt.
    - **Validierung**: 606 Unit-Tests bestanden, PyInstaller-Build erfolgreich, Live-Test der kompilierten `Tasks.exe` verifiziert.
    - **Release**: Version auf 2.5.1 angehoben (`APP_VERSION`, Inno Setup, Version-Info Structs).

- [x] **Ausfallsicheres Update-System (Resilient Updates mit Range-Resuming & Retries) (2026-11-08)**:
  - **Problem & Anforderung**: Bei langsamen oder instabilen Internetverbindungen schlug das Update komplett fehl. Der Release-Check brach bereits nach 3 Sekunden mit irreführender Meldung ab (*"Tasks is already up to date"*). Der ~80 MB Installer-Download brach bei kurzen Netzwerk-Schwankungen ohne Wiederholungsversuche sofort ab und löschte alle bereits geladenen Teildaten, was den Benutzer dazu zwang, den Download manuell im Browser durchzuführen.
  - **Umsetzung & Status**:
    - `src/services/update_service.py`:
      - `check_for_updates`: Default-Timeout von 3s auf 12s erhöht, plus 1 automatischer Retry bei Netzwerkproblemen.
      - `download_update_installer`: Neuer Parameter `status_callback` und `max_retries=3`. Vollständige HTTP-Range-Header-Unterstützung (`Range: bytes={offset}-`), Auswertung von HTTP 206 (Partial Content) vs. HTTP 200 (Reset), automatischer Backoff (2s, 4s, 8s) bei Socket-Fehlern, sauberes Löschen der `.part`-Datei nur bei explizitem Benutzerabbruch via `cancel_event` und Erhalt von `.part` bei Netzwerkfehlern für nahtloses Resuming.
    - `src/ui/tui_app.py`:
      - `UpdateReminderModal`: `_on_download_status()` implementiert und via `status_callback` angebunden. Anzeige von Warnungen und Retry-Versuchen (`⏳ Connection interrupted... Retrying (1/3) in 2s...`) direkt im Status-Label. Bei Fehlschlag setzt ein Klick auf *🔄 Try Again* den Download nahtlos an den bereits geladenen Megabytes fort.
    - `src/core/agent_cli.py`:
      - `tasks update`: Live-Download-Fortschritt (`cur_mb / tot_mb (pct%)`) und Konsolenausgabe von Verbindungs- und Retry-Meldungen via `status_callback`.
    - `update.bat`:
      - Standalone-Batch-Reparaturtool im eingebetteten PowerShell-Teil ebenfalls mit Range-Requests (`$request.AddRange`), Retry-Schleife (bis zu 3 Versuche) und Konsolen-Rückmeldungen abgesichert.
    - **Testabdeckung**:
      - `tests/test_update_service.py` um 5 neue Tests erweitert (API-Check-Timeout-Retry, HTTP 206 Range-Resuming, HTTP 200 Fallback-Reset, Retry bei Socket-Drop inkl. `status_callback`, Erhalt der `.part`-Datei bei Fehlererschöpfung).
      - Alle 26 Tests in `test_update_service.py` und alle 606 Tests der Gesamtsuite bestanden (100% grün).

- [x] **TwoThumbRangeSlider Text-Markierung beim Verschieben unterbunden (2026-11-08)**:
  - `ALLOW_SELECT = False` auf `TwoThumbRangeSlider` gesetzt, `capture_mouse()`/`release_mouse()` implementiert und Mouse-Events mit `prevent_default()` und `stop()` isoliert. Der Slider gleitet nun wie ein echtes GUI-Element ohne Text-Hervorhebung, bei 100% identischem optischen Design.
  - 14 Tests in `tests/test_page_range_slider.py` validiert (100% bestanden).

- [x] **Digi4School Multi-Core PDF-Komprimierung & `tasks books compact` (2026-11-08)**:
    - **Multi-Core Beschleunigung**: `compact_pdf_document` nutzt `ProcessPoolExecutor` mit dynamischem Worker-Pool (`os.cpu_count() - 1` Standard, überschreibbar mit `--workers <N>`). Bilder werden über ein Sliding Window kontinuierlich komprimiert und sofort in PyMuPDF eingebettet, was den RAM-Bedarf unter 400 MB hält und 400-Seiten-Bücher in Sekunden abarbeitet.
  - **Ziel**: Die vom Digi4School Grabber erzeugten PDFs waren durch unkomprimierte PNG/FlateDecode-Bilder extrem groß (~850 MB für 400 Seiten). Downloads sollten auf kompakte JPEGs mit 4:4:4 Farbsampling umgestellt und bereits vorhandene PDFs offline nachträglich schrumpfbar werden.
  - **Umsetzung & Status**:
    - `src/services/digi4school_service.py`:
      - `encode_image_dct(pil_img, quality=90, subsampling=0)`: JPEG-Kodierung inkl. RGB-Konvertierung, `optimize=True` und robustem Fallback für Pillow-Versionen, die `optimize` + 4:4:4 nicht unterstützen.
      - `ocr_worker_process`: JPEG wird in eine temporäre `.jpg`-Datei geschrieben und an `pytesseract.image_to_pdf_or_hocr` übergeben → Tesseract bettet `DCTDecode` (JPEG) ein. Fallback-Konfigurationen und letzter Bild-only-Fallback nutzen dasselbe optimierte JPEG.
      - `download_book(..., jpeg_quality=None)`: Preset-Mapping `standard=80`, `high=85`, `ultra=90` (Default 90); Weitergabe an OCR-Worker; `--no-ocr`-Pfad konvertiert `img_bytes` vor `insert_image`.
      - `compact_pdf_document(...)`: Ersetzt alle eingebetteten Bilder via `page.replace_image(xref, stream=jpeg)`, speichert mit `garbage=4, deflate=True, clean=True`, validiert Seitenanzahl und ersetzt das Original atomar (optional `*.orig.pdf`).
      - `Digi4SchoolService.list_downloaded_books()` listet PDFs im Downloadordner (ohne `.orig.pdf`/Temp-Dateien).
    - `src/core/agent_cli.py`:
      - Neuer Subcommand `tasks books compact <datei|index|all> [--quality 1-100] [--workers <N>] [--keep-original] [--output <pfad>] [--json]` inkl. Fortschritt, Zusammenfassung (`Before -> After (Saved: X MB / Y%)`) und Fehlerbehandlung.
      - `tasks books download` unterstützt zusätzlich `--jpeg-quality <1-100>`.
    - **Dokumentation**: `docs/features.md`, `docs/changelog.md` und dieser Session-Handoff aktualisiert.
  - **Tests**: `tests/test_digi4school.py` um 7 Tests erweitert (JPEG-Header/4:4:4-Sampling, `compact_pdf_document` Größe/Text/TOC/Seitenzahl, `--keep-original`, Multi-Core mit `max_workers=2`, CLI `compact --json`, CLI `--workers`, Qualitätsvalidierung). Alle 20 Tests bestanden (bei nicht-interaktivem stdin).

- [x] **Tasks PyInstaller Executable & Clean Installer Implementation (2026-11-04)**:
  - **Aufgabe**: Standalone-Binaries (`Tasks.exe` Console + `TasksTray.exe` Windowed), PyInstaller Onedir-Build, Clean Inno-Setup-Installer, Playwright-Silent-Setup und Frozen-Path-Handling.
  - **Umsetzung & Status**:
    - `requirements.txt`: `pyinstaller>=6.0.0` unter `# Build & Packaging` erg�nzt.
    - `src/core/config.py`: Frozen-Bundle-Pfade (`WORKSPACE_DIR`, `SRC_DIR`, `CORE_DIR`) via `sys.frozen` inkl. `_internal`-Fallback; `DATA_DIR`/`ASSETS_DIR` konsistent gebunden.
    - `main.py`: `--install-playwright` (Playwright Chromium silent install) und `TasksTray.exe` -> Auto-Append `--tray`.
    - `src/services/autostart_service.py`: Autostart registriert `TasksTray.exe` direkt, sobald es existiert.
    - `src/services/update_service.py`: `apply_update.cmd` startet nach Update `Tasks.exe` (Fallback `run.bat`).
    - `tasks.spec`: PyInstaller Onedir-Spec (2 Exe: Console `Tasks.exe`, Windowed `TasksTray.exe`, excludes `tkinter`/`matplotlib`/`unittest`, datas `assets`/`skills`/`src`, Version-Info via `installer/version_info*.txt`).
    - `scripts/build_exe.py`: PyInstaller-Build + Copy von `tasks.cmd`, Helper-Skripten (`scripts/*.bat`), Icons und Skills; Cleanup von `assets/git-sync-tutorial`; Verify `dist/Tasks/Tasks.exe` & `TasksTray.exe`.
    - `build.bat`: Fuehrt `python scripts/build_exe.py` aus.
    - `installer/tasks.iss`: Clean Installer (Bundle `dist\Tasks\*`, silent Playwright-Setup, Start-Menü+Desktop-Icons, obsolete File-/Dir-Cleanup ohne Daten/Cache).
    - `installer/build_installer.py`: Verifiziert `dist/Tasks/Tasks.exe` und startet bei Bedarf `scripts/build_exe.py`.
  - **Tests**: Build-/Packaging-Code nicht Teil der Unittest-Suite; Gesamtsuite (592 Tests) ohne neue Fehler/Regressionen.

- [x] **AI Agent Hub Modal, Skill State Management, Relocation & Clean Unlink/Removal Flow (2026-11-02)**:
    6. **Automatische Integritätsprüfung bei manuellem Löschen auf der Festplatte**:
       - Wenn ein Benutzer den Ordner oder die `SKILL.md` außerhalb von Tasks manuell löscht, erkennt `verify_skill_integrity()` dies bei jedem Programmstart (`TasksApp.on_mount`), vor jeder Hintergrund-Update-Prüfung (`_start_update_checker`), im CLI (`tasks update`) sowie beim Öffnen des Hubs (`AgentHubModal._refresh_state`).
       - Die Konfiguration wird sofort bereinigt (`clear_skill_target_dir()`), der Button `Skill State` im Hub wird deaktiviert und in Tasks erscheint rechts unten eine Warning-Toast-Benachrichtigung: `"Agent Skill was unexpectedly removed"`.
  - **Problem & Anforderungen**:
    1. Wenn ein Benutzer den AI Agent Skill eingerichtet hat und später nicht mehr verwenden möchte, blieb der Pfad weiterhin in der Konfiguration hinterlegt, sodass der Skill bei jedem zukünftigen Update erneut heruntergeladen und installiert wurde.
    2. Es fehlte ein zentraler Hub beim Klick auf den 🤖 Agent-Button im Chat, der vor dem Guide geschaltet ist und zwei klare Optionen bietet: 🛠️ Setup Guide und 📊 Skill State.
    3. Der 📊 Skill State-Button muss dynamisch ausgegraut (disabled = True) sein, wenn noch kein Skill installiert/hinterlegt ist.
    4. Das neue AgentSkillStatusModal (auf Englisch) soll den aktuellen Zielordner anzeigen, den Status der automatischen Updates (ENABLED), einen 📦 Move Skill-Button zum Verschieben an einen neuen Ordner (inkl. Bereinigung der alten SKILL.md) und einen 🗑️ Remove Skill-Button besitzen.
    5. Vor dem Löschen muss ein Sicherheitsdialog (ConfirmSkillRemovalModal) bestätigen; nach der Bestätigung wird SKILL.md gelöscht, die Auto-Update-Eintragung entfernt (clear_skill_target_dir()) und der Benutzer kehrt zum AgentHubModal zurück, wo der 📊 Skill State-Button sofort wieder dynamisch ausgegraut ist.
  - **Lösung & Implementierung**:
    - src/core/config.py:
      - Neue atomare Funktion clear_skill_target_dir() -> bool entfernt den Key skill_target_dir synchron aus APP_CONFIG_FILE und CONFIG_FILE.
    - src/core/agent_cli.py:
      - unlink_skill(delete_files=True): Löscht SKILL.md, entfernt leere Verzeichnisse und leert die Konfiguration.
      - move_skill_target_dir(new_target_dir): Normalisiert den neuen Zielordner (mit automatischer 	asks-Namensprüfung), synchronisiert den Skill dorthin, bereinigt die alte SKILL.md und aktualisiert den Konfigurationspfad.
      - CLI-Befehle 	asks skill remove / 	asks skill unlink [--keep-files] [--json] und 	asks skill move <pfad> [--json].
    - src/ui/tui_app.py:
      - ConfirmSkillRemovalModal: Sicherheitsdialog mit englischer Warnung und tn_confirm_remove (🗑️ Yes, Remove Skill) sowie tn_cancel_remove (↩️ Cancel).
      - AgentSkillStatusModal: Statusanzeige mit Verzeichnis, Auto-Update-Status und Aktionen 📦 Move Skill, 🗑️ Remove Skill und ↩️ Back.
      - AgentHubModal: Intermediärer Hub mit 🛠️ Setup Guide, 📊 Skill State (dynamisch disabled, wenn nicht installiert) und ↩️ Back. Beim Schließen des Guides oder nach Bestätigung der Löschung wird der Status sofort aktualisiert (_refresh_state()).
      - AiChatScreen: ction_open_agent_skill() öffnet nun AgentHubModal.
    - **Testabdeckung**:
      - 	ests/test_agent_skill_modal.py: 13 Unittests inklusive Tests für AgentHubModal (Ausgrauen vor Installation und nach Löschung), AgentSkillStatusModal (Statusanzeige & Verschieben) und ConfirmSkillRemovalModal (100% bestanden).
      - 	ests/test_agent_cli.py: 22 Unittests inklusive 	asks skill remove, 	asks skill unlink und 	asks skill move (100% bestanden).
      - 	ests/test_skill_auto_sync.py: 21 Unittests (100% bestanden).


- [x] **On-Demand AI Agent Skill Downloader, Installer Cleanup & TUI Universal Setup Wizard (2026-11-02)**:
  - **Problem & Anforderungen**:
    1. Bislang wurde der Ordner skills/tasks/ bei jedem Build in die Distribution und das Installer-Paket gepackt. Das vergrößerte unnötig das Setup und konnte veraltete Skill-Versionen ausliefern.
    2. Der Skill soll nun stattdessen bei Bedarf direkt aus dem öffentlichen GitHub-Repository heruntergeladen werden — und zwar zwingend ohne GitHub-Authentifizierung / Login.
    3. Bei der Neuinstallation / beim Update durch Inno Setup soll ein vorhandener alter skills/-Ordner im Anwendungsverzeichnis bereinigt werden.
    4. In der TUI sollte im AI-Chat-Menü ein neuer Button 🤖 Agent in Zeile 2 zwischen 🗑️ Clear (Zeile 1) und ↩️ Back (Zeilen 3-5) platziert werden, der einen englischsprachigen Schritt-für-Schritt-Assistenten (AgentSkillSetupModal) öffnet, welcher nicht nur für Antigravity, sondern universell für verschiedene Agent Harnesses (Antigravity, Claude Code, Cursor, Windsurf, Custom Folder) anleitet.
  - **Lösung & Implementierung**:
    - 	asks.spec & scripts/build_exe.py: skills/ aus den PyInstaller-Datas und dem Dist-Kopierschritt entfernt.
    - installer/tasks.iss: DelTree(AppDir + '\skills', True, True, True) in CurStepChanged (ssInstall) eingefügt sowie skills\* in [Files] ausgeschlossen.
    - src/core/agent_cli.py:
      - Neue Funktion download_skill_from_github(target_dir) lädt SKILL.md via urllib.request direkt und ohne Authentifizierung von https://raw.githubusercontent.com/X4nd109/Tasks/main/skills/tasks/SKILL.md.
      - sync_skill_to_dir() und handle_skill_command() greifen bei Standalone-Installationen automatisch auf den On-Demand-Download zurück; Dev-Repo-Fallback bleibt erhalten.
    - src/ui/tui_app.py:
      - Neue Modalklasse AgentSkillSetupModal: 3-stufiger englischer Wizard mit direkter Ordnerauswahl via nativem Windows Dialog (`win_dialogs.pick_directory`), schlüssellosem On-Demand-Download von GitHub und kompaktem Leitfaden.
      - **Automatische 'tasks'-Ordner-Erkennung**: Unmittelbar nach der Ordnerauswahl sowie beim Wechsel zu Schritt 2 wird im Hintergrund geprüft, ob `tasks` irgendwo im Namen des Zielordners vorkommt (z. B. `Tasks App`, `App Tasks`, `TASKS - App`, `tasks_app`). Nur falls nicht, wird `tasks` automatisch ergänzt.
      - **Flag-Persistierung erst in Schritt 3**: Das Zielverzeichnis und die Konfigurations-Flags werden erst bei erfolgreicher Skill-Installation beim Übergang zu Schritt 3 persistent gespeichert (Abbrüche in Schritt 1 oder 2 hinterlassen kein Flag).
      - AiChatScreen: Neuer Button 🤖 Agent (`btn_ai_agent_skill`, Shortcut [Alt+A]) zwischen Clear (Zeile 1) und Back (Zeilen 3-5); CSS für `#ai_input_btn_box` mit 1-Zeilen / 3-Zeilen Buttons perfekt aufgeteilt.
    - **Testabdeckung**:
      - `tests/test_agent_skill_modal.py`: 7 Unittests für Modal-Initialisierung, Ordner-Picker, Step-Transitions, Download-Worker, Button-Hierarchie und die stille automatische `tasks`-Ordnerergänzung (100% bestanden).
      - `tests/test_skill_auto_sync.py`: Unittests für schlüssellosen Download, Fehlerbehandlung und CLI-Fallback (100% bestanden).
      - `tests/test_ai_chat_ui.py`: Aktualisiert auf 3-Button-Layout (100% bestanden).
      - `tests/test_agent_cli.py`: 19 Unittests inklusive `tasks update` und `reinstall` (100% bestanden).

- [x] **Update Manager Verbesserungen: ANSI-Fix, Englische Lokalisierung, 5s Auto-Close & `update.bat` (2026-11-02)**:
  - **Problem**:
    1. In Schritt 3 des Update Managers trat durch variierende Längen des animierten Spinners eine Text-Überlappung auf (`[✓] Installation abgeschlossen. onenten...nten...`).
    2. Die Ausgaben und Fehlerboxen des Update Managers waren auf Deutsch statt einheitlich auf Englisch.
    3. Es fehlte eine Möglichkeit, Tasks drüberzuinstallieren / zu reparieren (z. B. wenn die Anwendung beschädigt ist).
    4. Das Terminal-Fenster des Update Managers blieb nach erfolgreichem Update im PowerShell-Prompt offen (`-NoExit`), statt sich nach einem kurzen Countdown selbstständig zu schließen.
  - **Lösung & Implementierung**:
    - `src/services/update_service.py`:
      - **ANSI-Bereinigung**: Schritt 3 nutzt nun `$e[2K` (Clear Entire Line) vor dem Zeilenumbruch `
` bei jedem Frame und beim Abschluss (`Installation completed.`), wodurch jegliche Geisterzeichen restlos eliminiert werden.
      - **Vollständige englische Lokalisierung**: Header (`TASKS UPDATE MANAGER`), Schritte [1/5] bis [5/5], Logs und Fehlerboxen (`UPDATE FAILED`, `Error details`, `This window will remain open for troubleshooting`).
      - **Sofortiger Neustart & 5s Auto-Close**: Tasks wird nach Schritt 5 sofort im Hintergrund gestartet; anschließend läuft ein 5-Sekunden-Countdown (`Closing window in Xs... (press any key to exit immediately)`), geschützt gegen `InvalidOperationException` bei nicht-interaktiver stdin.
      - **Fenster-Lifecycle**: `-NoExit` beim Aufruf von `powershell.exe` entfernt; bei Erfolg schließt sich das Terminal nach 5 Sekunden oder Tastendruck automatisch, bei Fehlern hält `Read-Host` das Fenster zur Diagnose offen.
    - **Drüber-Installation & Reparatur**:
      - `update.bat` und `scripts/update_launcher.ps1`: Eigenständiger Launcher im Programmverzeichnis, der auch bei beschädigter oder fehlender `Tasks.exe` das neueste Release via GitHub API abfragt, das Setup herunterlädt und den Update Manager startet.
      - `src/core/agent_cli.py`: Neuer CLI-Befehl `tasks update` (inkl. Aliase `reinstall`, `--force` und `--json`).
      - `scripts/build_exe.py` & `installer/build_installer.py`: `update.bat` und `scripts/update_launcher.ps1` werden automatisiert in `dist/Tasks/` und das Inno Setup Installationspaket übernommen.
    - **Testabdeckung**:
      - `tests/test_update_service.py`: Tests an englische Strings, ANSI-Clear `$e[2K`, Auto-Close Countdown und PowerShell 5.1 Syntax validiert (21/21 Tests bestanden).
      - `tests/test_agent_cli.py`: 4 neue Unittests für `tasks update` / `reinstall` (19/19 Tests bestanden).

- [x] **Kein `explorer.exe`-Kill mehr beim Start aus Desktop-/Startmenü-Verknüpfung (2026-11-02)**:
  - **Problem**: Lief Tasks bereits im System Tray und wurde die App erneut über Desktop- oder Startmenü-Verknüpfung gestartet, flackerte der gesamte Bildschirm und die Taskleiste wurde zurückgesetzt (Windows Explorer Neustart).
  - **Ursache**: Bei Shortcut-Starts ist `os.getppid()` der `explorer.exe`. `_close_current_terminal_window()` beendete den Parent-PID bedingungslos mit `os.kill(..., SIGTERM)` → Desktop-Shell stirbt → Windows startet sie neu.
  - **Lösung & Implementierung**:
    - `main.py`: Neue Hilfsfunktion `_get_process_name(pid)` (`OpenProcess` + `QueryFullProcessImageNameW`) liefert den lowercase-EXE-Namen.
    - `_close_current_terminal_window()` beendet den Parent nur noch bei Whitelist-Treffern (`cmd.exe`, `powershell.exe`, `pwsh.exe`); alle anderen (insb. `explorer.exe`) bleiben unangetastet.
    - `tests/test_terminal_autoclose.py`: Neue Regressionstests `test_close_window_does_not_kill_explorer` und `test_close_window_kills_whitelisted_shell` (4/4 bestanden).
    - `docs/changelog.md` unter `[Unreleased] → Fixed` dokumentiert.

- [x] **Settings Navigation: Rückkehr zu Settings beim Schließen von `NotificationConfigModal` (2026-11-01)**:
  - **Problem**: Klickte man in den Einstellungen (`SettingsModal`) auf `🔔 Notifications` und danach im Dialog auf `↩️ Back` (oder Escape bzw. `💾 Save Settings`), schloss sich der Dialog vollständig, anstatt wie bei den übrigen Einstellungsdialogen (`TrayConfigModal`, `AiExplainModal`, `SchoolConfigModal`) wieder zurück zum `SettingsModal` zu führen.
  - **Lösung & Implementierung**:
    - `src/ui/tui_app.py`: In `action_open_settings()` wurde der Callback `on_notifications_done(saved: bool)` um `self.action_open_settings()` ergänzt.
    - `tests/test_notifications.py`: Neue automatisierte Integrationstests `test_notification_config_modal_back_returns_to_settings` und `test_notification_config_modal_save_returns_to_settings` hinzugefügt (100% bestanden).
    - Dokumentation in `docs/changelog.md` und `docs/current-state.md` nachgeführt.

- [x] **Verlinkten Fachordner direkt aus der Test-Detailansicht öffnen (`ExamDetailModal`) (2026-10-31)**:
  - **Problem**: In der Detailansicht von Tests gab es keine Möglichkeit, mit einem Tastendruck oder Klick direkt in den verknüpften Ordner des jeweiligen Schulfachs im Windows Explorer zu springen.
  - **Lösung & Implementierung**:
    - `src/ui/tui_app.py`:
      - `ExamDetailModal` um den Button `#btn_open_exam_folder` (`📁 Open Folder [F]`, `variant="primary"`) und das Binding `Binding("f", "open_folder", "Open Folder")` erweitert.
      - Methode `action_open_folder()` ermittelt über `DirectoryService.find_matching_directory_for_course(self.exam.subject, self.exam.name)` das verknüpfte Verzeichnis und öffnet es via `DirectoryService.open_directory()`.
      - Fallback: Wenn noch kein Ordner für das Fach hinterlegt ist, wird ein Toast-Hinweis (`No linked folder found for '<subject>'.`) angezeigt.
      - Dialogbreite im Modal-CSS von `82` auf `88` angepasst, damit alle 4 Aktionsbuttons sauber nebeneinander dargestellt werden.
    - `tests/test_untis_exams.py`: Neue Testfälle für das Rendern des Buttons, das Öffnen per Klick und die Taste `f` (inkl. Fallback bei nicht verknüpftem Fach) integriert; alle 18 Tests 100% bestanden.
    - `docs/features.md` und `docs/changelog.md` aktualisiert.

- [x] **Sofortiges Schließen des sekundären Terminals bei Vordergrund-Aktivierung (2026-10-31)**:
  - **Problem**: Wenn Tasks im Hintergrund (System Tray) läuft und in einem neuen Terminal 	asks ausgeführt wurde, wurde Tasks in den Vordergrund geholt, aber das aufrufende Terminal wartete mit einem 10-Sekunden-Countdown („This terminal will close in 10s. Press [ENTER] to cancel...“), bevor es sich schloss.
  - **Lösung & Implementierung**:
    - main.py: Countdown, Tastenabfrage (msvcrt) und Konsolenausgaben in _handle_existing_instance_autoclose() vollständig entfernt.
    - Das sekundäre Terminal schließt sich nun sofort und komplett geräuschlos via _close_current_terminal_window() und sys.exit(0).
    - 	ests/test_terminal_autoclose.py: Unit-Tests auf sofortiges Schließen und absolute Geräuschlosigkeit (leere stdout) aktualisiert (100% bestanden).

- [x] **Inno Setup Installer: Englische Lokalisierung & 3 Finish-Page-Optionen (2026-10-31)**:
  - **Problem**: Der Setup-Wizard war auf Deutsch, bot am Ende nur zwei Optionen ("Globalen Terminal Befehl" und "Tasks Starten"), und Benutzer konnten die Verknüpfungen (Terminal-Profil, Startmenü) auf der Abschlussseite nicht selektiv konfigurieren.
  - **Lösung & Implementierung**:
    - `installer/tasks.iss`:
      - `[Languages]` umgestellt auf `Name: "english"; MessagesFile: "compiler:Default.isl"`.
      - Alle Texte (z. B. Task-Beschreibungen, Icon-Namen, Playwright-Download-Status) einheitlich auf Englisch übersetzt.
      - Neugestaltung der `wpFinished`-Abschlussseite in `[Run]` mit 3 standardmäßig aktivierten Checkboxen:
        1. `Add 'tasks' command to PATH`
        2. `Configure Windows Terminal profile`
        3. `Add Tasks to Start Menu`
      - "Tasks Starten" ("Launch Tasks") vollständig von der Finish-Page entfernt.
      - Startmenü-Verknüpfung wird bei Aktivierung dynamisch über PowerShell `WScript.Shell` angelegt; saubere Deinstallation über `[UninstallDelete]` und `CurUninstallStepChanged` gewährleistet.
    - Setup erfolgreich kompiliert (`installer/dist/Tasks_Setup.exe`, 77.2 MB).

- [x] **PowerShell 5.1 Update-Runner Parser-Fix & Windows Terminal Handshake (2026-10-31)**:
  - **Problem**: Bei Klick auf Update im Reminder-Modal öffnete sich kurz ein zweites Terminalfenster mit roter Fehlermeldung und schloss sich augenblicklich; im Haupt-Terminal erschien `[Verarbeitung des Prozesses mit Code 42 beendet]`.
  - **Ursache**:
    - Windows PowerShell 5.1 liest `.ps1`-Dateien standardmäßig im Windows-1252 ANSI-Zeichensatz, wenn kein UTF-8 BOM vorhanden ist. Dadurch wurden UTF-8 Box-Rahmen (`│`) als `”` (Anführungszeichen) interpretiert, was einen fatalen Parser-Syntaxfehler in Zeile 138 verursachte.
    - Windows Terminal wertet Exit-Codes ungleich 0 (`42`) als Fehler und hält den Tab mit Fehlermeldung offen (`closeOnExit: graceful`).
  - **Lösung & Implementierung**:
    - `src/services/update_service.py`: `update_runner.ps1` wird mit `encoding="utf-8-sig"` geschrieben (garantiert 0 Parser-Fehler in PowerShell 5.1); `-NoExit` verhindert Schließen bei Shell-Fehlern; persistentes Logging aller Schritte in `%TEMP%\Tasks_Update\update.log`.
    - `src/ui/tui_app.py`: Sauberes Beenden mit Exit-Code `0` (schließt den Windows Terminal Tab geräuschlos); Sync-Flag bereinigt, um `"Sync not Complete"` zu verhindern.
    - 21 Unit-Tests in `tests/test_update_service.py` und Volltest (561 Tests) 100% bestanden; Installer neu gebaut (`Tasks_Setup.exe`, 77.2 MB).

- [x] **Windows Terminal Profil Reparatur & Auto-Migration (2026-10-31)**:
  - **Problem**: Nach der Umstellung auf Standalone-Binaries schloss sich das Windows-Terminal-Profil sofort wieder, da noch das veraltete 
un.bat als commandline hinterlegt war und Inno Setup bei Updates das Profil übersprang.
  - **Lösung & Implementierung**:
    - src/services/terminal_profile_service.py: Autarker Python-Service zur Erkennung von Windows-Terminal-Installationen (MSIX / Unpackaged) und atomaren Aktualisierung von settings.json.
    - src/ui/tui_app.py: Asynchroner Hintergrund-Aufruf (TasksSystemIntegrations) bei jedem App-Start repariert veraltete oder fehlerhafte Profile geräuschlos und selbstständig.
    - installer/tasks.iss: Die Bedingung ShouldSetupTerminalProfile schließt Updates (/UPDATE=1) nicht mehr aus, sondern migriert bestehende Profile immer auf Tasks.exe.
    - Sofort-Reparatur des lokalen Profils auf C:\\Users\\xandi\\Desktop\\Tasks\\Tasks.exe.
    - 8 neue automatisierte Unit-Tests in 	ests/test_terminal_profile.py (100% OK).

- [x] **Benutzerfreundliches & modernes Tasks-Update-System (Auto-Sync Toasts, Catppuccin PowerShell Runner, tasks://update Deep-Link) (2026-10-31)**:
  - **Problem**: Das bisherige Update-System funktionierte technisch, war jedoch intransparent: keine automatische Update-Prüfung im Hintergrund mit Toast-Meldung, ungestaltete Eingabeaufforderung die unvermittelt aufging und sich bei Fehlern schlagartig schloss.
  - **Lösung & Implementierung**:
    - **Auto-Sync-Prüfung mit 6h-Throttling**:
      - NotificationEngine.check_update_notification() prüft periodisch in _run_notification_checks und _check_auto_sync auf neuere Releases.
      - Maximal 1 Toast alle 6 Stunden pro Release-Tag (cache/notification_state.json), um Notification-Spam zuverlässig zu verhindern.
      - Native Windows Toast-Benachrichtigung (Tasks Update verfügbar (vX.Y.Z)) mit App-Logo und Deep-Link `tasks://update`.
    - **Isolierter Catppuccin Mocha PowerShell Runner (update_runner.ps1)**:
      - Generiert via generate_powershell_updater_script(...) in `%TEMP%\Tasks_Update\update_runner.ps1`. Da das Skript aus `%TEMP%` läuft, bleibt es vom Überschreiben durch Inno Setup unberührt.
      - Öffnet ein eigenständiges Terminalfenster (CREATE_NEW_CONSOLE) im edlen Catppuccin Mocha Theme (Lavender, Green, Blue, Red, Yellow, Dark Base).
      - Klare 5-Schritt-Anzeige: [1/5] Warten auf Beendigung von Tasks, [2/5] Verifikation des Installers, [3/5] Installation mit animiertem Progress-Spinner, [4/5] Validierung der installierten Binaries, [5/5] Bereinigung und sanfter Neustart von Tasks.exe.
      - Robuste Fehlerdiagnose: Bei unerwarteten Ausnahmen oder Installer-Fehlercodes bleibt das Fenster geöffnet und zeigt den Fehler in Rot an (Read-Host Pause, kein abruptes Schließen).
    - **URI Protocol Dispatching (`tasks://update`)**:
      - Klick auf den Toast öffnet Tasks direkt oder sendet den IPC-Befehl OPEN_UPDATE an die laufende Hintergrundinstanz (SingleInstanceServer), welche das Fenster wiederherstellt und das UpdateReminderModal anzeigt.
      - CLI-Parameter `--open-update` in `main.py` und `run_tui(..., open_update_dialog=True)` in `src/ui/tui_app.py`.
    - **Testsuite**:
      - Umfassende Tests in `tests/test_update_service.py`, `tests/test_notifications.py` und `tests/test_notification_service.py` inkl. Validierung gegen den offiziellen PowerShell-Parser ([System.Management.Automation.Language.Parser]::ParseInput).

- [x] **Nativer Windows-Prozess ("Tasks"), Standalone-Binaries & Batch-Dateien-Bereinigung (2026-10-31)**:
  - **Problem**: Im Windows Task-Manager tauchte die Anwendung lediglich generisch als "Python" oder "Windows-Terminal" auf. Bei der Installation wurden bisher sämtliche rohe `.py`-Dateien und temporäre Batch-Skripte mitkopiert.
  - **Lösung & Implementierung**:
    - **Standalone-Kompilierung (PyInstaller Onedir)**:
      - `tasks.spec` & `scripts/build_exe.py`: Generiert `dist/Tasks/Tasks.exe` (Konsole für TUI/CLI) und `dist/Tasks/TasksTray.exe` (fensterloser Hintergrundprozess).
      - PE-Versionsressourcen (`installer/version_info.txt`, `installer/version_info_tray.txt`) verleihen beiden Executables den Namen "Tasks", Firmenangabe "Alexander Endl" und Repo-Link `https://github.com/X4nd109/Tasks`.
    - **Bereinigung überflüssiger `.bat`-Dateien & Dev Root Sharing**:
      - Gelöscht: `setup.bat` (durch Standalone-Installation überflüssig), `tasks.bat` (redundantes Duplikat zu `tasks.cmd`), `run.bat` (Startskript der alten Python-Installation) und alle `scripts/*.bat`.
      - Als einziges Build-Skript verbleibt `build.bat` zum schnellen lokalen Kompilieren.
      - `tasks.cmd` startet bevorzugt direkt die kompilierte `Tasks.exe` und dient als schlanker Terminal-Runner.
      - Intelligente Dev-Root-Erkennung in `src/core/config.py`: Wenn `Tasks.exe` aus dem Git-Repository gestartet wird, nutzt sie direkt die Daten (`data/`, `cache/`, `config.json`) des Projekt-Roots. Keine doppelten Cache-/Daten-Ordner mehr in `dist/Tasks`.
      - `Tasks.exe` Launcher direkt im Projekt-Root (`scripts/RootLauncher.cs`), sodass Entwickler Tasks per Doppelklick oder Terminal direkt aus dem Root starten können.
    - **Inno Setup Installer (`Tasks_Setup.exe`) & Deinstallation**:
      - Verpackt ausschließlich kompilierte Binaries (`dist/Tasks/*`), Assets, `skills/tasks/SKILL.md` und `tasks.cmd` (Dateigröße ~77.2 MB).
      - Automatische Bereinigung alter `.py`-, `scripts/`- und `.bat`-Dateien bei Updates mit striktem Schutz des Entwicklungs-Repositories (`if not DirExists(AppDir + '\.git')`).
      - Autarke Einrichtung von User-`PATH` und Windows-Terminal-Profil (mit App-Logo und direktem Aufruf von `Tasks.exe`) via Inline-PowerShell, ganz ohne Hilfs-Batchdateien.
      - **Vollständige Deinstallation**: Entfernt bei Uninstall restlos alle Runtime-Dateien (`cache/`, `data/`, `config.json`, `skills/`, `assets/`, `*.log`), reinigt den User-`PATH`, deregistriert das Windows-Terminal-Profil (aller Editionen), entfernt die `tasks://`-Protokoll- & AppUserModelId-Registry-Einträge, löscht den Autostart-Registry-Key (`HKCU\...\Run\Tasks`) sowie eventuelle externe Relikte (`{autoprograms}\Tasks`, `%LOCALAPPDATA%\Tasks`) und entfernt das Anwendungsverzeichnis sauber vom System.

- [x] **Windows Toast Notifications & Neues Benachrichtigungsmenü (`NotificationConfigModal`) (2026-10-31)**:
  - **Problem**: Nach Hintergrund-Syncs oder vor Fristabläufen und Prüfungen gab es keine nativen Windows-Benachrichtigungen; der Nutzer musste die TUI manuell öffnen, um Fälligkeiten zu prüfen.
  - **Lösung & Implementierung**:
    - **Neue Aufgaben (New Assignments)**:
      - Konsolidierte englische Toast-Benachrichtigung (1 Aufgabe: Fach & Titel; mehrere Aufgaben: Gesamtzahl).
      - Klick auf den Toast öffnet/stellt Tasks im Vordergrund wieder her (`tasks://main`).
    - **Fälligkeitswarnungen (Due Reminders)**:
      - Einstellbares Vorlauffenster (`1h`, `2h` [Default], `3h`, `5h`, `1d`, `never`).
      - Klick auf den Toast öffnet direkt die betroffene Aufgabe in `TaskDetailModal` (`tasks://task/<id>`).
    - **Tägliche Prüfungs-Erinnerungen (Exam Reminders)**:
      - Täglicher Toast zur Lern-Erinnerung um konfigurierbare Uhrzeit (Standard: `20:00` Uhr) mit Catch-Up-Garantie bei Standby.
      - Vereinheitlichte Auswahlliste für alle Test-Arten (Tests, Schularbeiten, Wiederholungsprüfungen, mündliche Prüfungen) mit identischen Optionen: Disabled, 1, 2, 3, 4, 5, 7, 10, 14 Tage vorher (individuelle Defaults: SA: 7d, TE: 4d, WDH: 3d, PR: 3d) sowie Haupt-Schalter.
      - Klick auf den Toast öffnet direkt die betroffene Prüfung in `ExamDetailModal` (`tasks://exam/<id>`).
    - **Tasks Logo & Windows Protocol Deep-Linking**:
      - `NotificationService` bindet automatisch das offizielle Tasks-App-Logo (`assets/app_icon.png`) in alle Windows Toasts ein.
      - Nutzt modernes Windows 10/11 `ToastGeneric` Template mit `placement="appLogoOverride"` und `file:///` URI-Schema, wodurch das Logo prominent und gestochen scharf auf der linken Seite des Toasts angezeigt wird.
      - `ensure_tasks_protocol_registered()` registriert das Schema `tasks://` in `HKCU\Software\Classes\tasks` inkl. `DefaultIcon` sowie die AppUserModelId in `HKCU\Software\Classes\AppUserModelId\Tasks`.
      - `main.py --uri` verarbeitet URIs und sendet `OPEN_TASK:<id>` / `OPEN_EXAM:<id>` über den IPC-Server an die laufende Instanz.
    - **TUI Settings Integration (`NotificationConfigModal`)**:
      - Neuer Menüpunkt `🔔 Notifications [9/N]` in `SettingsModal`.
      - Übersichtlicher Konfigurationsdialog mit Toggles, Input (`HH:MM`) und Select-Dropdowns.
    - **Testsuite**:
      - 16 Unittests in `tests/test_notifications.py` und alle Tests der Gesamtsuite zu 100% bestanden.

- [x] **Automatisches Aufgaben-Synchronisationsintervall (Auto-Sync: 5min, 10min, 30min, 1h, never) (2026-10-31)**:
  - **Problem**: Bei minimierter Hintergrundinstanz im System Tray oder bei geöffneter TUI musste die Synchronisation bisher immer manuell angestoßen werden.
  - **Lösung & Implementierung**:
    - **TUI Settings Modal (`TrayConfigModal`)**:
      - Neues `Select`-Widget `#sel_auto_sync` mit Optionen `5 Minutes (5min)`, `10 Minutes (10min)`, `30 Minutes (30min) [Default]`, `1 Hour (1h)` und `Never (Disabled - save resources)`.
      - Wird persistent beim Klick auf `💾 Save Settings` in den Konfigurationsdateien gespeichert.
    - **Konfiguration (`src/core/config.py`)**:
      - `get_auto_sync_interval()`, `set_auto_sync_interval()` mit intelligenter Alias-Normalisierung (`5m`, `10m`, `30m`, `1hour`, `off`, `disabled`, `none`, `0`) und `get_auto_sync_interval_seconds()`.
    - **Foreground TUI Engine (`TasksApp` in `src/ui/tui_app.py`)**:
      - Periodischer Timer (`self.set_interval(20.0, self._check_auto_sync)`), der bei abgelaufener Zeitspanne geräuschlos `self.action_sync_tasks()` anstößt.
      - Aktualisiert nach jedem Sync den Task-Zähler des Tray-Icons (`self._tray_service.update_status(open_cnt)`).
      - Sofortige Neuinitialisierung des Zeitstempels bei Einstellungsänderung im Modal.
    - **Headless Background Process (`_run_tray_background` in `main.py`)**:
      - Verdrahteter `on_sync`-Callback für `TrayService` ("Sync Now").
      - Hintergrundschleife prüft das Intervall und synchronisiert Aufgaben auch im Standalone-Tray-Modus autark.
    - **CLI-Integration (`src/core/agent_cli.py`)**:
      - `tasks tray sync-interval [VALUE]` zum Auslesen und Festlegen des Intervalls (inkl. `--json`).
      - Erweiterte Statusausgabe `tasks tray status` mit `Auto-Sync Interval: <val>`.
    - **Testsuite**:
      - 7 Unittests in `tests/test_auto_sync.py` und alle 530 Tests der Gesamtsuite zu 100% bestanden.

- [x] **System Tray & Autostart Settings Text-Formatting & Zeilenbreite (2026-10-28)**:
  - **Problem**: Im Modal `TrayConfigModal` ("System Tray & Autostart Settings") wurden Texte zuvor künstlich nach wenigen Wörtern umgebrochen, wodurch die rechte Hälfte des Dialogs leer blieb.
  - **Lösung**:
    - Dialogbreite auf `76` optimiert (entspricht Standard-Modals wie `AiConfigModal` und `DownloadLocationModal` mit 70 Spalten Innenbreite).
    - `.tray_cfg_desc` mit `width: 100%; height: auto; margin-bottom: 1;` versehen, damit Multi-Line Rendering und Text-Wrapping in Textual aktiv sind.
    - Sätze pro Zeile verlängert: Jeder Satz nimmt nun elegant und gleichmäßig die volle Zeilenbreite ein (60–67 Zeichen).
    - Veralteten Import von `get_close_button_action` und doppelte `set_autostart`-Aufrufe in `TrayConfigModal` bereinigt.
    - `#tray_config_dialog` im OLED-Theme (`.-theme-oled`) für echten schwarzen Hintergrund registriert.
    - Testsuite `tests/test_tray_tui_integration.py` erfolgreich verifiziert.

- [x] **Terminal-Autoclose mit 10s-Countdown bei laufender Hintergrundinstanz (2026-10-28)**:
  - **Problem**: Wenn Tasks bereits im Hintergrund lief und man in einem neuen Terminal `tasks` eingab, wurde das bestehende Fenster zwar erfolgreich wiederhergestellt, aber das zweite Terminal blieb unnötig offen.
  - **10s Countdown & Interaktiver Abbruch mit [ENTER]**:
    - In `main.py`: `_handle_existing_instance_autoclose(timeout_seconds=10)` gibt bei erfolgreichem `SHOW` folgendes aus:
      ```text
      Restoring window...
      Window succesfully restored.
      This terminal will close in 10s. Press [ENTER] to cancel...
      ```
    - Prüft nicht-blockierend via Windows `msvcrt.kbhit()` und `msvcrt.getwch()`.
    - **Ausschließlich [ENTER]** (`\r` / `\n`) bricht den Countdown ab, gibt `Close cancelled. Terminal remains open.` aus und kehrt sofort zum normalen Terminal-Prompt zurück. Alle anderen Tasten werden ignoriert.
    - Läuft der Countdown ab, schließt `_close_current_terminal_window()` das Terminalfenster (via `WM_CLOSE` für ConHost bzw. SIGTERM der Host-Shell für Windows Terminal Tabs).
  - **Testsuite**: 5 Unittests in `tests/test_terminal_autoclose.py` mit deterministischer Fake-Uhr und Tastatur-Mocks zu 100% bestanden.

- [x] **Klares Beenden-Verhalten: Terminal, Tray & Ctrl+C (2026-10-28)**:
  - **Ctrl+C** (`Binding("ctrl+c", "real_quit", "Force Quit to Terminal")` → `action_real_quit()`): stoppt `SingleInstanceServer` und `TrayService`, beendet Textual via `self.exit()` und kehrt sauber zum Terminal-Prompt zurück, ohne das Terminalfenster zu schließen.
  - **[Q] / [Exit]** (`#btn_main_quit` → `action_quit_app(force=False)`): blendet bei aktivem `minimize_to_tray` weiterhin via `hide_to_tray()` ins System Tray aus (`ShowWindow(hwnd, SW_HIDE)`).
  - **Rotes [X] der Konsole** (`CTRL_CLOSE_EVENT`): stoppt `SingleInstanceServer` und `TrayService`, spawnt keinen Hintergrundprozess und lässt Windows das Fenster und das Tray-Icon vollständig schließen.
  - **Bereinigung**: `src/ui/win_close_dialog.py` und `tests/test_win_close_dialog.py` gelöscht; `TrayConfigModal` enthält nur noch die beiden Umschalter für `Minimize to System Tray` und `Autostart`.
  - **Testsuite**: 77 Unittests für Tray-Service, Single-Instance, Autostart, Notifications, TUI-Integration und Terminal-Autoclose zu 100% bestanden.

- [x] **Windows System Tray Hintergrundprozess, Instant-Start via Window-Hide & Notification Foundation (2026-10-27)**:
  - **Problem**: Der Kaltstart der TUI erforderte bei jedem Neuaufruf den Start des Python-Interpreters und das Laden von Modulen. Beim Schließen mit `[Q]` oder Exit wurde der Prozess komplett beendet. Zudem fehlte eine persistente Plattform für zukünftige Windows-Benachrichtigungen.
  - **Instant Startup via "Hide to Tray" & Exit-Fix**:
    - In `TasksApp`: Wenn `minimize_to_tray` aktiv ist (Standard: `True`), schließt `action_quit_app()` (`[Q]`, `[Ctrl+C]`, Exit-Button `#btn_main_quit`) die TUI nicht, sondern blendet das Konsolenfenster via `ShowWindow(hwnd, SW_HIDE)` unsichtbar in den Hintergrund aus.
    - Klick auf das Tray-Icon oder der erneute Aufruf von `tasks` im Terminal holt das bestehende Fenster via `ShowWindow(hwnd, SW_RESTORE)`, `SetWindowPos` und `SetForegroundWindow(hwnd)` mit `AttachThreadInput` in <50 ms sofort und 100% verlässlich in den Vordergrund.
  - **System-Tray-Service (`src/services/tray_service.py`)**:
    - Basiert auf `pystray` und `Pillow`.
    - Tray-Name `Tasks`; der Tooltip wird via `update_status(open_count)` als `Tasks — X open` aktuell gehalten.
    - Robuster Doppelklick- & Klick-Support: `WM_LBUTTONDBLCLK` (0x0203) und `WM_LBUTTONUP` (0x0202) gepatcht, Debouncing gegen Doppel-Triggern integriert und alle Callbacks gegen Loop-Crashes abgesichert.
    - Kontextmenü: `Open Tasks` (Default/Doppelklick), `Sync Now` (Hintergrund-Synchronisation), Statuszeile `Tasks: X open` (deaktiviertes Label), `Autostart with Windows` (Toggle) und `Quit Tasks`.
  - **Single-Instance IPC & Zero-Overhead Kaltstart (`src/core/single_instance.py`, `main.py`)**:
    - Nutzt eine lokale Windows Named Pipe (`\\.\pipe\Tasks_App_Pipe_<user>`) mit TCP-Fallback.
    - Eingehende Befehle: `SHOW` (Fenster in den Vordergrund holen), `QUIT` (vollständig beenden), `STATUS` (Aufgaben-Anzahl).
    - Sekundäre CLI-Aufrufe (`tasks`) erkennen die laufende Hintergrund-Instanz und beenden sich sofort, anstatt eine zweite konkurrierende TUI zu starten.
    - **Zero-Overhead Kaltstart**: Bei deaktiviertem System Tray (`minimize_to_tray: false`) prüft `main.py` in <0.2ms die JSON-Konfiguration, importiert weder `single_instance` noch `pystray`, und startet ohne jeden Millisekunden-Overhead klassisch direkt. Ebenso startet `tui_app.py` weder SingleInstanceServer noch TrayService.
    - Server-Named-Pipe bleibt über `DisconnectNamedPipe` permanent verbunden, ohne Handles zwischen Abfragen zu zerstören.
  - **Windows Autostart (`src/services/autostart_service.py`)**:
    - Registriert `pythonw.exe main.py --tray` in `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
    - Bevorzugt `pythonw.exe`, sodass beim Windows-Boot kein Konsolenfenster aufpoppt.
  - **Notification Foundation (`src/services/notification_service.py`)**:
    - Modulare Service-Klasse auf Basis von `winotify` für native Windows 10/11 Toast-Benachrichtigungen.
    - Robuste Fehlerkapselung, bereit für zukünftige Reminder- und Sync-Trigger.
  - **TUI Settings Integration (`TrayConfigModal` & `SettingsModal`)**:
    - Neuer Menüpunkt `🖥️ System Tray & Autostart [8/T]` in `SettingsModal`.
    - `TrayConfigModal` mit Toggle-Buttons (`#btn_tray_toggle`, `#btn_auto_toggle`): Feste Beschriftungen `"🖥️ Minimize to System Tray on Close"` und `"🚀 Windows Autostart"` ohne redundanten `": []"`-Text; Aktivierung wird clean und pointer-sicher über die Button-Farbe (Grün = aktiv, Grau = inaktiv) signalisiert.
    - **Sicheres Schließen ins Tray beim Klick auf das rote Fenster-"X"**: Globaler Hook `WH_MOUSE_LL` wurde restlos entfernt (Maus-Cursor bewegt sich wieder zu 100% flüssig und latenzfrei). Beim Klick auf das rote `[X]` fängt `SetConsoleCtrlHandler` (`CTRL_CLOSE_EVENT`) das Schließen ab und spawnt bei aktivem `minimize_to_tray` automatisch einen vollständig losgelösten Hintergrundprozess (`pythonw.exe main.py --tray` mit `DETACHED_PROCESS` und `CREATE_NEW_PROCESS_GROUP`), sodass das Tray-Icon und der Single-Instance-Server nahtlos weiterleben. Bei klassischem ConHost wird `SC_CLOSE` zusätzlich im Systemmenü deaktiviert.
    - Dynamisches Starten/Stoppen: Umschalten von `minimize_to_tray` in den Einstellungen stoppt bzw. startet die Tray- und IPC-Threads sofort im laufenden Betrieb.
    - `SettingsModal` auf 2-spaltiges Layout optimiert: Dialoghöhe von 38 auf 21 Zeilen reduziert, kein Scrollbalken mehr nötig, 100% responsive auf kleinen Terminals.
  - **CLI-Erweiterung (`tasks tray` & `tasks autostart`)**:
    - `tasks tray [status|enable|disable|show|quit] [--json]`
    - `tasks autostart [status|enable|disable] [--json]`
    - `tasks --quit` und `tasks --tray`
  - **Testsuite**: 70 dedizierte Tests in `tests/test_autostart_service.py`, `tests/test_notification_service.py`, `tests/test_single_instance.py`, `tests/test_tray_service.py` und `tests/test_tray_tui_integration.py` mit 100% Erfolg bestanden.

- [x] **AI Agent Skill: Flexibles Zielverzeichnis & Auto-Sync bei Updates (2026-10-27)**:

  - **Problem**: `tasks skill sync` legte den Skill bisher fest in `~/.gemini/config/skills/tasks/` für Antigravity ab. Entwickler, die auch andere KI-Coding-Agenten (wie Claude Code, Codex etc.) nutzen, konnten das Zielverzeichnis nicht flexibel wählen und mussten Pfade manuell konfigurieren.
  - **Explorer-Auswahldialog & Terminal-Prompt**:
    - Vor Öffnen des nativen Windows-Explorer-Dialogs erscheint die englische Eingabeaufforderung:
      `"Please select the directory where you want to install the Tasks skill for your AI agent (e.g. Antigravity, Claude Code, Codex). Press [ENTER] to open the folder picker..."`
    - Nach Drücken von `[ENTER]` öffnet sich der native Ordnerauswahldialog (`pick_directory`).
    - Bricht der Nutzer ab, erfolgt eine saubere Meldung `"Operation cancelled. No folder selected."` ohne Fehler.
    - Bei Auswahl wird der Pfad persistent in `tasks_config.json` unter `"skill_target_dir"` hinterlegt.
  - **1:1 Kopie der Skill-Dateien**: `SKILL.md` und Begleitdateien/Ordner werden direkt in den ausgewählten Zielordner synchronisiert.
  - **Neuer Befehl & Flag zum nachträglichen Ändern**:
    - Unterstützt sowohl Subcommand als auch Flag: `tasks skill set-dir [PATH]` und `tasks skill --set-dir [PATH]`.
    - Ohne Pfadangabe öffnet sich der interaktive Explorer; mit Pfad wird das Verzeichnis direkt gesetzt.
  - **Automatischer Re-Sync nach App-Updates**:
    - In `src/core/task_manager.py` wird bei Versions-Updates (`is_update`) geprüft, ob der Skill bereits früher synchronisiert wurde (`is_skill_synced()`).
    - Falls ja, wird der Skill geräuschlos im Hintergrund via `sync_skill_to_dir` aktualisiert und im Log vermerkt.
  - **Testsuite**: 32 gezielte Tests in `tests/test_agent_cli.py` und `tests/test_skill_auto_sync.py` sowie alle 446 Unittests der Gesamtsuite mit 100% Erfolg bestanden.

- [x] **AI Chat: Clear-Button nach unten verlegt & Bestätigungsdialog (2026-10-27)**:
  - **Problem**: Im AI Chat Menü (`AiChatScreen`) befand sich der Clear-Button in einer separaten Leiste (`#ai_chat_toolbar`) direkt unter dem Aufgaben-Banner und stahl dem Chat-Verlauf 1 bis 2 Zeilen vertikalen Platz. In der unteren Leiste über dem Back-Button gab es ungenutzten Freiraum. Zudem wurde der Chat bisher ohne Rückfrage sofort geleert.
  - **Toolbar entfernt & Platz zurückgewonnen**: `#ai_chat_toolbar` wurde ersatzlos aus `AiChatScreen` und dem CSS entfernt. Die Chat-Nachrichten beginnen nun direkt unter dem Aufgaben-Banner.
  - **Buttons unten bündig gestapelt**:
    - `#ai_input_btn_box` auf `layout: vertical; width: auto; min-width: 11; height: 5; align: right bottom;` umgestellt.
    - Oben: 1-Zeilen Clear-Button (`#btn_ai_clear_chat`, `height: 1`, `margin-bottom: 1`, `width: 100%`, `padding: 0`) mit vollständigem Label `"🗑️ Clear"`.
    - Mitte: 1 Zeile Abstand.
    - Unten: 3-Zeilen Back-Button (`#btn_ai_back`, `height: 3`, `width: 100%`) mit Label `"↩️ Back"`.
    - Box-Breite auf `width: 11;` fixiert, sodass Emoji und Text nebeneinander ohne Abschneiden dargestellt werden.
  - **Sicherheits-Bestätigungsdialog (`ClearChatConfirmModal`)**:
    - Dialog mit Abfrage ("Clear Chat History?", "Are you sure you want to clear the chat history for this assignment?") und Buttons `🗑️ Clear` und `Cancel [ESC]`.
    - Bei `[Ctrl+L]` oder Klick auf `🗑️ Clear` wird erst nach Bestätigung der Chat-Cache geleert, der Explain-Status zurückgesetzt und die Bestätigung angezeigt.
    - Theme-Support für Standard- und OLED-Modus.
  - **Testsuite**: 22 Tests in `tests/test_ai_chat_ui.py` und alle 429 Tests der Gesamtsuite erfolgreich bestanden.

- [x] **Startup-Performance & Lazy Loading (2026-10-26)**:
  - **Problem**: Der Programmstart benötigte vorher ca. 2,0 Sekunden, bedingt durch statische Vorab-Imports schwerer Bibliotheken (`moodle_service`, `teams_service`, `playwright`, `ui.py`), doppelte Initialisierungen und synchrones Cache-Cleanup auf dem Main-Thread.
  - **Direkter TUI-Einstieg (`main.py`)**: Bei Start ohne CLI-Parameter wird die TUI unmittelbar über `from tui_app import run_tui` geöffnet. Dadurch entfällt der Overhead des CLI-Parsers und doppelter Dependency-Checks.
  - **Lazy Imports (`task_manager.py` & `auth.py`)**: `moodle_service` und `teams_service` werden erst geladen, wenn eine echte Synchronisation oder Detailansicht stattfindet. `task_manager`-Importzeit sank von 421 ms auf 22 ms (-95%). `playwright` wird in `auth.py` nur noch bei interaktiven Teams-Logins importiert.
  - **Asynchrones Cleanup & schlankes TUI-Modul (`tui_app.py`, `src/main.py`)**: Synchrones `clean_browser_profile_caches()` aus dem Main-Thread entfernt (wird im Hintergrund-Thread ausgeführt). `import ui` aus `tui_app.py` entfernt und durch `webbrowser.open()` ersetzt. Services (`SchoolbookService`, `DirectoryService`, `check_for_updates`) werden erst beim Aufruf der jeweiligen Dialoge geladen.
  - **Ergebnis & Tests**: Startzeit um ca. 700–900 ms gesenkt (`python main.py --help` von ~1.2s auf 308 ms). Alle 426 Tests der Gesamtsuite mit 100% Erfolg bestanden.

- [x] **Sauberes Beenden bei aktivem Aufgaben-Sync & "Sync not Complete" (2026-10-26)**:
  - **Problem**: Wenn der Nutzer die TUI verlässt während im Hintergrund Aufgaben über Microsoft Teams / Playwright synchronisiert werden, führte das Schließen der Browser-Kontexte zu `TargetClosedError` auf `sys.stderr` sowie verwaisten Asyncio-Warnungen. Bei `Strg + C` warf Textuals `call_from_thread` zudem `RuntimeError: App is not running` in `SyncWorker`.
  - **Globales Shutdown-Signal & Fehlerunterdrückung**: `src/core/config.py` führt `set_shutting_down()` und `is_shutting_down()` ein. In `teams_service.py` und `task_manager.py` brechen Schleifen bei Shutdown sofort ab; TargetClosedErrors werden unterdrückt.
  - **Graceful Thread-Exit & "Sync not Complete"**: `src/ui/tui_app.py` merkt sich den Sync-Thread (`self._sync_thread`), joint ihn beim Exit mit 0.5s Timeout und fängt `RuntimeError: App is not running` in `call_from_thread` sauber ab. Wurde der Sync vorzeitig abgebrochen, wird im Terminal genau einmal der Hinweis `"Sync not Complete"` ausgegeben.
  - **Testsuite**: Vollständig verifiziert über 7 Tests in `tests/test_teams_shutdown.py` und alle 427 Tests der Gesamtsuite.

- [x] **AI-Menü: Back-Button exakt wie im Tests-Menü (Breite & Styling) & 1 Zeile nach unten versetzt (2026-10-26)**:
  - **Exakt gleiche Breite & Beschriftung wie im Tests-Menü (`ExamsScreen`)**:
    - Label vereinheitlicht auf `"↩️ Back"` (identisch zu `#btn_exams_back` mit Emoji-Grafik).
    - `min-width: 12` auf `min-width: 4` reduziert, wodurch der Button mit exakt 9 Zellen Breite (`Region(width=9, height=3)`) genauso kompakt wie der Back-Button im Prüfungsmenü dargestellt wird.
  - **Um 1 Zeile nach unten verschoben**:
    - `#ai_input_btn_box` wurde von `align: right middle;` auf `align: right bottom;` umgestellt.
    - Dadurch rückt der 3-Zeilen hohe Button um genau 1 Zeile tiefer (von `y=35` auf `y=36`), schließt unten bündig mit der Schreibleiste `#ai_chat_input` ab (`y=38`), und seine Textzeile liegt auf der gleichen Zeile wie die untere Zeile des Eingabefeldes.
  - **Clear-Button (`#btn_ai_clear_chat`) mit Label "Clear" & ganz rechts**:
    - Der Button trägt nun das Textlabel `"Clear"` statt des Emojis `🗑️`.
    - Box-Breite automatisch mit Puffer (`min-width: 9; padding: 0 1; margin: 0;`).
    - Toolbar `#ai_chat_toolbar` (`height: 1; align: right middle; padding: 0; margin: 0;`) schließt bündig am rechten Fensterrand direkt unter dem Aufgaben-Banner ab, wodurch der Button stabil ganz rechts in der Ecke sitzt.
  - **Theme-Support**: Sowohl im Standard-Theme als auch im OLED-Theme (`.-theme-oled`) konsistent durchgestylt.
  - **Testsuite**: Vollständig durch automatisierte Unittests in `tests/test_ai_chat_ui.py` (20 Tests) verifiziert.

- [x] **Gezielte Zuweisung des 3-Zeilen-Verhaltens (`ChatInputArea`) & Standard-Felder für alle restlichen Eingaben (2026-10-25)**:
  - **3-Zeilen-Schriftfelder (`ChatInputArea`)**: Bleiben exklusiv aktiv für die dafür prädestinierten Freitextfelder:
    - **AI Chat Menü**: `#ai_chat_input` (mit bündig ausgerichtetem `#btn_ai_back` und Leistenhöhe 7)
    - **Add Task Modal**: `#inp_add_desc` (Aufgaben-Beschreibung)
    - **Add Exam Modal**: `#inp_add_exam_topics` (Prüfungsstoff / Themen)
    - **Exam Detail Modal**: `#inp_exam_topics` (Prüfungsstoff / Notizen)
  - **Dünne Randlinie & 3-Zeilen-Logik**: Saubere 1-Zellen-Randlinie (`border: solid #45475a`, bei Fokus `#89b4fa`; OLED `#343331` bzw. `#58a6ff`) bei Gesamthöhe `height: 5` (1 Zeile Rand oben, 3 Zeilen Textinhalt, 1 Zeile Rand unten), mit vertikalem Zeilensprung (Zeile 1 mittig -> Zeile 2 oben/mitte -> Zeile 3 oben/mitte/unten -> Zeile 4+ Bottom-Scroll mit Scrollbar).
  - **Rückkehr zu Standard-`Input`-Feldern für alle restlichen Felder**:
    - `AddTaskModal`: `inp_add_subject`, `inp_add_title`, `inp_add_due`, `inp_add_time`, `inp_add_teacher`.
    - `AddExamModal`: `inp_add_exam_subject`, `inp_add_exam_date`, `inp_add_exam_time`, `inp_add_exam_teacher`, `inp_add_exam_room`.
    - `SettingsModal`: `inp_cfg_name`, `inp_cfg_class`, `inp_cfg_school`, `inp_cfg_teacher`, `inp_cfg_address`, `inp_cfg_district`.
    - `MoodleLoginModal`: `inp_m_url`, `inp_m_user`.
    - `TeamsSetupModal`: `inp_t_email`, `inp_t_code`.
    - `UntisSetupModal`: `inp_u_school`, `inp_u_user`.
    - `GitSetupModal`: `inp_git_url`, `inp_git_branch`.
    - `Digi4SchoolDownloadModal`: `digi_input_email`, `digi_input_code`.
    - `SchoolbookUrlModal`: `book_input_url`, `book_input_name`.
  - **Testsuite**: Alle Tests in `tests/test_form_inputs_3lines.py` (7 Tests), `tests/test_ai_chat_ui.py` (20 Tests), `tests/test_untis_exams.py` und `tests/test_directories.py` (37 Tests) fehlerfrei bestanden.
  - **100% Textual-Kompatibilität (`Input`-Metaclass & Events)**:
    - `ChatInputArea` besitzt `.value` (Getter/Setter) und postet bei Enter sowohl `ChatInputArea.Submitted` als auch `Input.Submitted`, sowie bei Eingaben `Input.Changed`.
    - Metaklassen-Hook `type(Input).__instancecheck__` und `type(Input).__subclasscheck__` erkennt `ChatInputArea` nahtlos als `Input`, wodurch `query_one(..., Input)` in der gesamten Codebase und allen Tests ohne `WrongType`-Fehler funktioniert.
  - **Testsuite**: Unittest-Suite `tests/test_form_inputs_3lines.py` (7 Tests), `tests/test_ai_chat_ui.py` (20 Tests) und alle Modultests fehlerfrei bestanden.

- [x] **AI-Menü: Konstante 3-Zeilen Schreibleiste, vertikaler Zeilensprung & Back-Button Redesign (2026-10-25)**:
  - **Feste 3-Zeilen-Höhe (`ChatInputArea`)**: Das Eingabefeld startet und verbleibt konstant auf einer Höhe von 3 Zeilen (`height: 3;`).
  - **Vertikaler Zeilensprung & dynamisches Padding**:
    - **1 Zeile (inkl. Platzhalter)**: Cursor und Text starten mittig in der mittleren Zeile (`padding: 1 1 1 1`).
    - **2 Zeilen**: Zeile 1 springt in die obere Zeile, Zeile 2 wird in der mittleren Zeile geschrieben (`padding: 0 1 1 1`).
    - **3 Zeilen**: Zeile 3 wird in der untersten Zeile geschrieben (`padding: 0 1 0 1`).
    - **> 3 Zeilen**: Schreiben verbleibt fix in der untersten Zeile, frühere Zeilen scrollen nach oben weg und die vertikale Scrollbar wird eingeblendet (`show_vertical_scrollbar = True`).
  - **3-Zeilen Back-Button (`#btn_ai_back`)**: Optisch an das Standard-Design der Prüfungsansicht angepasst (`↩ Back`, `height: 3;`, `min-width: 12;`).
  - **Kompakter Clear-Chat-Button (`#btn_ai_clear_chat`)**: Bleibt kompakt bei 1 Zeile Höhe (`🗑️`) und ist im 3-Zeilen-Container unten bündig ausgerichtet (`margin-top: 2;`).
  - **Theme-Unterstützung**: Sowohl im Standard-Theme als auch im OLED-Theme (`.-theme-oled`) konsistent durchgestylt.
  - **Testsuite**: 20 Tests in `tests/test_ai_chat_ui.py` und alle 413 Tests der Gesamtsuite mit 100% Erfolg bestanden.

- [x] **Backspace-Suchmenü (`UnifiedCommandPalette`) Feste 3-Tab-Boxen & Top-Docking (2026-10-25)**:
  - **Oberkante bündig mit Fenster**: `margin-top: 0;` auf `UnifiedCommandPalette > Vertical` und `#--container` gesetzt, sodass die Suchpalette bündig mit der oberen Fensterkante abschließt.
  - **Feste 3 Tab-Boxen nebeneinander**: Drei gleich große Boxen (`width: 18;`, `height: 1;`) mit festen Plätzen: `Courses` (links), `Schoolbooks` (Mitte), `Directories` (rechts) – ohne Positionswechsel.
  - **Farbliche Gestaltung**: Der gerade aktive Tab hat die jeweilige Hintergrundfarbe mit weißer Fettschrift (`Courses` Cyan, `Schoolbooks` Rot, `Directories` Grün). Die beiden inaktiven Tabs sind dezent ausgegraut mit Hover-Highlighting.
  - **Mausklick- & Tastatur-Steuerung**: Umschalten vorwärts mit `Tab` und rückwärts mit `Shift+Tab` sowie Direktumschaltung per Mausklick auf jede der drei Tab-Boxen (inklusive Fokus-Erhalt im Such-Eingabefeld).
  - **Vollständige Testabdeckung**: `test_palette_tabs_layout_and_switch` in `tests/test_directories.py` hinzugefügt; alle 19 Tests in `test_directories.py` und 77 Tests in `test_tui_app.py` fehlerfrei bestanden.

- [x] **Interaktive Spaltensortierung mit Header-Pfeilen, Standard `Due Date ↓` & 1..N Zeilennummerierung (2026-10-25)**:
  - **Automatischer Start mit `Due Date ↓`**: Beim Programmstart wird die Tabelle automatisch nach Fälligkeitsdatum sortiert (nächste Fälligkeit zuerst oben mit Indikator `Due Date ↓`).
  - **Pfeil-Sichtbarkeit für alle Spalten**: Spaltenbreiten wurden so kalkuliert (`Platform` 10, `Subject` 9, `Teacher` 9, `Due Date` 28, `Status` 11), dass der Pfeil auf jeder einzelnen Spalte vollständig sichtbar ist und nicht am Spaltenrand abgeschnitten wird.
  - **Sequenzielle 1..N Zeilennummerierung**: Egal nach welchem Kriterium sortiert wird, die `#`-Spalte zählt immer sauber von `1` oben bis `N` unten durch. Direktauswahl über die Tasten `1`–`9` öffnet die jeweilige Zeile von oben.
  - **2-Wege-Toggle**: Klick auf `Platform`, `Subject`, `Due Date`, `Status` oder `Teacher` schaltet zwischen `↑` und `↓` um.
  - **Column-Specific Hover Highlighting**: Neue Klasse `TasksDataTable` überschreibt `_should_highlight` und `watch_hover_coordinate`, sodass nur sortierbare Spalten-Header beim Überfahren mit der Maus einen Akzent-Hover-Glow (`#tasks_table > .datatable--header-hover`) erhalten.
  - **Testsuite**: Vollständig durch automatisierte Unittests in `tests/test_tui_app.py` abgedeckt (alle 77 Tests bestanden).

- [x] **TUI-Verlassen mit `Strg + C` (`Ctrl+C`) mit Kopier-Schutz in Schriftfeldern (2026-10-25)**:
  - **Globaler Exit-Shortcut mit Eingabefeld-Guard**: In `TasksApp.BINDINGS` wurde `Binding("ctrl+c", "quit_app", "Quit", show=False)` registriert.
  - **Kopieren geschützt**: In `action_quit_app()` wird geprüft, ob aktuell ein Text-/Schriftfeld (`Input`, `TextArea`) fokussiert oder Text markiert ist. In diesem Fall greift der Exit nicht und das reguläre Text-Kopieren bleibt ungestört aktiv.
  - **Button-Tooltip**: Der Exit-Button in der Fußleiste zeigt nun `Exit [Q / Ctrl+C]`.
  - **Unittest**: `test_ctrl_c_quits_app` in `tests/test_tui_app.py` verifiziert das Verhalten.

- [x] **Statusleiste Overhaul: Direkt benachbarte Farb-Badges (Pills), Zentrierung & Bereinigung (2026-10-25)**:
  - **Direkt benachbarte Zentrierung**: Die Status-Badges (`To Do`, `Moodle`, `Teams`, `Manual`, `Next`, `Sync`) liegen ohne künstliche Spaltenbreite direkt aneinander und werden als einheitlicher Block im Terminalfenster horizontal zentriert.
  - **Next-Exam Badge**: Klammern und Datumspräfix entfernt (`Next: [Fach] in [Tage]d`).
  - **Sync-Badge**: Zeigt die exakte Uhrzeit des letzten Syncs an (`Sync: [HH:MM]`).
  - **Vollständige Emoji-Bereinigung**: Alle Icons (`📋`, `🎓`, `👥`, `✏️`, `📝`, `🕒`) wurden entfernt.
  - **Farbige Badges (Pills mit Farbhintergrund)**:
    - `Moodle`: Weißer Text auf Orange (`#fe640b`).
    - `Teams`: Weißer Text auf Blau (`#1e66f5`).
    - `Manual`: Weißer Text auf Grün (`#40a02b`).
    - `To Do`: Dynamisch (Weiß auf Rot bei Überfälligkeit, Schwarz auf Gelb/Amber bei offenen Aufgaben, Weiß auf Grün bei 0).
    - `Next`: Weißer Text auf Violett (`#8839ef`).
    - `Sync`: Heller Text auf Schiefergrau (`#45475a`).
  - **Sync-Spinner**: Bleibt während der Synchronisation wie gewohnt rechts außen angedockt.
  - **100% Abwärtskompatibilität**: Alle Unittests für `#info_stats` und `#info_bar` laufen unverändert fehlerfrei durch.

- [x] **Git Cloud-Sync Setup Tutorial & TUI Integration (2026-10-25)**:
  - **Umfassende englische Anleitung**: `docs/tutorials/git-sync.md` mit detaillierten Abschnitten zur Repository-Erstellung (Private Repository), Erstellung eines Classic Personal Access Tokens (PAT) ohne Ablaufdatum (`No expiration`) mit vollen Rechten (`all scopes`), Token-Kopieren und App-Konfiguration (`🚀 Test & Connect`).
  - **Screenshots reorganisiert**: 8 Screenshots aus `assets/Git Sync Tutorial Screenshots/` nach `assets/git-sync-tutorial/` migriert und nummeriert (`01_create_new_repo.png` bis `08_copy_token.png`).
  - **TUI-Integration (`GitSetupModal`)**: Direkte GitHub-URL (`https://github.com/X4nd109/Tasks/blob/main/docs/tutorials/git-sync.md`) unterhalb der Beschreibung eingefügt (`#git_setup_guide_link`), ohne Präfix und ohne Leerzeile darüber; Dialogbreite auf 76 Zeichen optimiert für sauberes Kopieren der URL im Terminal.
  - **Testsuite & Doku**: Struktur-Test in `tests/test_git_sync.py` aktualisiert, `AGENTS.md`, `docs/features.md`, `docs/changelog.md` und `docs/current-state.md` synchronisiert.

- [x] **Terminal Window Title Capitalization Fix (2026-10-25)**:
  - In `src/ui/tui_app.py` (`adjust_terminal_size_smart`) wurde der gesetzte Fenstertitel von kleingeschriebenem `"tasks"` auf großgeschriebenes `"Tasks"` korrigiert (`SetConsoleTitleW("Tasks")` und `\033]0;Tasks\007`).
  - Batch-Skripte `scripts/setup_command.bat` und `scripts/remove_command.bat` vereinheitlicht.
  - Installer `Tasks_Setup.exe` frisch neu generiert und lokale Testinstallation synchronisiert.

- [x] **Windows Terminal Profile-Skripte: JSON-Schema-Härtung (2026-10-25)**:
  - `setup_terminal_profile.bat` / `remove_terminal_profile.bat`: Schema-Erkennung erfolgt nicht mehr über PowerShell-Truthiness, sondern explizit (`profiles` als Objekt mit `list` vs. Legacy-Array). Ein **leeres** `profiles.list` führte zuvor dazu, dass `profiles` durch ein Array ersetzt und `profiles.defaults` verloren ging.
  - `remove_terminal_profile.bat` schreibt `settings.json` nur noch, wenn tatsächlich ein Profil entfernt wurde (idempotent, keine unnötigen Rewrites).
  - `setup_terminal_profile.bat` gibt bei fehlender/unlesbarer `settings.json` Exit-Code 1 zurück und überspringt im interaktiven Modus die irreführende Erfolgsmeldung.
  - Verifiziert mit Sandbox-`%LOCALAPPDATA%`: modernes Schema, leere Liste mit `defaults`, Legacy-Array, doppelte Ausführung (keine Duplikate), fehlendes Windows Terminal (Setup `1`, Remove `0`).

- [x] **Installer App-Icon Packaging & Terminal-Profile Fix (2026-10-25)**:
  - **Git Whitelist für PNG-Assets**: In `.gitignore` Ausnahmen für `!assets/*.png` und `!assets/**/*.png` hinzugefügt, sodass `assets/app_icon.png` in Git versioniert und bei Clones/Releases mitgeführt wird.
  - **Compile-Time Garantie in Inno Setup (`installer/tasks.iss`)**: `Source: "{#SourceDir}\assets\app_icon.png"` und `.ico` werden nun explizit unter `[Files]` deklariert.
  - **Automatischer Asset-Check & Regeneration (`installer/build_installer.py`)**: `ensure_app_icons()` prüft vor dem Build, ob `app_icon.ico` und `app_icon.png` im Build-Verzeichnis existieren, und stellt sie bei Bedarf automatisch aus Vektor-Fallbacks (`assets/icons/svg_concept8_data_prism.*`) oder via PIL wieder her.
  - **Fallback im Terminal-Setup-Skript (`scripts/setup_terminal_profile.bat`)**: Falls `app_icon.png` nicht existiert, fällt das Skript nahtlos auf `app_icon.ico` zurück.
  - **Installer erfolgreich neu generiert**: `Tasks_Setup.exe` enthält nun garantiert beide Icon-Formate.

- [x] **Project Rebranding: Aufgaben-Detector -> Tasks (2026-10-25)**:
  - **Git Remote & Repository**: Auf `https://github.com/X4nd109/Tasks.git` aktualisiert und `GITHUB_REPO = "X4nd109/Tasks"` in `src/core/config.py` verankert.
  - **Core Refactoring**: Hauptklasse zu `TasksApp` umbenannt (inkl. `AufgabenDetectorApp = TasksApp` Alias für vollständige Abwärtskompatibilität).
  - **Konfiguration & Datenmigration**: Lokale JSON-Dateien zu `tasks_*.json` migriert. Automatische Start-Routine kopiert alte `aufgaben_detector_*.json` verlustfrei und hält Originale als Backup vor.
  - **Git-Sync Automatisierte Legacy-Bereinigung**: Neue Routine `cleanup_legacy_sync_repo_files(work_dir)` in `git_sync_service.py`, die Alt-Dateien (`aufgaben_detector_*.json`) im Remote-Repository einliest, in die Standarddateien integriert und per `git rm -f` automatisch aus dem Sync-Repo löscht und committet.
  - **Packaging & Setup**: Inno-Setup-Skript zu `installer/tasks.iss` migriert (`Tasks_Setup.exe`, Installationsverzeichnis `{autopf}\Tasks`). Batch-Dateien (`tasks.bat`, `tasks.cmd`, `run.bat`, `setup.bat`) und Windows-Terminal-Skripte auf `Tasks` umgestellt.
  - **Dokumentation**: Vollständige Überarbeitung von `AGENTS.md`, `README.md`, allen `docs/*.md`-Dateien und `skills/tasks/SKILL.md`.
  - **Verifikation**: 409 Tests in der Unittest-Suite fehlerfrei bestanden (100% OK), CLI-Befehle `tasks list` und `python main.py list` erfolgreich validiert.

- [x] **Windows Terminal Profile with App Logo (`scripts/setup_terminal_profile.bat` & `scripts/remove_terminal_profile.bat`)**:
  - **Reine, autarke Batch-Dateien**: Beide Skripte führen die JSON-Manipulation von Windows Terminal `settings.json` direkt per PowerShell inline aus (analog zu `setup_command.bat`).
  - Keine redundanten Python-Hilfsskripte mehr nötig (`setup_terminal_profile.py` und `remove_terminal_profile.py` wurden gelöscht).
  - Trägt das Profil `Aufgaben-Detector` mit GUID `{b4e2a1c3-7f8d-4a2e-9b1f-3c5d6e7a8b9c}` und `app_icon.png` ein bzw. entfernt es rückstandslos.
  - Beide Skripte unterstützen `/silent` für das Setup und den Uninstaller.
  - Inno-Setup-Installer frisch neu kompiliert.

- [x] **Single-Execution `Ai Explain` Memory & Chat-Clear Reset (2026-10-25)**:
  - **Persistenter Erklärungs-Status (`cache/ai_chats.json`)**: Neue Liste `_explained_task_ids` speichert pro Aufgabe, ob bereits eine erfolgreiche KI-Erklärung vorliegt.
  - **`is_task_ai_explained(task_id)`** (`src/services/ai_chat_service.py`):
    - Liest den Cache unter `CACHE_LOCK`; leere/fehlende Task-IDs, unbekannte Tasks sowie Tasks ohne Nachrichten liefern `False`.
    - Marker-Treffer in `_explained_task_ids` ⇒ `True`.
    - **Retroaktive Erkennung** für ältere Caches ohne Marker: User-Nachricht mit `is_explain`-Flag bzw. Prompt-Marker (`erkläre mir diese aufgabe` / `explain this assignment`) **und** mindestens eine Assistant-Antwort, die nicht mit `Error:` bzw. `AI request failed:` beginnt.
  - **`set_task_ai_explained(task_id, explained=True)`**: Setzt bzw. entfernt den Marker dedupliziert und schreibt den Cache atomar; bei ungültigem Marker-Typ wird die Liste automatisch repariert.
  - **`AiChatScreen.select_task(..., is_initial=True)`**: Der Auto-Explain-Prompt wird nur noch beim ersten Mal gesendet (`send_user_message(prompt, is_explain=True)`). Ist die Aufgabe bereits erklärt, wird der bestehende Verlauf geladen und `Existing explanation loaded.` als Notification angezeigt (in `try/except` gekapselt).
  - **`AiChatScreen.send_user_message(..., is_explain=False)`**: Markiert die User-Nachricht mit `"is_explain": True` und setzt den persistenten Marker erst im Worker-`update_ui()`, wenn die Antwort nicht mit `Error:` / `AI request failed:` beginnt (Fehler zählen also nicht als erklärt).
  - **Sofortiger Reset beim Chat-Löschen**: `action_clear_chat` ruft zusätzlich `set_task_ai_explained(task_id, False)` auf; `clear_task_chat_cache` entfernt Verlauf **und** Marker, sodass der nächste `Ai Explain [A]`-Klick wieder erklärt.
  - **`cleanup_ai_chats_cache`**: Filtert `_explained_task_ids` auf noch offene/aktive Aufgaben; verwaiste Marker werden ebenfalls entfernt und Unterstrich-Schlüssel (`_last_active_task_id`) bleiben unberührt.
  - **Tests**: 21 neue Service-Tests in `tests/test_ai_chat_service.py` (`TestAiExplainedState`) und 5 neue UI-Tests in `tests/test_ai_chat_ui.py` (`TestAiExplainSingleExecution`) – inkl. Fehlerantworten, retroaktiver Erkennung, Clear-Reset, Cleanup und synchron ausgeführter Worker-Threads.

- [x] **Desktop Shortcut & Installer Icons (`assets/app_icon.ico` & Inno Setup)**:
  - 8 handgefertigte **SVG-Vektor-Icons** mit Fluent-Squircle, transparenten Alpha-Ecken und leuchtenden Gradienten entworfen.
  - **Quantum Prism Convergence (`svg_concept8_data_prism`)** verfeinert: 120°-Tri-Radial-Symmetrie mit 3 Strahlen (Teams nach links oben, Moodle nach rechts oben, WebUntis-Uhr-Icon im zentrierten App-Tile exakt in Moodle-Größe gerade nach unten), echten Logos an den Ecken, zentralem Kristallprisma und entfernter 4. Emissionslinie/Häkchen.
  - Das verfeinerte Quantum-Prism-Icon wurde als Standard-Icon `assets/app_icon.ico` eingerichtet.
  - `installer/aufgaben_detector.iss` um `SetupIconFile` und `IconFilename: "{app}\assets\app_icon.ico"` für Desktop- & Startmenü-Verknüpfungen ergänzt.
  - Installer-Build erfolgreich getestet (`AufgabenDetector_Setup.exe` trägt das neue Vektor-Icon).

- [x] **AI Explain Single-Execution Memory & Chat Clear Reset**:
  - **Dauerhafte Deduplizierung (`is_task_ai_explained`, `set_task_ai_explained`)**:
    - Klickt der Nutzer in `TaskDetailModal` auf `🤖 Ai Explain [A]`, merkt sich das System per `_explained_task_ids` in `cache/ai_chats.json`, dass die Aufgabe bereits erklärt wurde.
    - Beim erneuten Klick auf `Ai Explain [A]` wird die Erklärung nicht nochmals doppelt an die KI geschickt, sondern der bestehende Chat direkt geöffnet und mit `ℹ️ Existing explanation loaded.` bestätigt.
  - **Reset beim Chat-Leeren**:
    - Klick auf `🗑️` (Clear Chat) oder `Ctrl+L` leert den Chat und setzt den Erklärungsstatus der Aufgabe zurück (`clear_task_chat_cache` & `set_task_ai_explained(task_id, False)`), sodass erneutes `Ai Explain [A]` wieder eine neue Erklärung triggert.
  - **Fehler-Resilienz & Abwärtskompatibilität**:
    - Tritt ein Fehler auf (z. B. fehlender API-Key oder Netzwerkabbruch), wird die Aufgabe nicht fälschlich als erklärt markiert.
    - Vorherige Chatverläufe mit Erklärungs-Prompts werden rückwirkend erkannt.
    - `cleanup_ai_chats_cache` entfernt verwaiste IDs abgeschlossener Aufgaben automatisch aus `_explained_task_ids`.
  - **Umfassende Testabdeckung**: 104 AI-Tests erfolgreich (alle 407 Tests im Gesamtprojekt grün).

- [x] **In-App AI Chat Assistant & Browser-Style Task Tabs (`AiChatScreen` & `AiConfigModal`)**:
  - **Interaktiver Vollbild-Assistent (`AiChatScreen`)**:
    - Schlanke obere Tableiste (`#ai_tab_scroll`) mit robuster Befüllung aller gefilterten Aufgaben aus dem Task-Manager.
    - **Filter-Synchronisation mit Hauptmenü**: Die im AI-Menü angezeigten Aufgaben-Tabs spiegeln exakt die im Hauptmenü aktiven Filter (Status, Zeitrahmen, Schulfach, Plattform) wider.
    - Saubere Kursanzeige & Dynamische Tabs: Inaktive Tabs zeigen direkt das Schulfach ohne Klammern (z. B. `SESD`, `SWP`, `AMEC`), der ausgewählte Tab expandiert flüssig auf `<Fach>: <Titel>` mit dynamischem Layout-Refresh (`refresh(layout=True)`).
    - **Kompakte 1-Zeilen-Tabs mit Vollfarb-Aktivierung**:
      - Aufgaben-Buttons sind nun exakt **1 Zeile hoch** (`height: 1`), wodurch kein ungenutzter Freiraum über oder unter dem Text entsteht.
      - Der ausgewählte Tab wird vollständig vollflächig farbig hervorgehoben (`background: #89b4fa; color: #11111b;` im Standard-Theme bzw. `#205ea6; color: #ffffff;` im OLED-Theme), statt nur durch einen Randstrich markiert zu werden.
      - Inaktive Tabs verbleiben in dezentem, dunklem Hintergrund (`#1e1e2e` bzw. `#181816`).
      - Auch `#ai_top_bar`, `#ai_tab_scroll` und `#btn_ai_clear_chat` wurden nahtlos auf `height: 1` angepasst.
    - 100% Modulare & Schulfreie KI-Persona: Hardcoded Schulnamen (`Spengergasse`) vollständig aus `_persona()` in `src/services/ai_chat_service.py` entfernt. Die KI agiert universell als neutraler Lernassistent für jede Schule, Universität oder Weiterbildung.
    - **Reines Aufgaben-Banner ohne Fach-Präfix**: In der Informationszeile unterhalb der Tabs wird nun ausschließlich der exakte Aufgabentitel angezeigt (z. B. `OverTheWire/Bandit_0-6_Linux:...` statt `SESD: OverTheWire/...`), da das Fach bereits in den Tabs präsent ist.
    - **Intelligente, dynamische Prompt-Eingabezeile (`ChatInputArea`)**:
      - `Send`-Button entfernt: Prompts werden nun direkt und intuitiv mit `Enter` abgesendet; die Eingabeleiste nutzt die gesamte verfügbare Breite.
      - **Zuverlässiges `Shift + Enter` für mehrzeilige Prompts**:
        - Unterstützung für `shift+enter`, `shift+return`, `ctrl+j`, `ctrl+enter`, `alt+enter` und `shift+linefeed`.
        - **Hardware-Level Win32-Fallback (`is_shift_pressed_win32`)**: Falls Terminal-Emulatoren (z. B. Standard Windows Console / conhost) bei gedrücktem Shift nur einfache `Enter`-Tastencodes senden, prüft der Eingabebereich über `GetAsyncKeyState(VK_SHIFT)` den physischen Zustand und fügt zuverlässig einen Zeilenumbruch ein (`self.insert("\n")`), ohne den Prompt versehentlich abzusenden.
        - Ergänzung in `patch_win32_event_monitor` zur Erzeugung von `\x1b[13;2u` bei Shift+Enter auf Windows-Treiber-Ebene.
      - **Symmetrische Rahmentrennung & Höhenverschiebung (`#ai_input_bar`)**:
        - Über und unter der Schreibleiste befinden sich nun identische Trennlinien (`border-top: solid #313244;` und `border-bottom: solid #313244;` bzw. `#343331` im OLED-Theme).
        - Die Eingabeleiste ist dadurch leicht nach oben versetzt und schließt nach unten mit einer sauberen horizontalen Kontur ab.
      - **Kompakter Clear-Button links neben dem Back-Button (`#btn_ai_clear_chat`)**:
        - Aus der oberen Tableiste (`#ai_top_bar`) entfernt, wodurch die Aufgaben-Tabs über die volle Breite ungestört scrollen können.
        - Platziert direkt links neben dem Back-Button im horizontalen Container `#ai_input_btn_box`.
        - Beschriftung auf das Emoji `🗑️` gestrafft (ohne Text "Clear") mit exakt symmetrischer 4-Zellen-Breite (`width: 4; min-width: 4; padding: 0;`), sodass links genau 1 Zeichen Abstand, in der Mitte das 2-Zellen-Emoji und rechts genau 1 Zeichen Abstand gerendert wird.
        - **Satter, echter Rotton**: Kräftiges, sattes Rot (`background: #e03131; color: #ffffff;` mit Hover `#c92a2a;`) sowohl im Standard- als auch im OLED-Theme für maximale Signalwirkung statt blasser oder pastellener Töne.
      - **Fest verankerter Button-Bereich (`#ai_input_btn_box`)**:
        - `#btn_ai_clear_chat` und `#btn_ai_back` sind zusammen in einem dedizierten Container (`Horizontal(id="ai_input_btn_box")`) mit `height: 100%; align: right bottom;` fixiert.
        - Wächst das Schreibfeld beim Verfassen längerer, mehrzeiliger Prompts von 1 auf 2 oder 3 Zeilen nach oben, verbleiben beide Buttons unverrückbar nebeneinander rechts unten auf der untersten Zeile.
      - Auto-Expand nach oben (1–3 Zeilen): Die Eingabeleiste wächst beim Tippen längerer Texte dynamisch von 1 auf bis zu 3 Zeilen nach oben.
      - Scrollbar ab Zeile 4: Bei noch längeren Texten blendet sich eine elegante, schlanke Scrollbar ein (`scrollbar-size: 1 1`).
      - Automatisches Zurückfedern: Nach dem Absenden schrumpft das Eingabefeld sofort wieder auf 1 Zeile zurück.
    - Symmetrisches Aufgaben-Banner: Banner mit oberer und unterer Trennlinie (`border-top` und `border-bottom`) eingefasst, sodass der Text absolut mittig zentriert wirkt.
    - Automatischer Start bei Aufgabe 1: Klick auf `[🤖 Ai]` im Hauptmenü öffnet direkt die 1. Aufgabe samt Chatverlauf bzw. Startanzeige, ohne leeren Platzhalter.
    - Fehlerfreie Chat-Persistenz: Bereinigung in `_populate_table` korrigiert (`getattr(self.mgr, 'tasks', [])`), sodass gespeicherte Chats für offene Aufgaben beim Verlassen des AI-Screens nicht mehr versehentlich gelöscht werden.
    - Minimalistischer Chatverlauf: Redundante Absenderzeilen (`🧑 You` / `🤖 AI (...)`) entfernt; Nachrichten werden clean und übersichtlich direkt durch den farbigen Seitenstrich (User grün, Assistant blau) visualisiert.
    - Vollbild-Optimierung: Unnötige Header-Leiste ("TASKS — School Assignment Hub" + Uhrzeit) komplett entfernt, um den vollen vertikalen Platz für den Chat bereitzustellen.
    - Höhen- und Layout-Perfektion: Natürlicher vertikaler Fluss für Tableiste (`height: 3`) und Banner (`height: 3`) sowie `dock: bottom; height: 4` für die Eingabeleiste verhindern jegliches Überlappen oder Abschneiden von Tabs, Clear-Button, Eingabefeld oder `Send`/`Back`-Buttons.
    - Perfekt zentrierte Button-Labels (`content-align: center middle`) und saubere Platzhalter ohne störenden Klammerzusatz.
    - Chat-Verlauf mit formatierten User- und Assistant-Nachrichten (`VerticalScroll`), Denk-Indikator während der KI-Anfrage und Eingabezeile mit direktem `Enter`-zum-Senden.
    - **Rich Markdown & Code-Block Rendering**: Assistant-Antworten werden über das Textual-`Markdown`-Widget gerendert (User-Nachrichten bleiben `Static`), inklusive eigener Styles für Fenced Code Blocks (`MarkdownFence`) und Inline-Code (`MarkdownCodeInline`) im Standard- und OLED-Theme.
    - **Animierte Denk-Anzeige (`Thinking.` $\rightarrow$ `Thinking..` $\rightarrow$ `Thinking...`)**:
      - Ersetzt die alte statische Box durch eine cleane, emoji-freie Textanzeige ohne störenden Text-Overhead.
      - 3-stufiger Textual-Timer (`self.set_interval(2.0 / 3.0, ...)`), der zyklisch zwischen 1, 2 und 3 Punkten wechselt (exakt 2,0 Sekunden pro voller Durchlauf).
      - Automatische Bereinigung und Stoppen des Timers beim Eintreffen der KI-Antwort, bei Screen-Dismiss (`action_dismiss_screen`) oder Unmount (`on_unmount`).
    - **Vollständige Multi-Theme-Unterstützung (alle 22 Themes)**:
      - Umstellung aller hardcodierten Catppuccin-Hexwerte in `AiChatScreen.DEFAULT_CSS` auf Textuals semantische Design-Variablen (`$background`, `$surface`, `$panel`, `$primary`, `$border`, `$text`, `$text-muted`, `$warning`, `$success`, `$error`).
      - Das gesamte AI-Menü (Tableiste, aktiver Tab, Banner, Chat-Bubbles, Code-Blöcke, Eingabebereich, Buttons und Platzhalter) passt sich sofort und automatisch jedem gewählten Theme (Catppuccin, Dracula, Tokyo Night, Nord, Gruvbox, Rosé Pine, Solarized Light, Textual Light/Dark etc.) an.
      - Beibehaltung und Verfeinerung dedizierter `.-theme-oled` Overrides für tiefschwarze `#000000`-Hintergründe und akzentuierte Ränder.
    - Dedizierter `🗑️ Clear Chat` Button pro Aufgaben-Tab zur manuellen Rücksetzung des Verlaufs.
  - **Deep Task Context & System Prompt**:
    - Automatischer Hintergrund-Download von Aufgaben-Dateien und Textextraktion aus PDFs (`fitz` / PyMuPDF) und Quellcode/Textdateien in den System-Prompt.
    - Die KI besitzt das komplette Wissen über Aufgabenstellung, Kriterien, Lehrer und Dateiinhalte.
  - **Cache-Persistenz & Automatische Bereinigung**:
    - Speicherung in `cache/ai_chats.json` bleibt während der Arbeit erhalten.
    - Sobald eine Aufgabe als abgeschlossen markiert wird oder nicht mehr offen/überfällig ist, wird ihr Chatverlauf automatisch aus dem Cache gelöscht (`cleanup_ai_chats_cache`).
  - **Nahtlose `Ai Explain` Weiterleitung**:
    - Klick auf `🤖 Ai Explain [A]` in der Aufgaben-Detailansicht schließt den Dialog, öffnet sofort `AiChatScreen` mit dem aktiven Tab der Aufgabe und versendet automatisch den Erklärungs-Prompt.
  - **Automatisierte & Vereinfachte Settings-Konfiguration (`AiConfigModal`)**:
    - Automatisches Laden der Modelle (`_fetch_models`): Sobald der Benutzer einen API-Key einfügt oder eingibt, wird die Modellliste unmittelbar und ohne manuellen Klick aktualisiert.
    - Prepayment-Hinweis & Fehlerbehandlung: Klare Diagnose und Handlungsanleitung, falls ein Google-Cloud-Key versehentlich an ein Projekt mit Billing gebunden ist, anstatt das kostenlose Google AI Studio Free-Tier zu nutzen.
    - Verbindungstest-Button `🔌 Test Connection` in voller Button-Höhe (`height: 3`) ohne vertikales Abschneiden.
    - Sprache umschaltbar (DE/EN) und automatische Provider-Erkennung (Google Gemini vs. OpenAI).
  - **Hauptmenü & Tastenkürzel**:
    - Neuer Button `[🤖 Ai]` in der Menüleiste neben Tests (`btn_main_ai`) mit Tastaturkürzel `[I]`.
  - **Intelligente Tab-Wiederherstellung (Zuletzt geöffnete Aufgabe)**:
    - Beim Öffnen des AI-Assistenten wird automatisch die Aufgabe geöffnet, die zuletzt aktiv war (`_last_opened_task_id` und `load_last_active_ai_task_id()`).
    - War noch nie eine Aufgabe geöffnet oder ist die zuletzt aktive Aufgabe nicht mehr in der Liste (z. B. erledigt oder weggefiltert), wird automatisch die erste offene Aufgabe (Index 0) als Fallback gewählt.
    - Gezielte Aufrufe (z. B. via `Ai Explain [A]`) überschreiben das Verhalten weiterhin priorisiert.
  - **Lesefreundliches Scrollen bei KI-Antworten (Start von oben)**:
    - Bei Eintreffen einer Antwort der KI wird das Chatfenster nicht mehr an das absolute Ende (Zeile 50) gescrollt.
    - Stattdessen wird die neue Assistant-Nachricht mit `last_assistant_bubble.scroll_visible(top=True, animate=False)` via `call_after_refresh` exakt an die Oberkante des Fensters ausgerichtet, sodass der Benutzer die Antwort sofort von der ersten Zeile an lesen kann.
  - **Umfassende Testabdeckung**: 104 dedizierte AI-Tests (71 in `test_ai_chat_service.py`, 13 in `test_ai_explain.py`, 20 in `test_ai_chat_ui.py`), Gesamtsuite erfolgreich.

- [x] **AI Chat Service Foundation (`src/services/ai_chat_service.py`)**:
  - **Attachment Text Extraction (`extract_attachment_text`)**: PDFs via PyMuPDF (`fitz.open`, whitespace-cleaned, capped at `max_chars`), text/source formats (`.txt`, `.md`, `.py`, `.c`, `.cpp`, `.java`, `.html`, `.css`, `.json`, `.csv`, `.xml`) with UTF-8/latin-1 fallback, binary placeholder `[Binary file: <name>]`, and graceful error notes for unreadable files.
  - **Task Context Builder (`build_task_ai_context`)**: German/English HTL-Spengergasse persona plus subject, title, due date, teacher, status, description, extracted local attachment contents (`--- Datei: ... ---`) or attachment name list, and closing answer instructions.
  - **Provider Dispatcher (`send_ai_chat_message`)**: Google Gemini (`generateContent`, `gemini-2.0-flash` default, `system_instruction` + user/model role mapping) and OpenAI-compatible (`/chat/completions`, system message, Bearer auth, configurable `base_url`/model). Errors are cleaned into `Error: ...` strings; missing API key returns the Settings hint.
  - **Connection Probe (`test_ai_connection`)**: Sends `"Hi, reply with OK"` and reports `(True, "Connection successful! Model responded.")` or `(False, <error>)`.
  - **Chat Cache (`cache/ai_chats.json`)**: `load_task_chat_cache`, `save_task_chat_cache`, `clear_task_chat_cache`, and `cleanup_ai_chats_cache(active_open_task_ids)` (atomic writes, RLock, corrupted-file tolerance).
  - **Tests**: 50 new unit tests in `tests/test_ai_chat_service.py` (mocked `requests.post` and `fitz`; no live network calls).

- [x] **Filter Menu Scrollbar & TUI Startup Speed Optimization**:
  - **Scrollbares Filter-Menü (`FilterMenuModal`)**:
    - Umstellung des `#filter_dialog` Containers von `Vertical` auf `VerticalScroll(id="filter_dialog")`.
    - CSS-Anpassung mit `overflow-y: auto;` und `scrollbar-gutter: stable;` für zuverlässiges Scrollen auf kleinen Bildschirmen (z. B. 80x20 Terminals) ohne abgeschnittene Buttons.
  - **Startbeschleunigung (~40% schneller, ca. 800 ms Ersparnis)**:
    - Lazy Loading für schwere Bibliotheken: `excuse_service` (`fpdf2`), `digi4school_service` (`fitz`/`PyMuPDF`, `PIL`, `pytesseract`) und `auth` (`playwright`, `requests`) in `src/ui/tui_app.py` und `src/main.py`.
    - Asynchroner Daemon-Thread für `clean_browser_profile_caches()`, sodass der synchrone Festplattenscan vor dem Öffnen der TUI entfällt.
    - Vollständige Verifikation: 316 Unit-Tests erfolgreich (100%), Kaltstartzeit von 1,88s auf 1,12s gesenkt.

- [x] **Release v1.3.0 — Smart Download Auto-Dir & Agent Cleanup**:
  - **Download Auto-Directory Modal (`DownloadLocationModal`)**:
    - Neues, vollständig auf Englisch gehaltenes Auswahldialog-Modal beim Klick auf `📥 Download [D]`.
    - Direkte Hotkeys: `[1]` (Auto-Dir), `[2]` (Manual), `[3]` (Standard Downloads), `[ESC]` (Cancel).
    - `[1] Linked Course Folder`: Automatische Erkennung via `DirectoryService.find_matching_directory_for_course()`. Erstellt einen Unterordner mit dem Aufgabennamen im verknüpften Kursverzeichnis (`<Matched_Path>/<Aufgabentitel>/`) und speichert dort alle Dateien ab. Falls kein Ordner für das Fach verknüpft ist: Button deaktiviert (`disabled=True`) mit gelbem Hinweis `⚠️ No linked folder for '<Fach>' [1]`.
    - `[2] Choose Folder Manually...`: Öffnet wie gewohnt den nativen Windows Explorer Folder Picker (`pick_directory`).
    - `[3] Standard Downloads Folder`: Speichert direkt unter `%USERPROFILE%\Downloads\<Fach> - <Aufgabe>\`.
  - **Headless CLI Erweiterung (`tasks download --auto-dir`)**:
    - Neuer Flag `--auto-dir` (`-a`) für `tasks download <id>`.
    - Ermittelt automatisch den verknüpften Ordner und legt den Aufgaben-Unterordner an; klare Fehlermeldung/JSON falls kein Ordner verknüpft ist.
  - **Vollständige Bereinigung des alten Agent-Harnesses**:
    - Entfernung des Buttons `🤖 Agent [G]` (`btn_det_agent`) und des Handlers `action_agent_open`.
    - Entfernung von `AiAgentConfigModal` und `AiConfigChoiceModal`.
    - Settings-Button `🤖 AI Explain Config` (`btn_set_ai_explain`, Shortcut `[7]`/`[A]`) führt direkt zu `AiExplainModal`.
    - Entfernung des CLI-Subcommands `tasks agent` und Löschung von `src/services/ai_agent_service.py`.
    - Neuer Unit-Test-Suite `tests/test_download_auto_dir.py` (7 Tests bestanden, Gesamtsuite 316 Tests).

- [x] **Release v1.2.1 — Global 'tasks' Agent-Skill & 'tasks skill sync' CLI-Befehl**:
  - **Schlanker, token-effizienter Skill (`skills/tasks/SKILL.md`)**:
    - Optimiert für manuelle Aktivierung über Slash-Command `/tasks` (kein unaufgeforderter Prompt-Overhead).
    - Schnelle <0.1s Cache-Abfragen mit deterministischer JSON-Struktur (`--json`) für alle Agentic Coding Tools (Antigravity, Claude Code, Cursor).
    - Dokumentiert die Kernbefehle: `tasks list`, `tasks show`, `tasks download`, `tasks done`, `tasks books`, `tasks dirs`, `tasks open`, `tasks sync`.
  - **Integrierter Sync- & Status-Befehl (`tasks skill [sync|status]`)**:
    - `tasks skill sync [--target <pfad>] [--json]`: Installiert oder aktualisiert den Skill direkt in Antigravitys globales Skill-Verzeichnis (`~/.gemini/config/skills/tasks/SKILL.md`).
    - `tasks skill status [--json]`: Prüft den Installationsstatus und ob die globale Version mit dem Repository synchron ist.
    - Flag-Aliase: `-skill`, `--skill`.
  - **Packaging & Tests**:
    - `skills/` Verzeichnis in `installer/build_installer.py` aufgenommen.
    - Vollständige Testabdeckung in `tests/test_agent_cli.py` (318 Tests in der Gesamtsuite erfolgreich).

- [x] **Release v1.2.0 — AI Explain, Agentic Coding Tool Integration & Desktop App Linking**:
  - **'Ai Explain' Button & Workflows (`TaskDetailModal`, `AiExplainModal`, `open_ai_explain`)**:
    - Strukturierte Prompts auf Deutsch oder Englisch mit allen Aufgabenmetadaten und Dateianhängen.
    - Automatisches Multi-Level Kopieren in die Windows-Zwischenablage (`pyperclip` + `ctypes` Fallback).
    - Browser-Link mit dynamischer Query-Param-Ersetzung (`{prompt}`) oder direktem Einfügen.
    - Vordefiniertes Preset `Desktop App` zum Starten lokaler KI-Anwendungen (`.exe`) via nativem Windows Dateidialog (`pick_file`).
    - Scrollbarer Dialog (`VerticalScroll`) mit `scrollbar-gutter: stable` und `max-height: 85%` gegen Button-Clipping.
    - Vollständige englische Lokalisierung der Benutzeroberfläche und Einstellungsdialoge.
  - **'Agent' Button & Agentic Coding Tool Workflow (`TaskDetailModal`, `AiAgentConfigModal`)**:
    - 1-Klick-Workflow lädt Aufgaben-Dateien & `angabe.md` in frei wählbaren Ordner via Windows Folder Picker herunter.
    - Kopiert automatisch den absoluten Projektpfad in die Windows-Zwischenablage (`Strg+V` im Coding Tool).
    - Startet das konfigurierte Agentic Coding Tool (Antigravity, Cursor, VS Code etc.) als unabhängigen Hintergrundprozess.
  - **Zentralisiertes 'AI Configuration' Einstellungsmenü (`AiConfigChoiceModal` & `AiAgentConfigModal`)**:
    - Zusammenfassung von AI Explain und AI Agent unter `🤖 AI Configuration` (Shortcut `[7]` / `[A]`).
    - Modale Verwaltung der Executable mit Explorer-Auswahl und Zurücksetzen-Funktion.
  - **Headless Agent CLI Subcommands (`tasks explain`, `tasks agent`)**:
    - Direkte Terminal- und JSON-Schnittstelle für autonome Agenten und Skripte.
  - 23 neue automatisierte Unit-Tests (Gesamtsuite: 317 Tests, 100 % Erfolgsquote).

- [x] **Feature: 'Agent' Button & 'AI Configuration' Hub (TUI & Headless CLI)**:
  - **Interaktiver 'Agent'-Button (`TaskDetailModal`)**:
    - Neuer Button `#btn_det_agent` (`🤖 Agent [G]`) in der Aufgaben-Detailansicht mit Shortcut `[G]`.
    - Öffnet den Windows-Folder-Picker (`pick_directory`), sodass der Benutzer sein gewünschtes Projektverzeichnis frei wählen kann.
    - Lädt alle Anhänge und die formatierte Aufgabenstellung (`angabe.md`) direkt in den Zielordner herunter.
    - Kopiert automatisch den absoluten Projektpfad in die Windows-Zwischenablage (`Strg+V` im Coding Tool).
    - Startet das konfigurierte Agentic Coding Tool als eigenständigen Hintergrundprozess (ohne erzwungene Projekt-Neuerstellung).
    - Falls kein Tool hinterlegt ist, erscheint eine In-App Notification mit Hinweis auf die Settings.
  - **Zentrales Einstellungs-Hub `AI Configuration` (`SettingsModal`, `AiConfigChoiceModal`, `AiAgentConfigModal`)**:
    - Zusammenführung von 'AI Explain' und 'AI Agent' unter `🤖 AI Configuration` (Shortcut `[7]` / `[A]`).
    - `AiConfigChoiceModal`: Übersichtliches Menü zur Verzweigung in Explain- oder Agent-Einstellungen.
    - `AiAgentConfigModal`: Anzeige der konfigurierten Tool-Executable, Durchsuchen per Windows Datei-Explorer (`pick_file`) und Reset-Funktion.
    - Persistente Speicherung in `config.json` unter `agent_coding_tool_path`.
  - **Headless Agent CLI (`tasks agent`)**:
    - `tasks agent <id|index> [--dir <pfad>] [--no-launch] [--json]`.
  - 9 neue automatisierte Unit-Tests in `tests/test_agent_feature.py` (Gesamtsuite: 315 bestandene Tests mit 100 % Erfolgsquote).

- [x] **Feature: 'Ai Explain' Integration (TUI & Headless CLI)**:
  - **Interaktiver Button in der Detailansicht (`TaskDetailModal`)**:
    - Neuer Button `#btn_det_ai_explain` (`🤖 Ai Explain [A]`) neben Download [D] / Mark as Open [E].
    - Shortcut `[A]` löst die Erklärung direkt per Tastatur aus.
    - Funktioniert nahtlos für alle Aufgabenarten (Moodle, Teams und manuell erstellte Aufgaben).
  - **Automatischer KI-Prompt mit Metadaten & Dateiliste (`build_ai_explain_prompt`)**:
    - Strukturierter Aufbau mit Aufgabenstellung, Fach, Titel, Fälligkeit, Lehrkraft, Beschreibung und Angabe-Details.
    - Listet alle dazugehörigen Dateianhänge auf, damit die KI über alle Aufgabendokumente im Bilde ist.
    - Umschaltbar auf Deutsch ("Erkläre mir folgende Schulaufgabe...") oder Englisch ("Please explain the following school assignment...").
  - **Multi-Level Clipboard-Integration (`copy_to_clipboard`)**:
    - Legt den generierten Prompt sofort in die Windows-Zwischenablage (pyperclip mit ctypes user32/kernel32 und clip.exe Fallback).
  - **Browser-Integration & URL-Templates (`open_ai_explain`)**:
    - Unterstützt direkte Query-Param-Übergabe via `{prompt}` (z. B. ChatGPT oder Perplexity).
    - Unterstützt Direktlinks (z. B. Google Gemini, wo einfaches `Strg+V` im geöffneten Chatfenster genügt).
  - **Konfigurations-Modal in den Einstellungen (`AiExplainModal` / `SettingsModal`)**:
    - Neuer Menüpunkt `#btn_set_ai_explain` (`🤖 AI Explain Config [6]`).
    - Schnellauswahl vorkonfigurierter Provider (Google Gemini, ChatGPT, Perplexity, Eigene URL).
    - 1-Klick Umschaltung der Prompt-Sprache (Deutsch / Englisch).
    - Persistente Speicherung in `config.json` unter `ai_explain_config`.
  - **Headless Agent CLI (`tasks explain`)**:
    - `tasks explain <id|index> [--lang de|en] [--copy-only] [--no-browser] [--json]`.
  - 11 neue automatisierte Unit-Tests in `tests/test_ai_explain.py` (Gesamtsuite: 306 bestandene Tests).

- [x] **Release v1.1.0 — WebUntis Lateness & Excuse Letter Polish, Login Reminder & Platform Toggle**:
  - **Minutengenaue Verspätungs- & Fehlzeitenberechnung**:
    - `match_absences_with_timetable` ermittelt für Verspätungen (z.B. eingetragene 11 oder 25 Minuten) die exakte minutengenaue Schnittmenge (`start_time`, `end_time`, `duration_minutes`) und behält das Unterrichtsfenster (`lesson_start_time`, `lesson_end_time`) bei.
    - Die Detailtabelle im `AbsencesScreen` zeigt in der Spalte `Time` das reale Abwesenheitsintervall (z.B. `14:25 - 14:36`).
    - `get_daily_absence_summaries` und `create_excuse_pdf` summieren die tatsächliche Abwesenheitsdauer exakt (z.B. `7:16` statt pauschal `8:20`).
  - **Verspätungen-Filterbutton (`ExcuseLetterModal`)**:
    - Neuer Toggle-Button `#btn_el_filter_lateness` (`⏳ Hide Lateness: ON` / `⏳ Hide Lateness: OFF`, Shortcut `[L]`) in der rechten unteren Ecke.
    - Standardmäßig aktiv: Filtert Fehltage mit einer Dauer von unter 50 Minuten (`< 50 min`) automatisch aus, sodass standardmäßig nur vollwertige Fehlstunden im Entschuldigungs-PDF aufgeführt werden.
    - Behoben: `Back`-Button im `ExcuseLetterModal` kehrt unmittelbar zum `AbsencesScreen` zurück ohne versehentliches Öffnen des Schülerdaten-Modals.
  - **Plattform-Deaktivierung & Abmelden im Login-Menü (`LoginChoiceModal`)**:
    - Kombinierter Action-Button (`Enable` / `Disable` / `🚪 Log Out`) am rechten Rand.
    - Leeren von Cache und Credentials bei Abmeldung; Deaktivieren schaltet Sync und Erinnerungen für ungenutzte Plattformen stumm.
    - Persistente Speicherung in `config.json` unter `enabled_platforms`.
  - **Humanisierte Netzwerk-Fehlerbehandlung & Fast-Fail**:
    - `_humanize_request_error` fängt rohe urllib3/requests Tracebacks ab und gibt präzise englische Fehlermeldungen aus.
    - Schneller Abbruch bei Serverausfällen ohne 15s Playwright-Wartezeit.
    - Neutraler Platzhalter `"Username"` und Bereinigung der E-Mail-Vorausfüllung in Teams.
  - **Login-Prüfung & LoginReminderModal bei jedem Sync**:
    - Automatischer Reminder am Ende eines Syncs, falls genutzte Plattformen nicht angemeldet sind, mit direkter Weiterleitung per Enter ins Login-Menü.
  - 18 neue automatisierte Unit-Tests in `tests/test_auth_logins.py`, `tests/test_excuse_service.py`, `tests/test_tui_app.py` und `tests/test_untis_service.py` (Gesamtsuite: 294 Tests, 100 % Erfolgsquote).

- [x] **Moodle & WebUntis Login Robustness & Cross-Device Compatibility**:
  - **Browserloses HTTP-Moodle-Login (`login_moodle_http`)**:
    - Moodle-Authentifizierung läuft primär über direkte HTTP-Requests (`requests.Session` mit dynamischer `logintoken`-Extraktion und Form-POST).
    - Funktioniert in unter 0,3s ohne vorinstallierten Playwright-Chromium-Browser (löst Login-Fehlschläge auf Geräten, auf denen nur `pip install -r requirements.txt` ausgeführt wurde).
    - Automatischer Browser-Fallback (`chrome`, `msedge`, `chromium`) nur noch als sekundäre Stufe für Notfälle.
  - **WebUntis Schulsuche & Bereinigung (`search_webuntis_school`, `clean_school_identifier`)**:
    - Automatische Erkennung und Bereinigung von Domains (`spengergasse.webuntis.com`), vollständigen URLs und Leerzeichen.
    - Integration der offiziellen WebUntis School Search API (`https://mobile.webuntis.com/ms/schoolquery2`).
    - Wenn das Schulfeld im Dialog leer gelassen wird, wird automatisch die Standard-Schule (`spengergasse`) verwendet.
  - **Automatisches Bereinigen von Schul-E-Mail-Adressen (`clean_school_username`)**:
    - Falls Schüler ihre E-Mail-Adresse (`end240102@spengergasse.at`) statt der Schülerkennung eingeben, wird das Suffix `@...` automatisch entfernt.
  - **Präzise Fehlerrückmeldung im TUI**:
    - `AuthResult` Tuple-Klasse transportiert den echten Server-Fehlertext von Moodle und WebUntis direkt in die Statuszeilen von `MoodleLoginModal` und `UntisSetupModal`.
  - **Playwright Chromium Pre-Flight Prüfung im `dependency_checker`**:
    - Erkennt fehlende Browser-Binärdateien und stellt diese bei Bedarf bereit.
  - 7 neue automatisierte Unit-Tests in `tests/test_auth_logins.py` (Gesamtsuite: 274 Tests, 100 % Erfolgsquote).

- [x] **Sync Performance & TUI Lag Optimization (v1.0.10)**:
  - **SyncSpinner Interval Throttling**: TUI-Ladeanimation (`SyncSpinner`) von aggressiven 80 ms (12,5 FPS) auf 250 ms (4 FPS) gedrosselt. Verhindert die Überlastung des Textual Asyncio-Event-Loops und von Windows ConPTY ANSI-Rerenders bei gleichzeitiger Hintergrundarbeit.
  - **Batch-UI-Aktualisierung & Throttling**: Entkopplung der Daten-Tabelle via `update_info_bar()`. Mehrere schnell aufeinanderfolgende Sync-Callbacks von Moodle und Teams leeren und zeichnen die 40+ Zeilen der `DataTable` nur maximal einmal alle 0,8 Sekunden neu; dazwischen wird lediglich die Info-Statistikzeile aktualisiert.
  - **Entsperrte Cache-Persistenz & Batch-Disk-Writes**: `TaskManager.save_cache()` kopiert den Speicherzustand unter Lock und schreibt atomar auf die Festplatte *ohne* Lock, wodurch kein anderer Thread blockiert wird. Im Hintergrund-Prefetcher (`_prefetch_worker`) werden Cache-Saves auf alle 5 Aufgaben gebündelt statt nach jeder einzelnen Aufgabe.
  - **Playwright Headless Chromium Optimierung**: `--disable-gpu`, `--disable-dev-shm-usage`, `--renderer-process-limit=2` und Muting zu den Chromium-Headless-Flags hinzugefügt, wodurch die CPU-Last des Teams-Syncs minimiert wird.
  - **Mouse-Back-Listener Schlafpause**: Polling-Intervall in `_run_mouse_back_listener` von 25 ms auf 60 ms relaxiert.

- [x] **In-Terminal Update-Workflow & Getting-Started Restoration (v1.0.10 Polish)**:
  - **Getting-Started Wiederherstellung bei Updates**: `TaskManager._check_and_apply_version_update` erkennt Versions-Updates (via `data/version.json` oder In-App Update Marker), entfernt `manual_welcome_setup_guide` aus `deleted_manual_ids`, setzt den Status auf `Open` zurück und platziert die Aufgabe an erster Stelle.
  - **Button-zentrierte englische Anleitung**: Sämtliche Hotkey-Angaben wurden durch präzise Bezeichnungen der realen Textual UI-Buttons ersetzt (`⚙️ Settings`, `⚙️ School & Student Config`, `🔑 Login`, `👥 Teams Login`, `🎓 Moodle Login`, `📅 WebUntis Login`, `🐙 Git Cloud-Sync`, `🔄 Sync`, `✓ Mark as Completed`, `🗑️ Delete`).
  - **Keine redundante Bibliotheksinstallation**: `setup.bat /silent` wurde aus dem Update-Prozess entfernt, da `dependency_checker.py` fehlende Abhängigkeiten automatisch beim App-Start prüft und installiert.
  - **In-Terminal Update-Loop in `run.bat`**: `run.bat` fängt den Exit-Code `42` sowie `%TEMP%\AufgabenDetector_Update\pending_update.txt` ab, führt das Update via `start /wait` im aktuellen Konsolenfenster stillschweigend aus und startet die App direkt im selben Terminal neu (ohne PowerShell-Popups oder neue Konsolenfenster).
  - 3 neue automatisierte Unit-Tests in `tests/test_update_service.py` (Gesamtsuite: 267 bestandene Tests mit 100 % Erfolgsquote).

- [x] **Documentation Modernization**:
  - Replaced legacy documentation files with standardized 2-tier persistent memory structure.
  - Created lean `< 3 KB` `AGENTS.md` master index for instant Antigravity session bootstrap.
  - Modularized domain documentation into `docs/project-overview.md`, `architecture.md`, `conventions.md`, `current-state.md`, and `decisions.md`.
- [x] **Multi-Platform Task Aggregation**:
  - Consolidated Moodle (`mod_assign`, calendar) and Microsoft Teams Education assignments into unified `Task` models.
  - Implemented persistent caching (`cache/tasks_cache.json`) enabling `< 0.1s` instant offline startup.
  - Added multi-level filtering (platform, subject, completion status, overdue).
- [x] **Interactive Textual TUI**:
  - Full keyboard & mouse-driven terminal application with color themes (Nord, Catppuccin, Monokai, Dracula).
  - Quick-Jump fuzzy course opener (`Backspace`), task detail viewer, and manual task creation modal.
- [x] **WebUntis Timetable & Absence Accounting**:
  - Correlated raw absence intervals with daily lesson timetables to calculate actual missed periods.
  - Filtered split workshop/lab classes (`1x` vs `1y`) and handled cancelled periods (*Entfall*).
  - Integrated exam planner (`UntisExam`) with custom revision notes.
- [x] **Headless Agent CLI (`tasks`)**:
  - Implemented token-efficient CLI dispatcher in `src/core/agent_cli.py`.
  - Supported subcommands and flags (`list`, `show`, `download`, `open`, `courses`, `add`, `done`, `delete`, `restore`, `sync`, `guide`).
  - Added `--json` output option for programmatic consumption by AI agents and scripts.
- [x] **Download & Document Generation**:
  - 1-Click download of assignment attachments and markdown problem statement (`angabe.md`) to `%USERPROFILE%\Downloads\<Fach> - <Titel>\`.
  - Automated PDF absence excuse generator using ReportLab / fpdf2 with official school header.
- [x] **Open-Source Distribution & Automated Releases**:
  - Transitioned from proprietary device-licensing to standard open-source **MIT License** (`LICENSE`).
  - Completely removed hardware-fingerprinting, secret keys, and activation prompts.
  - Refactored Inno Setup 6 packaging pipeline (`installer/build_installer.py` & `installer/aufgaben_detector.iss`) to produce universal `AufgabenDetector_Setup.exe` with on-demand Python 3.12 download.
  - Created automated GitHub Actions CI/CD workflow (`.github/workflows/release.yml`) building and publishing release installers upon Git tag pushes (`v*`).
  - Successfully published official release **[v1.0.0](https://github.com/X4nd109/Aufgaben-Detector/releases/tag/v1.0.0)** with bundled `AufgabenDetector_Setup.exe`.

- [x] **Git Cloud-Sync Deadlock & Connection Fix**:
  - Replaced non-reentrant `threading.Lock` with `threading.RLock` in [`git_sync_service.py`](../src/services/git_sync_service.py), eliminating mutual self-deadlock between `setup_repository`, `pull_and_sync`, and `push_changes`.
  - Added `-c core.askPass=` and `SSH_ASKPASS` to `_run_git_cmd` to strictly prevent external GUI/credential prompts from blocking background execution.
  - Hardened TUI `GitSetupModal` background worker with robust error recovery so UI status and connect buttons never freeze.
  - Handled clean repo-switching and empty remote branches without redundant failed fetch calls.

- [x] **Verzeichnis-Schnellzugriff & CommandPalette UX Fixes (v1.0.4)**:
  - Unified `Backspace` CommandPalette mit 3-Wege `Tab`-Umschaltung: **Courses** (Cyan) ➔ **Schoolbooks** (Rot) ➔ **Directories** (Grün).
  - Zentrierter Header-Schriftzug `[bold green]Directories[/bold green]` und dynamischer Such-Placeholder (`Search directories (/link, /unlink)...`).
  - **Suchtext-Erhalt bei Moduswechsel**: Eingegebener Text in der Suchleiste bleibt beim Wechseln mit `Tab` erhalten und filtert sofort im neuen Tab.
  - **Backspace-to-Close**: Wenn die Suchleiste leer ist, schließt ein Druck auf `Backspace` die Suchleiste sofort (`UnifiedCommandInput`).
  - Direkte Ordnerverknüpfung via `/link` über den nativen Windows-Ordnerauswahldialog (`FolderBrowserDialog` / `askdirectory`) mit automatischer Titelableitung vom Ordnernamen (z. B. `BET`).
  - 1-Klick / `Enter` zum Öffnen des verknüpften Ordners direkt im Windows Explorer (`os.startfile`).
  - Schnelles Löschen verknüpfter Ordner über `/unlink` oder `/delete`.
  - Lokale Persistenz in `data/directories.json` (automatisch von Git-Tracking ausgeschlossen via `.gitignore`).
  - Vollständige Headless CLI-Integration via `tasks dirs [list|open|add|remove] [--json]`.
  - **OLED Theme & UI Polish (22 Themes)**:
    - Neues `oled` Theme mit purem Schwarz (`#000000` Background/Surface/Panel) kombiniert mit Flexoki-Farbakzenten.
    - **Header & Bar Clipping behoben**: Borders von `Header`, `#info_bar` und `#button_bar` entfernt, damit Widgets und Buttons vertikal nicht mehr abgeschnitten werden.
    - **Button-Höhe wiederhergestellt**: Durch `height: 3;` in `.-theme-oled Button` besitzen Buttons in allen Menüs und Modals (`SettingsModal`, `ThemeSelectModal`, etc.) wieder die gewohnte 3-Zeilen-Höhe mit voller Lesbarkeit und zentrierter Schrift statt auf 1 Zeile zusammenzufallen.
    - **Weiße Spalten-Header**: Tabellen-Header (`DataTable > .datatable--header`) von Orange auf klares Weiß (`#ffffff`, bold) umgestellt.
    - **Tabellen-Fokus bleibt tiefschwarz**: Wenn mit `Tab` durch die Menüs (Main `#tasks_table`, Tests `#exams_table`, Absenzen `#abs_subject_table`/`#abs_detail_table`) navigiert wird, bleibt der Hintergrund rein schwarz (`background: #000000; background-tint: transparent;`) statt durch Textuals Default-Fokus-Tint grau aufzuleuchten.
    - **Theme-Menü Hover-State**: Beim Hovern über Themes in `ThemeSelectModal` wird der Hintergrund in dezentem Hellgrau (`#343331`) hervorgehoben.
  - 19 automatisierte Tests für Verzeichnisse und OLED-Theme-Styling.

- [x] **Windows-Tastatur-Shortcuts für alle Texteingabefelder (v1.0.5)**:
  - Projektweite Bereitstellung (`configure_enhanced_text_inputs`) für alle `Input`-Widgets (CommandPalette, Suchleisten, Formulare, Logins, Schulkonfiguration) und mehrzeilige `TextArea`-Notizen.
  - **STRG + A**: Markiert den gesamten Inhalt des Textfeldes (ersetzt Textuals Default `home`).
  - **Pos1 (`Home`) & Ende (`End`)**: Springt direkt an Zeilenanfang bzw. Zeilenende.
  - **SHIFT + Pos1 & SHIFT + Ende**: Markiert vom Cursor bis zum Zeilenanfang bzw. Zeilenende.
  - **STRG + ← & STRG + →**: Wortweises Springen des Cursors.
  - **SHIFT + STRG + ← & SHIFT + STRG + →**: Wortweises Markieren des Textes (`ctrl+shift+left` und `shift+ctrl+left`).
  - **STRG + Backspace & STRG + Entf**: Wortweises Löschen nach links bzw. rechts.
  - **STRG + Backspace 5-Stufen-Absicherungsarchitektur**:
    - Stufe 1 (Win32 Driver Patch): ConPTY KeyEvents mit `\x1b[127;5u`.
    - Stufe 2 (Hardware-Hook): OS-Abfrage (`GetAsyncKeyState(0x11)`).
    - Stufe 3 (CommandPalette Guard): `UnifiedCommandInput.action_delete_left`.
    - Stufe 4 (App-Level Menü Guard): Menü-Blockierung bei gedrücktem STRG.
    - Stufe 5 (Fallback Bindings): Native Terminal-Bindings.
  - 6 automatisierte Unit-Tests in `tests/test_tui_app.py` (insgesamt 230 Tests).

- [x] **Per-Monitor DPI-Awareness v2 & Native Windows Explorer Dialoge (v1.0.6)**:
  - Zentrales Modul `src/core/win_dialogs.py` mit `enable_high_dpi_awareness()`, `pick_file()` und `pick_directory()`.
  - Aktiviert `SetProcessDpiAwarenessContext(HANDLE(-4))` (Per-Monitor DPI Aware v2) direkt beim Programmstart (`main.py`, `src/main.py`), in `AufgabenApp.on_mount` und vor jedem Dialog.
  - Echte native Windows COM `IFileOpenDialog`-Instanzen für Dateiauswahl (`/link` in Schulbüchern) und moderne Ordnerauswahl mit `FOS_PICKFOLDERS` (`/link` in Verzeichnissen).
  - Volle Unterstützung für Schnellzugriff, Adressleiste, Suche und automatische 4K-Skalierung ohne bilineare DWM-Bitmap-Streckung („Low-Res-Explorer-Effekt“ behoben).
  - Graceful Fallback Cascade auf DPI-aware Tkinter und PowerShell Windows Forms.
  - 11 neue automatisierte Tests in `tests/test_win_dialogs.py`.

- [x] **Automatische 1-Klick In-App Update-Funktion im UpdateReminderModal (v1.0.7)**:
  - Vollautomatischer Download des Release-Installers (`AufgabenDetector_Setup.exe`) direkt im Modal mit Textual `ProgressBar`, Statusanzeige (MB/Gesamt-MB, Prozent) und Abbruchmöglichkeit (`cancel_event`).
  - Robuste Fehlerbehandlung mit Retry- und Fallback-Button ("Im Browser herunterladen").
  - **Zielordner- & Konfigurationserhalt**: Installation erfolgt zwingend im aktuellen Programmverzeichnis (`WORKSPACE_DIR`); `config.json`, `data/`, Caches und persönliche Einstellungen bleiben unberührt.
  - **Keine PATH-Modifikation**: Übergabe von `/NOTASKS=1` und `/UPDATE=1` an Inno Setup (`installer/aufgaben_detector.iss`) überspringt `setup_command.bat`, sodass die PATH-Variable unberührt bleibt.
  - **Automatisches Abhängigkeiten-Update**: `setup.bat /silent` prüft und installiert neue pip requirements im Hintergrund ohne blockierende Pause-Abfragen.
  - **Entkoppelter Handoff & Auto-Neustart**: `%TEMP%\AufgabenDetector_Update\apply_update.cmd` wartet auf Beenden des Python-Prozesses, führt die Aktualisierung geräuschlos (`/VERYSILENT`) durch und startet `run.bat` neu.
  - 5 neue automatisierte Tests in `tests/test_update_service.py` (insgesamt 246 Tests in der Testsuite mit 100% Erfolgsquote).

- [x] **DPI-Fensterproportionen & Settings-Modal UX Fix**:
  - **Terminal-Startgröße**: `ensure_terminal_window_size` auf 123 Spalten (+1 Spalte breiter) und 33 Textzeilen (-3 Zeilen niedriger) feinjustiert.
  - **DPI-Höhenskalierung**: Höhe wird unter Berücksichtigung von `GetDpiForWindow` und gemessener Zeilenhöhe dynamisch auf 33 Textzeilen (`effective_min_h`) skaliert.
  - **ExamsScreen Vollbreiten-Spaltenverteilung & Beseitigung des rechten Leerraums**:
    - Alle 9 Spalten werden dynamisch und proportional über die gesamte Containerbreite gestreckt (`dt.columns[i].width`), sodass rechts kein ungenutzter schwarzer Bereich mehr entsteht und der blaue Zeilen-Cursor die gesamte Breite hervorhebt.
    - Themen/Notizen erhalten bei breiten Bildschirmen bis zu 60 % des zusätzlichen Freiraums (keine unnötigen `...`-Kürzungen mehr).
    - Vertikaler Scrollbar-Puffer verhindert horizontales Scrollen bei jeder Fenstergröße.
    - Vollständige dynamische Größenanpassung via `on_resize(term_w_override=...)`.
    - Neuer Test `test_exams_screen_full_width_column_distribution_and_resize` (Gesamtsuite: 247 bestandene Tests mit 100% Erfolgsquote).
  - **SettingsModal Button-Clipping behoben**: `#settings_dialog` auf `VerticalScroll` umgestellt, Button-Abstände (`margin-bottom: 1;`, `padding: 1 2;`) exakt an `FilterMenuModal` angeglichen und maximale Höhe auf `96%` erweitert. Der `[↩️ Close [ESC]]`-Button wird nicht mehr abgeschnitten und bleibt jederzeit voll sichtbar und erreichbar.
  - **FilterMenuModal Bereinigung**: Die redundante Textzeile (`#filter_info`) unter dem Titel („Status: ... | Due Window: ...“) wurde entfernt, da die Zustände bereits auf den Buttons abgebildet werden.

- [x] **Main Task Dashboard Vollbreiten-Spaltenverteilung & Beseitigung der Scrollleiste (v1.0.8)**:
  - Dynamische proportionale Breitenberechnung aller 7 Spalten (`#`, `Platform`, `Subject`, `Assignment`, `Due Date`, `Status`, `Teacher`) basierend auf der tatsächlichen Fenster-/Container-Breite analog zum Exams-Screen.
  - Spaltenbreiten werden explizit auf den `DataTable`-Spalten gesetzt (`col.width`, `auto_width = False`), wodurch die Tabelle 100 % der Fensterbreite ausfüllt und horizontaler Überlauf sowie die Scrollleiste vollständig eliminiert werden.
  - Spalte *Assignment* erhält den flexiblen Mittelteil der Breite und wird bei Überschreitung sauber mit `...` (3 ASCII-Punkte) gekürzt (z. B. `OverTheWire/Bandit_0-6_Linux...`).
  - Zeilenumbrüche und Whitespace-Spitzen in Titeln und Notizen werden vor der Darstellung bereinigt, um Mehrzeiligkeit oder Formatierungsbrüche zu verhindern.
  - Reagiert sofort auf Terminalgrößenänderungen via `on_resize(term_w_override=...)`.
  - **Moodle-Status-Negationsprüfung**: Negationsabsicherung in `Task.is_completed` und `format_status_english`: Texte wie *„Bisher wurden keine Aufgaben abgegeben“* oder *„nicht abgegeben“* werden nicht mehr fälschlicherweise durch das Teilwort *„abgegeben“* als erledigt gewertet, sondern bleiben korrekt als `Open` erhalten.
  - 3 neue automatisierte Tests in `tests/test_tui_app.py` (insgesamt 249 Tests in der Gesamtsuite mit 100 % Erfolgsquote).

- [x] **UpdateReminderModal Englisch-Lokalisierung, Button-Layout & Text-Clipping (v1.0.8 Polish)**:
  - **Vollständige englische Lokalisierung**: Alle Textbausteine des Update-Erinnerungsmodals auf Englisch umgestellt (`🚀 New Version Available!`, `Current Version: ...`, `Latest Version: ...`, `A newer release with improvements and bug fixes is available on GitHub.`, `Initializing download...`, `Connecting to GitHub...`, `Downloading: ... MB / ... MB`, `Download complete! Preparing installation...`, sowie Fehlermeldungen).
  - **2-Zeilen-Button-Layout**: Der `Later [ESC]`-Button ist nun unter den beiden Haupt-Aktionen (`⬇️ Install Update Now` und `🌐 View in Browser`) zentriert platziert, sodass kein Button mehr am Dialogrand abgeschnitten wird.
  - **Analoges Error-Buttons-Layout**: Auch im Fehlerzustand sind die Optionen auf 2 Zeilen aufgeteilt (`🔄 Try Again` + `🌐 Download in Browser` oben, `Close [ESC]` zentriert unten).
  - **Beseitigung des Text-Clippings**: `width: 100%` auf `#update_hint` gesetzt, wodurch der Hinweistext automatisch sauber mehrzeilig umbrochen wird. Dialogbreite leicht auf 70 Spalten vergrößert für entspannte Ränder.
  - Maskierung der `\[ESC]`-Klammern, damit Textuals Content/Rich-Markup-Parser die Tastenkombination nicht verschluckt.
  - Neuer Test `test_update_reminder_modal_layout_and_english_texts` in `tests/test_update_service.py` (insgesamt 250 Tests in der Gesamtsuite mit 100 % Erfolgsquote).

- [x] **Tesseract OCR-Optimierung für Fett- und Unterstrichenen Text (v1.0.9)**:
  - **Sauvola Binarisierung (`thresholding_method=2`)**: Lokale adaptive Schwellenwertbildung verhindert das Zulaufen dicker Buchstabenschlaufen und trennt Unterstreichungen sauber vom Grundtext.
  - **Nicht-lineare Strichdicken-Normierung (`classify_nonlinear_norm=1`)**: Präzise Klassifizierung fetter Schriftzüge ohne Einstufung als Fremdsymbole.
  - **Unterstreichungstrennung (`textord_restore_underlines=1` & `textord_underline_threshold=0.5`)**: Horizontale Linien werden gezielt von Unterlängen (`g`, `j`, `p`, `q`, `y`) abgeschnitten.
  - **Sanftes Unsharp-Masking**: Schärfung vor Tesseract (`radius=1.2, percent=115, threshold=3`) für optimale Kantenpräzision ohne visuelle Einbußen im PDF.
  - Robuster doppelter Fallback auf Standard-OCR und reine Bild-Einbettung bei inkompatiblen Tesseract-Versionen.

- [x] **Digi4School Interaktive Seitenauswahl & 2-Thumb Range-Slider (v1.0.9)**:
  - **Automatische Buch- & Seitenzahlerkennung**: Neue Methode `Digi4SchoolService.inspect_book` loggt sich headless im Hintergrund ein und liest Buchtitel sowie die exakte Gesamtzahl der Buchseiten aus.
  - **Ladedialog `Digi4SchoolDetectModal`**: Kompakte Ladeanzeige (*"Connecting to Digi4School and detecting book pages..."*) mit Lade-Spinner und Abbrechen-Möglichkeit.
  - **Kompaktes Menü `Digi4SchoolPageRangeModal`**: Grafischer Auswahldialog für den gewünschten Seitenbereich mit Buchtitel, Zugangscode, 2-Thumb-Slider, synchronisierten Ziffernfeldern und zentriertem *All*-Button.
  - **Interaktives `TwoThumbRangeSlider` Widget**:
    - Stellt eine visuelle Schiene mit 2 Schiebern (Startseite und Endseite) im Catppuccin Mocha-Design dar.
    - Volle Mausbedienung (Klick auf Schiene zur Positionierung des nächstgelegenen Griffs sowie Halten und Ziehen per Drag & Drop).
    - Tastaturnavigation mit Pfeiltasten (`Left`/`Right`, `Shift` für 10er-Schritte, `Tab`/`1`/`2` zum Wechseln des aktiven Schiebers, `Home`/`End`).
  - **Synchronisierte Ziffernfelder**: Zwei Eingabefelder (*"From Page"* und *"To Page"*) zur Direkteingabe; bidirektional in Echtzeit mit dem Schieberegler synchronisiert.
  - **Range-Download & OCR**: Nahtlose Weitergabe des gewählten Seitenbereichs (z. B. `20-50`) an `Digi4SchoolProgressModal` und `Digi4SchoolService.download_book`.
  - 12 neue automatisierte Unit-Tests in `tests/test_page_range_slider.py` (insgesamt 264 Tests in der Gesamtsuite mit 100 % Erfolgsquote).

- [x] **Main Task Dashboard Formatierung, Sync-Uhrzeit & Spaltenpriorisierung (v1.0.9 Polish)**:
  - **Kein Zeilenumbruch der Sync-Uhrzeit**: `#info_bar` und `#info_stats` auf feste `height: 1` gesperrt mit `overflow-y: hidden`, `overflow-x: hidden` und `margin-bottom: 1;`, wodurch die gewohnte leere Trennzeile zwischen Info-Leiste und Aufgaben-Tabelle erhalten bleibt.
  - **Zero-Layout-Shift Sync-Spinner**: `SyncSpinner` besitzt nun eine permanent feste Boxbreite (`width: 3; height: 1; display: block;`). Das Starten und Stoppen des Hintergrund-Syncs verändert die verfügbare Breite um 0 Zeichen, wodurch das Springen der Uhrzeit (`19:09:06`) in eine zweite Zeile vollständig eliminiert wurde.
  - **Dynamisches Badge-Kompaktieren**: Bei schmaleren Terminalbreiten (< 118 Spalten) oder langen Prüfungs-Badges werden 0-Zähler (`Teams: 0`, `Manual: 0`) automatisch ausgeblendet und Trennzeichen gestrafft, damit die Sync-Anzeige niemals abgeschnitten wird.
  - **Header-Truncation "Teacher" behoben**: Spalte 6 (`Teacher`) von Basisbreite 6 auf min. 8 (bzw. 7 bei extrem schmalen Fenstern) erhöht, sodass der Header `"Teacher"` niemals zu `"Teache"` abgeschnitten wird und Lehrerkürzel voll lesbar bleiben.
  - **Priorisierte Spaltenbreitenverteilung**:
    - Spalte *Due Date* erhält garantierte 28–32 Zeichen für vollständige Datumsangaben (z. B. `Montag, 2. November, 23:59`) ohne unschöne `...`-Kürzungen.
    - Spalte *Teacher* erhält min. 8 Zeichen für Header und Lehrerkürzel.
    - Spalte *Assignment* nimmt den gesamten flexiblen Rest ein (`avail_content - sum(others)`) und wird bei Verkleinerung des Fensters als erste Spalte gekürzt.
  - **4K/1440p Startup Viewport-Kalibrierung**: In `_sync_initial_viewport` wird `refresh_table()` nach dem initialen UI-Mount erneut aufgerufen, sodass die exakten gemessenen Fensterdimensionen auf hochauflösenden Displays sofort greifen.
  - 2 neue automatisierte Tests in `tests/test_tui_app.py` (insgesamt 252 Tests in der Gesamtsuite mit 100 % Erfolgsquote).

---

## 2. In Progress / Immediate Next Steps

- [x] **Digi4School PDF-Komprimierung & DCTDecode-Pipeline**: Umstellung von FlateDecode-PNGs auf JPEG 4:4:4 (`subsampling=0`) mit Preset-Qualität 80/85/90 (Default Q90; Dateigrößenreduktion um ~80-85%).
- [x] **Multi-Core In-Place PDF-Kompaktierer (`tasks books compact`)**: Parallele Bildkompression via `ProcessPoolExecutor` mit Streaming Sliding-Window (RAM < 400 MB, `os.cpu_count() - 1` Cores).
- [x] **Range-Slider Text-Selektions-Fix**: `ALLOW_SELECT = False` und Maus-Capture auf `TwoThumbRangeSlider` zur Beseitigung der Markierungs-Artefakte beim Ziehen.
- [ ] **Optionaler ESC-Shortcut im AI Chat**: Überprüfen, ob [ESC] im Chatverlauf bei geöffneter Tastatur den Fokus freigibt oder direkt zurückkehrt.
- [ ] **Vorbereitung Release v2.4.1 / Tagging**: Versionierung hochstufen und Release-Paket schnüren.

---

## 3. Session Handoff Notes

- **Erreicht in dieser Session (Digi4School PDF Compression, Multi-Core Compactor & Slider Polish)**:
  - **JPEG 4:4:4 DCTDecode-Pipeline**: Bilder im Grabber werden nun mit `subsampling=0` als hochauflösendes JPEG eingebettet (Preset-Qualität 80/85/90, Default Q90). Text, Formeln und Schaltpläne bleiben gestochen scharf ohne Farbsäume; Dateigrößen sinken von ~850 MB auf ~130–150 MB.
  - **Neuer Befehl `tasks books compact <datei|index|all>`**:
    - Kompaktiert existierende PDFs nachträglich verlustarm direkt auf der Festplatte.
    - Vollständiger Erhalt aller OCR-Texte, Inhaltsverzeichnisse (Bookmarks/Outlines) und PageLabels.
    - Atomare Ersetzung mit optionalem Sicherheitsbackup (`--keep-original`).
  - **Multi-Core `ProcessPoolExecutor` Pipeline**:
    - Automatische Erkennung aller CPU-Kerne (`os.cpu_count() - 1` Standard, anpassbar via `--workers <N>` / `--cores <N>`).
    - Streaming Sliding-Window (`workers * 2` Aufgaben in-flight) hält RAM stabil unter 400 MB.
    - Beschleunigung um den Faktor 6x bis 10x (~20–30s für 400 Seiten).
  - **TwoThumbRangeSlider Text-Markierung behoben**:
    - `ALLOW_SELECT = False`, `capture_mouse()` und Event-Isolierung eliminieren die unschöne Text-Hervorhebung beim Ziehen mit der Maus restlos, bei 100% unverändertem Design.
- **Hinweis für nächste Session / nächsten Agent**:
  - Alle 20 Tests in `tests/test_digi4school.py` und alle 14 Tests in `tests/test_page_range_slider.py` laufen fehlerfrei durch (100% Erfolgsquote).
  - ADR-026 wurde in `docs/decisions.md` dokumentiert.
  - Dokumentation in `AGENTS.md`, `docs/current-state.md`, `docs/changelog.md`, `docs/features.md`, `docs/architecture.md` und `docs/decisions.md` ist vollständig synchron.
