# Current Project State & Session Handoff — Tasks

> **Last Updated**: 2026-10-25  
> **Active Milestone**: Release v2.0.0 (Released) — Tasks Rebranding, New Quantum Prism Icons, Single-Execution Ai Explain & Git-Sync Cleanup

---

## 1. Completed Tasks & Milestones

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

- [ ] **Background Task Notifications**:
  - Optional Windows notification toast for assignments due within 24 hours.
- [ ] **Extended Test Coverage**:
  - Expand offline test fixtures for WebUntis multi-day holiday and substitution edge cases.
- [ ] **Git Synchronization Refinement**:
  - Enhance `git_sync_service.py` conflict resolution for user notes in `data/exam_notes.json`.

---

## 3. Known Issues & Blockers

- **Keine**: Alle 407 automatisierten Unit-Tests laufen fehlerfrei durch (`Ran 407 tests — OK`).
  - Hinweis: `tests/test_digi4school.py` fragt bei interaktivem `stdin` (`isatty() == True`) nach E-Mail/Passwort. In CI bzw. mit nicht-interaktivem `stdin` laufen alle Tests grün; in einer TTY-Shell ohne Eingabedaten können die zwei Credential-Tests `EOFError` werfen (umgebungsbedingt, unabhängig vom AI-Chat).

---

## 4. Session Handoff Notes (Context for Next Agent)

- **Latest Achievement (2026-10-24 — AI Explain Single-Execution Memory & Chat Clear Reset)**:
  - **Dauerhafte Deduplizierung (`is_task_ai_explained`, `set_task_ai_explained`)**:
    - Wenn der Benutzer in der Aufgaben-Detailansicht auf `🤖 Ai Explain [A]` klickt, speichert das System in `cache/ai_chats.json` unter `_explained_task_ids`, dass diese Aufgabe bereits erklärt wurde.
    - Bei erneutem Klick auf `Ai Explain [A]` wird die Erklärung nicht nochmals an die KI gesendet, sondern der bestehende Chat direkt angezeigt (inkl. Hinweis `ℹ️ Existing explanation loaded.`).
  - **Reset beim Chat-Leeren**:
    - Klickt der Nutzer auf `🗑️` (Clear Chat) oder drückt `Ctrl+L`, wird die Aufgabe aus `_explained_task_ids` entfernt (`clear_task_chat_cache` & `set_task_ai_explained(task_id, False)`).
    - Ein nachfolgender Klick auf `Ai Explain [A]` erklärt die Aufgabe wieder vollständig von Grund auf.
  - **Fehler-Resilienz & Abwärtskompatibilität**:
    - Tritt ein Fehler auf (z. B. fehlender API-Key oder Netzwerkfehler), wird die Aufgabe nicht fälschlich als erklärt markiert.
    - Vorherige Chatverläufe mit Erklärungs-Prompts werden rückwirkend erkannt.
    - `cleanup_ai_chats_cache` entfernt verwaiste IDs abgeschlossener Aufgaben automatisch aus `_explained_task_ids`.
  - **Umfassende Testabdeckung**: 104 AI-Tests erfolgreich (alle 407 Tests im Gesamtprojekt grün).

- **Release v1.3.0 Milestone Summary (2026-10-24)**:
  - **In-App AI Chat Assistant (`AiChatScreen`)**: Vollständiger Ersatz des alten externen Web-Ai-Systems durch ein integriertes Vollbild-Terminal-Interface.
  - **Browser-Style Task Tabs**: Horizontale, kompakte 1-Zeilen-Tableiste mit Fachkürzeln für inaktive Tabs und voller Fachtitel-Expansion für den aktiven Tab inklusive flüssigem Scrolling.
  - **Auto-Attachment Extraction**: PyMuPDF (`fitz`), Markdown- und Quellcode-Extraktion bettet alle Aufgaben-Dateien ohne Zutun des Benutzers direkt in den Prompt-Kontext ein.
  - **Rich Markdown & Code-Block Rendering**: Native Formatierung für Assistant-Antworten mit Highlighting für Inline-Code und Codeblöcke im Standard- und OLED-Theme.
  - **Pulsierende Denk-Anzeige**: 3-Stufen-Animation (`Thinking.` $\rightarrow$ `Thinking..` $\rightarrow$ `Thinking...`) mit 2,0s Zyklus und sauberem Timer-Lifecycle.
  - **Universal Theme Support**: Semantische Textual-Variablen für fehlerfreie Darstellung über alle 22 Themes hinweg.
  - **Intelligente Tab-Wiederherstellung & Lesefluss**: Merkt sich die zuletzt geöffnete Aufgabe und richtet das Chatfenster bei Antworten an der Fensteroberkante aus.
  - **Auto-Growing Prompt-Eingabe**: Dynamisch wachsende Leiste (1–3 Zeilen) mit echtem `Shift+Enter` Zeilenumbruch (inkl. Win32-Hardware-Fallback) und verankertem, sattem Karminrot-Clear-Button (`#e03131`).
  - **Smart Download Auto-Directory (`DownloadLocationModal`)**: 1-Klick-Download direkt in verknüpfte Schulfach-Ordner (`tasks download --auto-dir`).
  - **Startzeit-Optimierung**: Kaltstart um ~40% beschleunigt durch Lazy Loading von Heavyweight-Paketen und asynchrone Cache-Pruning-Threads.

- **Recent Achievements (2026-10-23 — Filter Menu Scrollbar & TUI Startup Speed Optimization)**:
  - **Scrollbares Filter-Menü (`FilterMenuModal`)**:
    - Umstellung des `#filter_dialog` Containers von `Vertical` auf `VerticalScroll(id="filter_dialog")`.
    - CSS-Anpassung mit `overflow-y: auto;` und `scrollbar-gutter: stable;` für zuverlässiges Scrollen auf kleinen Bildschirmen (z. B. 80x20 Terminals) ohne abgeschnittene Buttons.
  - **Startbeschleunigung (~40% schneller, ca. 760 ms Ersparnis)**:
    - Lazy Loading für schwere Bibliotheken: `excuse_service` (`fpdf2`), `digi4school_service` (`fitz`/`PyMuPDF`, `PIL`, `pytesseract`) und `auth` (`playwright`, `requests`) in `src/ui/tui_app.py` und `src/main.py`.
    - Asynchroner Daemon-Thread für `clean_browser_profile_caches()`, sodass der synchrone Festplattenscan vor dem Öffnen der TUI entfällt.
    - Vollständige Verifikation: 316 Unit-Tests erfolgreich (100%), Kaltstartzeit von 1,88s auf 1,12s gesenkt.
  - **Architektur & ADR**:
    - Dokumentiert in `ADR-022: On-Demand Lazy Subsystem Loading & Non-Blocking Startup Optimization` und `docs/architecture.md`.

- **Previous Achievements (2026-10-23 — Release v1.3.0: Smart Download Auto-Dir & Agent Streamlining)**:
  - **Smart Download Auto-Directory Feature (`DownloadLocationModal`)**:
    - Vollständig englischsprachiges Auswahldialog-Modal beim Klick auf `📥 Download [D]` mit Hotkeys `[1]`, `[2]`, `[3]` und `[ESC]`.
    - `[1] Linked Course Folder`: Automatische Erkennung via `DirectoryService.find_matching_directory_for_course()`. Erstellt einen Unterordner mit dem Aufgabennamen im verknüpften Kursverzeichnis (`<Matched_Path>/<Aufgabentitel>/`) und speichert dort alle Dateien ab. Falls kein Ordner für das Fach verknüpft ist: Button deaktiviert (`disabled=True`) mit gelbem Hinweis `⚠️ No linked folder for '<Fach>' [1]`.
    - `[2] Choose Folder Manually...`: Öffnet wie gewohnt den nativen Windows Explorer Folder Picker (`pick_directory`).
    - `[3] Standard Downloads Folder`: Speichert direkt unter `%USERPROFILE%\Downloads\<Fach> - <Aufgabe>\`.
  - **Headless CLI Erweiterung (`tasks download --auto-dir`)**:
    - Neuer Flag `--auto-dir` (`-a`) für `tasks download <id>`.
  - **Vollständige Bereinigung des alten Agent-Harnesses**:
    - Button `🤖 Agent [G]` (`btn_det_agent`), Key-Binding `[G]` und `action_agent_open` entfernt.
    - Dialoge `AiAgentConfigModal` und `AiConfigChoiceModal` entfernt; das Einstellungsmenü verlinkt wieder direkt auf `🤖 AI Explain Config`.
    - Headless CLI-Befehl `tasks agent` entfernt und `src/services/ai_agent_service.py` gelöscht.
  - **Testabdeckung**:
    - Neue Test-Suite `tests/test_download_auto_dir.py` (7/7 Tests erfolgreich).
    - Gesamte Test-Suite mit 100 % Erfolgsquote (316 Tests).
- **Previous Achievements (2026-10-22 — Release v1.2.1: Global 'tasks' Agent-Skill & CLI Sync Command)**:
  - Schlanker, token-effizienter Skill (`skills/tasks/SKILL.md`) optimiert für `/tasks`.
  - Befehl `tasks skill [sync|status]`.
- **Previous Achievements (2026-10-22 — Release v1.2.0: AI Explain & Desktop App Linking)**:
  - AI Explain mit Provider-Vorlagen und Desktop App Linking.
- **Entry Points**:
  - Desktop / Interactive: `run.bat` oder `python main.py`
  - Agent / Script: `tasks.bat <subcommand>` oder `python main.py <subcommand>`
- **Test Verification**:
  - Run all tests with `python -m unittest discover tests`.
