# Changelog — Tasks

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/)
und dieses Projekt hält sich an [Semantic Versioning](https://semver.org/lang/de/).

---

## [Unreleased]

## [2.1.1] - 2026-10-26

### Changed
- **Startup-Performance & Lazy Loading (ca. 700–900ms schnellere Startzeit) & Launch-Hinweis**:
  - `main.py` / `src/main.py`: Gibt beim Start der interaktiven TUI (z.B. via `tasks` oder `python main.py`) unmittelbar `"Launching TUI..."` ins Terminal aus, bevor Textual den Vollbildmodus initialisiert. Startet bei Aufruf ohne Argumente (`len(sys.argv) == 1`) direkt `run_tui()` ohne Umweg über den CLI-Argparser und redundante Vorabprüfungen.
  - `src/main.py`: Synchronen Aufruf von `clean_browser_profile_caches()` im Hauptthread entfernt (wird bereits asynchron im Hintergrund von `tui_app.py` ausgeführt). Top-Level-Imports von `ui`, `Prompt`, `TaskManager` und `Task` in die jeweiligen CLI-Pfade verlagert.
  - `src/core/task_manager.py`: Statische Imports von `moodle_service` und `teams_service` entfernt und lokal in `sync()`, `_prefetch_worker()`, `load_task_details()` und `download_task_files()` verschoben. Importzeit von `task_manager` sank von 421 ms auf 22 ms (-95%).
  - `src/core/auth.py`: Statischen Playwright-Import (`sync_playwright`) entfernt und on-demand in den interaktiven Teams-Logins platziert.
  - `src/ui/tui_app.py`: `import ui` entfernt und durch direktes `webbrowser.open()` ersetzt; Modal-Imports für `auth`, `SchoolbookService`, `DirectoryService` und `check_for_updates` auf bedarfsgerechtes Lazy-Loading umgestellt.

### Fixed
- **Sauberes Beenden bei aktivem Aufgaben-Sync (Unterdrückung von TargetClosedError & Asyncio-Meldungen)**:
  - `src/core/config.py`: Globales Flag `_IS_SHUTTING_DOWN` mit `set_shutting_down()` und `is_shutting_down()` eingeführt; `close_all_active_browser_contexts()` setzt dieses Flag automatisch.
  - `src/services/teams_service.py`: Warteschleifen brechen bei gesetztem Shutdown-Flag sofort ab; `TargetClosedError` ("Target page, context or browser has been closed") und Fehler während des App-Beendens werden nicht mehr auf `sys.stderr` ausgegeben.
  - `src/core/task_manager.py`: `shutdown()` ruft `set_shutting_down()` auf; `sync()` unterdrückt Fehlermeldungen bei Shutdown/abgebrochenen Browserkontexten.
  - `src/ui/tui_app.py`: Hintergrund-Sync-Thread wird referenziert (`self._sync_thread`) und beim Beenden mit bis zu 0.5s Timeout gejoint (`join(timeout=0.5)`). Asyncio-Logger-Filter `_PlaywrightShutdownFilter` und `sys.unraisablehook` unterdrücken verwaiste `TargetClosedError`-Futures und zerstörte `BrowserContext.close()`-Pending-Tasks.
  - `src/ui/tui_app.py`: `RuntimeError: App is not running` in `SyncWorker` (wenn der Nutzer während des Syncs `Strg + C` drückt) wird sauber abgefangen; gibt stattdessen genau einmal `"Sync not Complete"` im Terminal aus.
  - Unittest-Suite `tests/test_teams_shutdown.py` auf 7 Tests erweitert.

## [2.1.0] - 2026-10-26

### Added
- **AI-Menü: Back-Button exakt wie im Tests-Menü (Breite & Styling) & 1 Zeile nach unten versetzt**:
  - `src/ui/tui_app.py`: `#btn_ai_back` Label auf `"↩️ Back"` vereinheitlicht und `min-width: 4;` gesetzt (vorher 12), wodurch die Breite exakt 9 Zeichen wie bei `#btn_exams_back` beträgt.
  - `#ai_input_btn_box` auf `align: right bottom;` umgestellt, wodurch der Button um 1 Zeile nach unten rückt und bündig mit der Unterkante von `#ai_chat_input` abschließt.
  - Der Clear-Chat-Button (`#btn_ai_clear_chat`) trägt nun das Textlabel `"Clear"` (statt Emoji `🗑️`), wurde verbreitert (`min-width: 9; padding: 0 1;`) und dockt über `#ai_chat_toolbar` (`align: right middle; margin: 0; padding: 0;`) direkt unter dem Aufgaben-Banner bündig an der rechten Bildschirmecke an.
- **Gezielte Zuweisung des 3-Zeilen-Verhaltens (`ChatInputArea`) auf Freitextfelder**:
  - `src/ui/tui_app.py`: Die 3-Zeilen-Eingabelogik (`ChatInputArea`) mit dynamischem Zeilensprung (Mitte -> Oben -> Mitte -> Unten -> Scrollen) und feiner Randlinie rundherum (`border: solid`) bleibt exklusiv aktiv für:
    - AI-Chat Menü (`#ai_chat_input`)
    - Aufgaben-Beschreibung in `AddTaskModal` (`#inp_add_desc`)
    - Prüfungsstoff in `AddExamModal` (`#inp_add_exam_topics`) und `ExamDetailModal` (`#inp_exam_topics`)
  - Alle restlichen Felder (Fach, Titel, Datum, Uhrzeit, Lehrer, Raum, Einstellungen, Login-Credentials, URLs) wurden wieder zu kompakten Standard-`Input`-Feldern zurückgesetzt.
- **Anwendungsweites 3-Zeilen-Verhalten für Formular-Schriftfelder (`ChatInputArea`)**:
  - `src/ui/tui_app.py`: Rollout des 3-Zeilen-Verhaltens mit dynamischem Zeilensprung (Zeile 1 mittig -> Zeile 2 oben/mitte -> Zeile 3 oben/mitte/unten -> Zeile 4+ Bottom-Scroll mit Scrollbar) auf alle Formular- und Texteingabefelder in sämtlichen Dialogen (`AddTaskModal`, `AddExamModal`, `ExamDetailModal`, `SettingsModal`, `MoodleLoginModal`, `TeamsSetupModal`, `UntisSetupModal`, `GitSetupModal`, `Digi4SchoolDownloadModal`, `SchoolbookUrlModal`).
  - Reine Suchleisten (`UnifiedCommandPalette`, `SubjectFilterModal`) und sensible Passwortfelder (`password=True`) verbleiben wie vorgegeben 1-zeilig.
  - Vollständige Duck-Typing- und Metaklassen-Kompatibilität (`isinstance(..., Input)` und `issubclass(..., Input)` via `_MessagePumpMeta`), sodass alle Abfragen (`query_one(..., Input)`) und Event-Handler (`Input.Submitted`, `Input.Changed`) unverändert funktionieren.
  - Neue Unittest-Suite in `tests/test_form_inputs_3lines.py` hinzugefügt.
- **AI-Menü: Konstante 3-Zeilen Schreibleiste mit dynamischem Zeilensprung (`ChatInputArea`)**:
  - `src/ui/tui_app.py`: Schreibleiste im AI-Assistenten ist nun von Beginn an konstant 3 Zeilen hoch (`height: 3;`).
  - **Dynamischer Zeilensprung**:
    - Bei 1 Zeile (bzw. leerem Eingabefeld mit Platzhalter) steht der Cursor in der mittleren Zeile (`padding: 1 1 1 1`).
    - Bei 2 Zeilen springt Zeile 1 in die obere Zeile und Zeile 2 wird in der Mitte getippt (`padding: 0 1 1 1`).
    - Bei 3 Zeilen wird in der unteren Zeile getippt (`padding: 0 1 0 1`).
    - Ab 4 Zeilen verbleibt die Schreibzeile unten, ältere Zeilen scrollen nach oben weg und die Scrollbar blendet sich ein.
  - **3-Zeilen hoher Back-Button (`#btn_ai_back`)**:
    - Label vereinheitlicht auf `"↩ Back"` (analog zur Prüfungs- und Fehlstundenansicht).
    - Höhe auf 3 Zeilen (`height: 3; min-width: 12;`) vergrößert im Standard-Button-Design.
  - **Kompakter Clear-Chat-Button (`#btn_ai_clear_chat`)**:
    - Bleibt bei 1 Zeile Höhe mit `🗑️` und ist unten bündig im Container platziert.
  - Volle Farbanpassung für Standard- und OLED-Theme (`.-theme-oled`).
  - Aktualisierte Unittests in `tests/test_ai_chat_ui.py`.
- **Backspace-Suchmenü (`UnifiedCommandPalette`) Feste 3-Tab-Boxen & Top-Docking**:
  - `src/ui/tui_app.py`: Die Suchpalette dockt nun bündig an der Fensteroberkante an (`margin-top: 0;`).
  - **Feste 3-Tab-Boxen nebeneinander**: 3 gleich große Boxen in fixer Reihenfolge nebeneinander (`Courses` links, `Schoolbooks` Mitte, `Directories` rechts) ohne Positionswechsel.
  - **Farben & Typografie**: Der jeweils aktive Tab hat weiße Schrift auf farbigem Hintergrund (Courses: Cyan `#04a5e5`, Schoolbooks: Rot `#e64553`, Directories: Grün `#40a02b`). Inaktive Tabs sind dezent ausgegraut mit sanftem Hover-Highlighting.
  - **Interaktion**: Navigation vorwärts per `Tab` und rückwärts per `Shift+Tab` sowie Direktwechsel per Mausklick auf jede der 3 Boxen (mit automatischem Fokus-Erhalt im Suchfeld).
  - Neuer automatisierter Integrationstest `test_palette_tabs_layout_and_switch` in `tests/test_directories.py`.
- **Interaktive Spaltensortierung in der Haupttabelle (`TasksApp`)**:
  - `src/ui/tui_app.py`: Klick auf Spaltenheader (`Platform`, `Subject`, `Due Date`, `Status`, `Teacher`) sortiert die Tabelle aufsteigend (`↑`) bzw. absteigend (`↓`) im 2-Wege-Toggle.
  - **Start-Sortierung**: Beim Programmstart wird die Tabelle automatisch nach Fälligkeitsdatum absteigend sortiert (`Due Date ↓`, nächste Fälligkeit zuerst oben).
  - **Vollständige Pfeil-Sichtbarkeit auf allen Spalten**: Dynamische Breitenberechnung garantiert ausreichend Platz (`Platform ↑/↓`, `Subject ↑/↓`, `Due Date ↑/↓`, `Status ↑/↓`, `Teacher ↑/↓`), sodass der Sortierpfeil auf jeder Spalte vollständig sichtbar ist und niemals abgeschnitten wird.
  - **Sequenzielle `#`-Nummerierung**: Die Zeilennummerierung in Spalte `#` ist bei jeder Sortierung immer fortlaufend von 1 oben nach unten aufsteigend (1..N). Direktauswahl über `1`–`9` öffnet die jeweilige Zeile.
  - **Hover-Highlighting**: Sortierbare Spalten-Header heben sich bei Maus-Hover subtil mit Akzent-Hintergrund (`datatable--header-hover`) hervor; `#` und `Assignment` sind nicht sortierbar und bleiben unberührt.
  - Neue Unittests `test_table_column_sorting_and_persistent_ids` und `test_tasks_data_table_hover_highlight` in `tests/test_tui_app.py`.
- **Exit Shortcut `Ctrl+C` in TUI mit Eingabefeld-Schutz (Input/TextArea Guard)**:
  - `src/ui/tui_app.py`: `Binding("ctrl+c", "quit_app", "Quit", show=False)` hinzugefügt.
  - **Schutz beim Kopieren in Schriftfeldern**: Befindet sich der Fokus in einem Eingabefeld (`Input`, `TextArea` etc.) oder ist Text markiert, wird das Beenden unterbunden, sodass `Strg + C` regulär für das Kopieren von Text in die Zwischenablage zur Verfügung steht.
  - Button-Tooltip von `❌ Exit` auf `Exit [Q / Ctrl+C]` erweitert.
  - Neuer Unittest `test_ctrl_c_quits_app` in `tests/test_tui_app.py`.
- **Git Cloud-Sync Setup Tutorial (`docs/tutorials/git-sync.md`)**:
  - Ausführliche englischsprachige Schritt-für-Schritt-Anleitung zur Einrichtung von Git Cloud-Sync (Erstellung eines privaten GitHub-Repositories, Generierung eines klassischen Personal Access Tokens (PAT) ohne Ablaufdatum und mit vollen Rechten/Scopes sowie Konfiguration in der Tasks-App).
  - 8 illustrierende Screenshots in `assets/git-sync-tutorial/` (`01_create_new_repo.png` bis `08_copy_token.png`).
- **Setup-Guide-Link im `GitSetupModal`**:
  - Direkter Infotext mit Link auf das Online-Tutorial (`https://github.com/X4nd109/Tasks/blob/main/docs/tutorials/git-sync.md`) im Einrichtungsdialog der TUI (`#git_setup_guide_link`) hinzugefügt.

### Changed
- **Statusleiste Overhaul: Direkt benachbarte Farb-Badges (Pills), Zentrierung & Formatierung**:
  - `src/ui/tui_app.py`: Alle Status-Pills (`To Do`, `Moodle`, `Teams`, `Manual`, `Next`, `Sync`) liegen nun direkt nebeneinander und sind gemeinsam als Gruppe horizontal zentriert.
  - Sämtliche Emojis (`📋`, `🎓`, `👥`, `✏️`, `📝`, `🕒`) wurden entfernt.
  - **Next-Exam Formatierung**: Das Datums-Präfix und die Klammern wurden entfernt (`Next: [Fach] in [Tage]d`).
  - **Sync-Zeit Formatierung**: `Sync: [HH:MM]` zeigt bei heutigen Synchronisationen die Uhrzeit bzw. das Datum des letzten Syncs an.
  - Sämtliche Emojis (📋, 🎓, 👥, ✏️, 📝, 🕒) wurden entfernt.
  - Farbige Pill-Hintergründe implementiert:
    - Moodle: Weiß auf Orange (#fe640b).
    - Teams: Weiß auf Blau (#1e66f5).
    - Manual: Weiß auf Grün (#40a02b).
    - To Do: Dynamisch (Weiß auf Rot bei Überfälligkeit, Schwarz auf Gelb bei offenen Aufgaben, Weiß auf Grün bei 0).
    - Next: Weiß auf Violett (#8839ef).
    - Sync: Heller Text auf Schiefergrau (#45475a).
  - SyncSpinner: Bleibt bei Hintergrundaktivität wie gewohnt am rechten Rand der Statusleiste angedockt.

### Fixed
- **Terminal-Fenstertitel Großschreibung ("Tasks")**:
  - `src/ui/tui_app.py`: `adjust_terminal_size_smart()` setzt den Fenstertitel per Windows-API (`SetConsoleTitleW`) und OSC-Escape-Sequenz (`\033]0;Tasks\007`) nun korrekt auf `"Tasks"` (Großbuchstabe T) anstelle des kleingeschriebenen `"tasks"`.
  - Batch-Skripte `scripts/setup_command.bat` und `scripts/remove_command.bat` auf einheitliche Titel `"Tasks - ..."` harmonisiert.
- **Installer App-Icon Packaging & Terminal-Profil (`assets/app_icon.png`)**:
  - `.gitignore` angepasst, sodass Asset-PNGs (`!assets/*.png`, `!assets/**/*.png`) nicht mehr ignoriert und versioniert werden.
  - `installer/tasks.iss` deklariert `Source: "{#SourceDir}\assets\app_icon.png"` und `.ico` nun explizit unter `[Files]`, um ein Fehlen zur Compile-Zeit unmöglich zu machen.
  - `installer/build_installer.py` ergänzt um `ensure_app_icons()`: validiert `app_icon.png` und `app_icon.ico` im Build-Ziel und erzeugt sie bei Bedarf automatisch aus Fallback-Vektor-Rendern oder per PIL.
  - `scripts/setup_terminal_profile.bat` prüft primär auf `app_icon.png` und fällt bei Nichtvorhandensein robust auf `app_icon.ico` zurück.
  - `scripts/setup_terminal_profile.bat` und `scripts/remove_terminal_profile.bat` normalisieren beide `settings.json`-Schemata (`profiles.list` sowie Legacy-`profiles`-Array) nun explizit: Ein leeres `profiles.list` und vorhandene `profiles.defaults` bleiben unangetastet, statt das Schema zu beschädigen.
  - Das Setup-Skript liefert bei fehlender oder unlesbarer `settings.json` Exit-Code 1 und zeigt im interaktiven Modus eine Fehlermeldung statt der Erfolgsmeldung; das Entfernen lässt die Datei unverändert, wenn kein passendes Profil vorhanden ist.

---

## [2.0.0] - 2026-10-25

### Changed
- **Vollständiges Rebranding von Aufgaben-Detector zu Tasks**:
  - Offizieller Projekt- und Repository-Name auf **Tasks** (`X4nd109/Tasks`) umgestellt.
  - Hauptklasse in `src/ui/tui_app.py` zu `TasksApp` refaktoriert (inkl. `AufgabenDetectorApp = TasksApp` Alias für vollständige Abwärtskompatibilität).
  - TUI-, CLI- und Konsolentitel auf `Tasks` harmonisiert.
  - Lokale Konfigurationsdateien von `aufgaben_detector_*.json` zu `tasks_*.json` migriert (mit automatischer Backup-Kopie vorhandener Daten beim ersten Start).
  - Installer von `installer/aufgaben_detector.iss` zu `installer/tasks.iss` migriert, Ausgabedatei zu `Tasks_Setup.exe` und Installationsverzeichnis zu `{autopf}\Tasks`.
  - Windows Terminal-Profil von `Aufgaben-Detector` auf `Tasks` aktualisiert.
  - **Git-Sync Auto-Cleanup**: `cleanup_legacy_sync_repo_files()` migriert und bereinigt alte `aufgaben_detector_*.json`-Dateien im Remote-Sync-Repository automatisch per `git rm -f`.

### Added
- **Desktop & Installer Icons (`assets/app_icon.ico` & `assets/icons/`)**:
  - 8 moderne, handgefertigte **SVG-Vektor-Icons** mit Fluent-Squircle, transparenten Ecken und leuchtenden Verläufen entworfen:
    - **SVG Konzept 8 (Verfeinert & Neuer Standard ⭐)**: *Quantum Prism Convergence* — 3 Datenlaserstrahlen im 120°-Winkel (Teams nach links oben, Moodle nach rechts oben, WebUntis Mobile-Uhr mit Stift-Zeigern gerade nach unten) mit echten Plattform-Logos und zentralem Kristallprisma ohne extra Emissionsstrahl/Haken.
    - **SVG Konzept 1**: *Radar & Tasks* — Leuchtendes Clipboard mit Checkmarks & Radarstrahl auf Obsidian-Badge.
    - **SVG Konzept 2**: *Cyber Reticle* — Sci-Fi HUD Zieloptik mit Abtastlaser und Dokument.
    - **SVG Konzept 3**: *3D Prism Check* — Geometrischer Facetten-Checkmark mit Sonar-Wellen.
    - **SVG Konzept 4**: *School Hub & Digital Book* — Digitales Buch mit Moodle/Teams/Untis Orbit-Knoten.
    - **SVG Konzept 5**: *Cyber Owl Sentinel* — Low-Poly Cyber-Eule mit Scanner-Linsenaugen.
    - **SVG Konzept 6**: *Terminal & Radar* — Developer-Terminalfenster mit Ampel-Buttons, `> tasks --sync` und Sonar-Grid.
    - **SVG Konzept 7**: *Deadline Shield & Hourglass* — Cyber-Schild mit leuchtender Zeitschleifen-Sanduhr & Haken.
  - Automatischer Build-Generator (`scripts/build_svg_icons.py`), der aus den SVGs pixelgenaue Alpha-PNGs und Multi-Size-Windows-`.ico` (16–256px) rendert.
  - Das verfeinerte Quantum Prism Icon wurde als primäres Standard-Icon in `assets/app_icon.ico` hinterlegt.
- **Inno Setup Installer Shortcut-Icons & Windows Terminal Option**:
  - `installer/tasks.iss` um `SetupIconFile={#SourceDir}\assets\app_icon.ico` erweitert (Installer-EXE trägt nun das App-Icon).
  - Desktop- und Startmenü-Verknüpfungen mit `IconFilename: "{app}\assets\app_icon.ico"` ausgestattet, sodass keine Standard-Batch-Symbole mehr verwendet werden.
  - Neues Checkbox-Feature auf der Fertigstellen-Seite: `[x] Windows-Terminal-Profil mit Logo einrichten (empfohlen)` samt automatischer Deinstallation beim Uninstaller.
  - Vollständig autarke Skripte `scripts/setup_terminal_profile.bat` und `scripts/remove_terminal_profile.bat` (arbeiten rein über PowerShell inline, ohne Python-Abhängigkeit oder `.py`-Hilfsdateien).
- **Persistentes Gedächtnis für `Ai Explain` (Deduplizierung)**:
  - `is_task_ai_explained(task_id)` und `set_task_ai_explained(task_id, explained)` in `src/services/ai_chat_service.py`.
  - Verhindert, dass beim erneuten Klick auf `🤖 Ai Explain [A]` in den Aufgaben-Details dieselbe Aufgabe redundant nochmals an die KI gesendet und doppelt erklärt wird.
  - Das System lädt unmittelbar den bestehenden Chatverlauf und bestätigt dies mit dem dezenten Hinweis `ℹ️ Existing explanation loaded.`.
  - **Automatischer Reset beim Chat-Leeren**: Klickt der Benutzer im AI-Menü auf `🗑️` (Clear Chat) oder drückt `Ctrl+L`, wird auch der Erklärungsstatus zurückgesetzt.
  - **Fehler-Resilienz**: Schlägt eine KI-Anfrage fehl (z. B. fehlender API-Key oder Netzwerkfehler), wird die Aufgabe nicht fälschlich als erklärt markiert.
  - **Rückwirkende Erkennung**: Bereits vor dem Update bestehende Chat-Verläufe mit Erklärungs-Prompts werden rückwirkend erkannt.
- **Windows Terminal Profile mit App-Logo (`scripts/setup_terminal_profile.bat`, `scripts/remove_terminal_profile.bat`)**:
  - Neues Profil `Tasks` (GUID `{b4e2a1c3-7f8d-4a2e-9b1f-3c5d6e7a8b9c}`) in der Windows Terminal `settings.json` mit `assets/app_icon.png` als Icon, Projektordner als Startverzeichnis und `cmd.exe /c "<abs>\run.bat"` als Startbefehl.
  - Bereinigt frühere `Aufgaben-Detector`-Einträge automatisch.

---

## [1.3.0] - 2026-10-24

### Added
- **Native In-App AI Assistant Screen (`AiChatScreen`)**:
  - Neuer Hauptmenü-Button `🤖 Ai` in der unteren Leiste (Shortcut `[I]`) links neben Tests.
  - **Browser-Style Task Tabs**: Schlanke obere Tableiste mit allen aktuell offenen / überfälligen Aufgaben. Inaktive Tabs zeigen platzsparend nur das Schulfach (z. B. `[SWP]`, `[AMEC]`), der aktive Tab expandiert auf `📌 <Fach>: <Aufgabentitel>` und verschiebt die Nachbartabs. Flüssig horizontal scrollbar.
  - **Deep Context & Auto-Attachment Extraction**: Lädt beim Betreten des Chats Aufgaben-Anhänge im Hintergrund herunter und extrahiert Textinhalte aus PDFs (via PyMuPDF `fitz`), Markdown und Quellcode direkt in den System-Prompt der KI. Die KI kennt die vollständige Aufgabenstellung ohne Erklärung durch den Benutzer.
  - **Interaktiver Chat**: Scrollbare Chat-Nachrichten mit Markdown-Formatierung, `Enter`-zum-Senden im Eingabefeld, visuelle Denk-Indikatoren und asynchrone Hintergrund-Abfragen ohne UI-Lag.
  - **Cache-Persistenz & Automatische Bereinigung**: Speichert Konversationen in `cache/ai_chats.json`. Sobald eine Aufgabe als erledigt markiert wird oder nicht mehr offen/überfällig ist, wird ihr Verlauf automatisch aus dem Cache gelöscht. Eigener `🗑️ Clear Chat`-Button pro Aufgaben-Tab.
  - **AI Explain Nahtlos-Integration**: Klick auf `🤖 Ai Explain [A]` in der Aufgaben-Detailansicht wechselt direkt in den AI-Chat auf den richtigen Tab und startet automatisch die Schritt-für-Schritt-Erklärung.
  - **Rich Markdown & Code-Block Rendering**: Assistant-Antworten nutzen jetzt das Textual-`Markdown`-Widget statt reinem Text. Fenced Code Blocks (`MarkdownFence`) und Inline-Code (`MarkdownCodeInline`) erhalten abgesetzte Hintergründe, Rahmen und Akzentfarben – inklusive eigener OLED-Varianten. User-Nachrichten bleiben bewusst als schlichter `Static`-Text.
  - **Animierte 3-Punkte Denk-Anzeige (`Thinking.` $\rightarrow$ `Thinking..` $\rightarrow$ `Thinking...`)**: Sanft pulsierende Textanzeige ohne Emoji-Overhead, gesteuert über einen Textual-Intervalltimer (exakt 2,0 Sekunden pro voller 3-Stufen-Zyklus), die beim Eintreffen der Antwort oder beim Verlassen des Screens automatisch gestoppt wird.
  - **Universelle Theme-Unterstützung für das AI-Menü**: Vollständige Ablösung fester Hex-Codes durch Textuals semantische CSS-Variablen (`$background`, `$surface`, `$panel`, `$primary`, `$border`, `$text`, `$warning`, `$success`, `$error`), wodurch sich der Chat-Screen dynamisch und fehlerfrei an alle 22 Themes (Dark, Light, Retro/Warm und OLED) anpasst.
  - **Intelligente Tab-Wiederherstellung (Zuletzt geöffnete Aufgabe)**: Öffnet automatisch die Aufgabe, die zuletzt aktiv war (bzw. die 1. Aufgabe als Fallback, falls noch nie eine offen war oder die Aufgabe abgeschlossen wurde).
  - **Lesefreundliches Scrollen bei KI-Antworten (Start von oben)**: Bei Eintreffen einer Antwort wird das Chatfenster nicht mehr an das absolute Ende gescrollt, sondern richtet die neue Antwort mit `last_assistant_bubble.scroll_visible(top=True, animate=False)` exakt an der Fensteroberkante aus, sodass man sofort von der ersten Zeile an lesen kann.
  - **Verbessertes Einstellungsmenü `AiConfigModal`**:
    - Presets-Dschungel komplett entfernt: Einfache, direkte Eingabe des API-Keys für Google Gemini oder OpenAI.
    - Automatischer Zeilenumbruch und optimierte Beschriftung (`.ai_hint` mit `width: 100%`), kein Abschneiden mehr am rechten Rand.
    - Automatisches Modell-Laden: Sobald ein API-Key eingefügt wird, triggert die Eingabe automatisch `_fetch_models` ohne manuellen Button-Klick.
    - Dynamisches Modell-Dropdown (`Select`) mit `🔄 Load Models` Button zum Abfragen aller für den Key freigeschalteten Modelle (z. B. Gemini Flash, Pro).
    - Korrigierte Höhe des `🔌 Test Connection` Buttons auf Standardhöhe (`height: 3`) und sprechende Prepayment-Fehlerdiagnose für Google-Cloud-Keys.
  - **Polished `AiChatScreen` Layout & Navigation**:
    - Unnötige Header-Leiste ("TASKS — School Assignment Hub" + Uhrzeit) im AI-Chat-Vollbild entfernt.
    - Start bei Aufgabe 1: Öffnen des AI-Menüs wählt sofort die erste offene Aufgabe aus und zeigt den Chat/Start-Placeholder an.
    - Zuverlässige Chat-Persistenz: Behebung eines Cache-Wipe-Bugs in `_populate_table`, Chats bleiben dauerhaft gespeichert.
    - Symmetrisches Aufgaben-Banner mit oberer und unterer Trennlinie (`border-top` und `border-bottom`), perfekt zentrierter Text.
    - **Reines Aufgaben-Banner ohne Fach**: Die Bannerzeile unter den Tabs zeigt nun ausschließlich den vollständigen Titel der Aufgabe ohne Kurs-Präfix.
    - **Dynamische Auto-Growing Prompt-Eingabe (`ChatInputArea`)**:
      - `Send`-Button entfernt: Schnelles Absenden ausschließlich per `Enter`, die Eingabezeile füllt die gesamte verfügbare Breite aus.
      - **Zuverlässiger Zeilenumbruch mit `Shift + Enter`**:
        - Unterstützung für `shift+enter`, `shift+return`, `ctrl+j`, `ctrl+enter`, `alt+enter` und `shift+linefeed`.
        - Hardware-Win32-Fallback (`is_shift_pressed_win32`) und `patch_win32_event_monitor` Treibersequenz (`\x1b[13;2u`), um auch in Standard-Windows-Konsolen ohne ANSI-Shift-Modus zuverlässig Zeilenumbrüche im Prompt zu ermöglichen.
      - **Symmetrische Rahmentrennung & Höhenverschiebung (`#ai_input_bar`)**:
        - Oberhalb und unterhalb der Eingabeleiste befindet sich jeweils eine dünne Trennlinie (`border-top` und `border-bottom`), wodurch das Schreibfeld leicht angehoben und nach unten sauber abgeschlossen wird.
      - **Fest verankerte Aktions-Buttons (`#ai_input_btn_box`)**:
        - `#btn_ai_clear_chat` aus der oberen Tableiste entfernt und als kompakter, perfekt zentrierter `🗑️`-Button direkt links neben den Back-Button gesetzt (`width: 4; min-width: 4; padding: 0;`).
        - Beide Buttons verbleiben über `Horizontal(id="ai_input_btn_box")` mit `align: right bottom;` unverrückbar rechts unten, selbst wenn das Schreibfeld bei mehrzeiligen Prompts nach oben auf 2 oder 3 Zeilen wächst.
      - Automatisches Wachsen nach oben (1 bis maximal 3 Zeilen) bei längeren Prompts oder Soft-Wrapping.
      - Integrierte dezente Scrollbar ab 4 Zeilen Text.
      - Automatisches Zurücksetzen auf 1 Zeile Höhe nach dem Absenden.
    - **Filter-Synchronisation mit dem Hauptmenü**: Die im AI-Chat angezeigten Aufgaben-Tabs basieren nun direkt auf den im Hauptmenü eingestellten Filtern (Zeitfenster, Fach, Plattform, Status).
    - **Kompakte 1-Zeilen-Tabs & vollflächig farbige Aktivierung**:
      - Die Aufgaben-Buttons und die obere Tableiste wurden auf exakt **1 Zeile Höhe** (`height: 1`) gestrafft.
      - Der aktive Tab wird komplett vollflächig farbig hervorgehoben (`background: #89b4fa; color: #11111b;` im Standard-Theme bzw. `#205ea6; color: #ffffff;` im OLED-Theme), während inaktive Tabs dezent dunkel bleiben.
      - Kein überflüssiger Randstrich oder ungenutzter Freiraum mehr.
    - Vollständige Modularisierung des AI-Personaprompts: Alle hardcoded Schulnamen (`Spengergasse`) aus `_persona()` in `src/services/ai_chat_service.py` entfernt, sodass der Lernassistent neutral für jede Bildungseinrichtung funktioniert.
    - Saubere Kursbezeichnungen in inaktiven Tabs ohne Klammern (z. B. `SESD` statt `[SESD]`).
    - Flüssiger dynamischer Tab-Wechsel mit sofortiger Neuberechnung der Tab-Breiten (`refresh(layout=True)`).
    - Schlankerer Chatverlauf ohne Absender-Header (`🧑 You` / `🤖 AI`); Differenzierung rein über den farbigen Seitenstrich.
    - Exakte Höhenanpassungen verhindern jegliches Abschneiden von Tabs, Clear-, Send- und Back-Buttons.
    - Neuer sichtbarer `↩️ Back [ESC]` Button in der unteren Eingabeleiste zum bequemen Verlassen des Screens.
    - Robuste Tab-Befüllung aus dem TaskManager für alle offenen Aufgaben.
  - Neuer CLI-Workflow: `tasks explain <id>` nutzt bei hinterlegtem API-Key direkt die KI zur Erklärungsausgabe.

### Removed
- **Externes Web-Ai-System**:
  - Das Öffnen von externen Browser-Fenstern und Desktop-Apps via `open_ai_explain` wurde vollständig durch das native In-App Chat-Interface ersetzt.

### Added (Previous)
- **Smart Download Auto-Directory Feature (`DownloadLocationModal`)**:
  - Interaktives, englischsprachiges Auswahlmodal beim Klick auf `📥 Download [D]` in der Aufgaben-Detailansicht.
  - 1-Klick-Hotkeys `[1]`, `[2]`, `[3]` und `[ESC]`:
    - `[1] Linked Course Folder`: Sucht via `DirectoryService.find_matching_directory_for_course` automatisch nach einem verknüpften Ordner für das Schulfach, erstellt einen Unterordner mit dem Aufgabennamen und speichert alle Dateien direkt dort ab. (Deaktiviert mit Hinweis, falls kein Ordner für das Fach verknüpft ist).
    - `[2] Choose Folder Manually...`: Öffnet den nativen Windows Explorer Folder Picker zur freien Pfadauswahl.
    - `[3] Standard Downloads Folder`: Speichert wie gewohnt in `%USERPROFILE%\Downloads\<Fach> - <Aufgabe>\`.
  - Neuer CLI-Flag `tasks download <id> --auto-dir` (`-a`): Automatische Zielordner-Erkennung auch headless im Terminal.
  - `DirectoryService.find_matching_directory_for_course`: Mehrstufige Erkennung über Kurskürzel, Kursvollnamen, Ordner-Basenamen und Wortgrenzen.

### Fixed & Optimized
- **Scrollbares Filter-Menü (`FilterMenuModal`)**:
  - Umstellung des Filter-Hubs von `Vertical` auf `VerticalScroll(id="filter_dialog")` mit `overflow-y: auto;` und `scrollbar-gutter: stable;`.
  - Verhindert das Abschneiden von Filter-Optionen und des Close-Buttons bei begrenzter Fensterhöhe (z. B. 20 Zeilen).
- **Drastische Startzeit-Optimierung (~40% schneller, ca. 800 ms Ersparnis)**:
  - **Lazy Loading**: `excuse_service` (`fpdf2`), `digi4school_service` (`fitz`/`PyMuPDF`, `PIL`, `pytesseract`) und `auth` (`playwright`, `requests`) werden nun on-demand erst beim tatsächlichen Aufruf der jeweiligen Module geladen anstatt top-level beim Start.
  - **Asynchrone Cache-Bereinigung**: `clean_browser_profile_caches()` läuft in `run_tui()` nun als unabhängiger Hintergrund-Thread, wodurch die Festplatten-Traversal (`os.walk`) das Erscheinen der TUI nicht mehr verzögert.

### Removed
- **Vollständige Bereinigung des 'Agent'-Buttons & Harnesses**:
  - Button `🤖 Agent [G]` und `action_agent_open` aus `TaskDetailModal` entfernt.
  - Dialoge `AiAgentConfigModal` und `AiConfigChoiceModal` entfernt; das Einstellungsmenü verlinkt wieder direkt auf `🤖 AI Explain Config`.
  - Headless CLI-Befehl `tasks agent` entfernt.
  - Service `src/services/ai_agent_service.py` und Hilfsfunktionen `load_agent_coding_tool` / `save_agent_coding_tool` in `config.py` gelöscht.

---

## [1.2.1] - 2026-10-22

### Added
- **Globaler 'tasks' Agent-Skill (`skills/tasks/SKILL.md`)**:
  - Extrem schlanker, token-effizienter Skill speziell für autonome Agenten (Antigravity, Claude Code, Cursor).
  - Optimiert für manuelle Aktivierung über Slash-Command `/tasks` (kein unaufgeforderter Prompt-Overhead).
  - Volle Unterstützung aller Textmodus-Befehle (`tasks list`, `tasks show`, `tasks download`, `tasks done`, `tasks books`, `tasks dirs`, `tasks open`, `tasks sync`) mit Fokus auf `--json`.
- **CLI-Befehl `tasks skill [sync|status]`**:
  - `tasks skill sync [--target <pfad>] [--json]`: Installiert oder aktualisiert den Skill direkt im globalen Antigravity Skill-Verzeichnis (`~/.gemini/config/skills/tasks/SKILL.md`).
  - `tasks skill status [--json]`: Überprüft, ob der Skill global installiert und inhaltlich mit dem Projekt-Repository synchron ist.
  - Subcommands und Flag-Aliase: `-skill`, `--skill`.
- **Installer-Konfiguration**:
  - Aufnahme von `skills` in `INCLUDE_DIRS` in `installer/build_installer.py`.
- **Automatisierte Unit-Tests**:
  - Neue Tests für `tasks skill sync` und `tasks skill status` in `tests/test_agent_cli.py`.

---

## [1.2.0] - 2026-10-22

### Added
- **Desktop App Linking in 'Ai Explain' (`AiExplainModal`, `open_ai_explain`)**:
  - Unterstützung für die Verknüpfung lokaler Desktop-Anwendungen (`.exe`, z. B. Gemini Desktop App, ChatGPT Desktop App) direkt in AI Explain.
  - Vordefiniertes Preset `Desktop App` mit nativer Windows Dateiauswahl (`pick_file`) und dynamischer Umschaltung zwischen Web-URL und App-Pfad.
  - Beim Klick auf `Ai Explain [A]` wird der Prompt in die Zwischenablage kopiert und die Desktop-App als Hintergrundprozess gestartet.
- **Vollständige englische Lokalisierung der AI-Konfiguration**:
  - Sämtliche Dialoge, Titel, Labels, Hilfetexte, Buttons und Benachrichtigungen in `AiConfigChoiceModal`, `AiExplainModal`, `AiAgentConfigModal`, `SettingsModal` und `TaskDetailModal` wurden einheitlich auf Englisch umgestellt.
- **'Ai Explain' Button & Integration (`TaskDetailModal`)**:
  - Neuer Button `🤖 Ai Explain [A]` in der Detailansicht von Aufgaben (sowohl Moodle/Teams als auch manuelle Aufgaben), auslösbar per Mausklick oder Shortcut `[A]`.
  - Generiert automatisch einen strukturierten, hochwertigen Prompt für KI-Modelle mit Fach, Titel, Fälligkeit, Lehrkraft, Aufgabenbeschreibung und vollständiger Auflistung aller beigefügten Dateianhänge.
  - Multi-Level Clipboard-Kopieren (automatische Ablage in der System-Zwischenablage via `pyperclip` mit sicherem Windows ctypes / clip.exe Fallback).
  - Öffnet die konfigurierte KI-Webseite im Standard-Browser mit direkter Parameter-Ersetzung für URL-Templates (`{prompt}`).
- **AI Explain Konfigurationsdialog (`AiExplainModal`)**:
  - Schnellauswahl vorkonfigurierter Provider-Vorlagen (Google Gemini, ChatGPT, Perplexity, Custom URL oder Desktop App .exe).
  - Flexible Sprachauswahl für generierte Prompts (German oder English) per 1-Klick-Toggle.
  - Persistente Speicherung in `config.json` unter `ai_explain_config`.
- **Headless Agent CLI Subcommand `tasks explain`**:
  - Aufruf über `tasks explain <id|index> [--lang de|en] [--copy-only] [--no-browser] [--json]`.
  - Vollständige JSON- und Terminalausgabe für autonome Agenten und Skripte.
- **'Agent' Button & Agentic Coding Tool Integration (`TaskDetailModal`)**:
  - Neuer Button `🤖 Agent [G]` (Shortcut `[G]`) in der Aufgaben-Detailansicht.
  - Lädt alle Anhänge und die `angabe.md` in einen frei wählbaren Ordner via Windows Folder Picker herunter.
  - Kopiert automatisch den absoluten Pfad des Projektordners in die Zwischenablage (`Strg+V` im Coding Tool).
  - Startet das konfigurierte Agentic Coding Tool (Antigravity, Cursor, VS Code etc.) als unabhängigen Hintergrundprozess ohne erzwungene Projekt-Neuerstellung.
  - Zeigt einen Hinweis, falls noch kein Coding-Tool in den Einstellungen hinterlegt wurde.
- **Zentralisiertes 'AI Configuration' Einstellungsmenü (`AiConfigChoiceModal` & `AiAgentConfigModal`)**:
  - Zusammenfassung von AI Explain und AI Agent unter dem gemeinsamen Menüpunkt `🤖 AI Configuration` (Shortcut `[7]` / `[A]`).
  - `AiAgentConfigModal`: Auswahl der Coding Tool `.exe` über den nativen Windows Datei-Explorer (`pick_file`) mit Zurücksetzen- und Speicherfunktion.
- **Headless Agent CLI Subcommand `tasks agent`**:
  - `tasks agent <id|index> [--dir <pfad>] [--no-launch] [--json]`.
- 23 neue automatisierte Unit-Tests in `tests/test_ai_explain.py` und `tests/test_agent_feature.py` (Gesamtsuite: 317 Tests, 100 % Erfolgsquote).

### Changed
- **Scrollbarer Dialog & dynamische Scrollbar (`AiExplainModal`, `AiAgentConfigModal`)**:
  - Konfigurationsdialoge wurden auf `VerticalScroll` mit `scrollbar-gutter: stable` und `max-height: 85%` umgestellt, wodurch eine vertikale Scrollbar eingeblendet wird, sobald der Dialoginhalt die Terminalhöhe übersteigt.
  - Einheitliche Beschriftung der Abbruchbuttons auf `↩️ Back [ESC]` (statt „Close“).

### Fixed
- **Button-Abschneiden am unteren Rand von `AiExplainModal`**:
  - Behebt ein Layoutproblem, bei dem die Buttons `Save` und `Back` bei kleineren Terminalhöhen (z. B. 24–25 Zeilen) über den unteren Dialogrand geschoben und abgeschnitten wurden.
- **Unicode-Glyphen in Konsolenanzeige**:
  - Ersetzung problematischer Flaggenemojis im Sprach-Toggle durch standardkonforme Bezeichnungen (`🌐 Language: German (DE)` / `🌐 Language: English (EN)`).

---

## [1.1.0] - 2026-10-21

### Fixed
- **Navigation im ExcuseLetterModal (`btn_el_back`)**:
  - Behoben: Beim Klick auf den `Back`-Button im `ExcuseLetterModal` wurde irrtümlich zusätzlich das Schülerdaten-Konfigurationsmodal (`SchoolConfigModal` / `ExcuseProfileModal`) aufgerufen, anstatt direkt zum `AbsencesScreen` zurückzukehren.

### Added
- **Verspätungen-Filterbutton im Entschuldigungsschreiben (`ExcuseLetterModal`)**:
  - Neuer Toggle-Button `#btn_el_filter_lateness` (`⏳ Hide Lateness: ON` / `⏳ Hide Lateness: OFF`) in der rechten unteren Ecke des Dialogs (Tastenkürzel `[L]`).
  - Standardmäßig aktiv: Blendet Tage mit einer Abwesenheitsdauer unter 50 Minuten (`duration < 50 min`) automatisch aus, sodass standardmäßig nur vollwertige Fehlstunden in der Tabelle und im generierten PDF erscheinen.
  - Mit einem Klick oder Tastendruck auf `[L]` umschaltbar, um bei Bedarf auch reine Verspätungen anzuzeigen und zu entschuldigen.
  - Dynamische Anpassung der Tabellenzeilen, der Auswahlfilter und des Zusammenfassungs-Labels.
- **Exakte Minuten- & Verspätungsberechnung im WebUntis Entschuldigungsschreiben (`ExcuseLetterModal` & PDF)**:
  - **Exakte Abwesenheitsfenster & Dauer (`MissedLesson`)**:
    - `match_absences_with_timetable` ermittelt für Teilabwesenheiten und Verspätungen (z.B. Lehrer erfasst 11 Minuten Verspätung) die exakte minutengenaue Schnittmenge (`start_time`, `end_time`, `duration_minutes`) und behält zeitgleich das originale Stundenfenster (`lesson_start_time`, `lesson_end_time`) bei.
    - Die Tabelle im `AbsencesScreen` zeigt in der Spalte `Time` präzise das verspätete Intervall (z.B. `14:25 - 14:36`) anstelle der vollen 50-Minuten-Stunde.
  - **Exakte Tagessummen & PDF-Generierung**:
    - `get_daily_absence_summaries` summiert die tatsächlichen `duration_minutes` pro Tag (z.B. `0:11` oder `0:25`) statt pauschal `hours * 50`. Die Spalte `Periods` zeigt unverändert die Anzahl der betroffenen Schulstunden (`1 periods`).
    - `create_excuse_pdf` in `src/services/excuse_service.py` parst die minutengenauen Angaben aus `day.duration_str` und berechnet in der Summenzeile die mathematisch exakte Fehlzeit (z.B. `7:16` statt fälschlich `8:20`).
    - `ExcuseLetterModal` in `src/ui/tui_app.py` aktualisiert das Auswahl-Label dynamisch mit Gesamtstunden und -dauer (`Selected: 2 days (2 periods | 0:36)`).
  - 3 neue automatisierte Unit-Tests in `tests/test_untis_service.py` und `tests/test_excuse_service.py` (Gesamtsuite: 294 Tests, 100 % Erfolgsquote).
- **Humanisierte Netzwerk-Fehlerbehandlung bei Moodle-Ausfällen**:
  - `_humanize_request_error` in `src/core/auth.py` fängt rohe `urllib3` / `requests`-Exceptions (`HTTPSConnectionPool`, `NewConnectionError`, `WinError 10061`) ab und übersetzt sie in klare, prägnante Statusmeldungen auf Englisch (`Connection refused: Moodle server is offline or requires school VPN.`, `Connection timeout: Moodle server is not responding.`, etc.).
  - `_is_network_connectivity_error` erkennt Verbindungsabbrüche und nicht erreichbare Server.
- **Fast-Fail ohne Playwright-Verzögerung bei Server-Offline-Zustand**:
  - `login_moodle_direct` überspringt bei Verbindungsfehlern (Connection Refused, Timeout, DNS-Fehler) sofort den trägen 15-Sekunden-Playwright-Browser-Fallback.
  - Reduziert die Wartezeit bei Serverausfällen von bis zu ~27 Sekunden auf ~1,5 Sekunden.
- **TUI Statusanzeige**:
  - `#moodle_status` in `MoodleLoginModal` mit `width: 100%;` und `height: auto;` ausgestattet für zentrierte, mehrzeilige Lesbarkeit ohne Text-Clipping.
- **Bereinigung von Login-Feldern & Platzhaltern**:
  - `TeamsSetupModal`: E-Mail-Eingabefeld wird beim Öffnen des Modals nicht mehr automatisch vorausgefüllt.
  - `MoodleLoginModal` & `UntisSetupModal`: Placeholder im Benutzername-Feld auf neutrales `"Username"` bereinigt (Hardcoded-Beispielkennungen entfernt).
- **Plattform-Deaktivierung & Abmelden im Login-Menü (`LoginChoiceModal`)**:
  - **Kombinierter Action-Button (`Enable` / `Disable` / `🚪 Log Out`)**:
    - Platziert die Toggle- und Logout-Funktionalität auf einem einzelnen Button-Slot am rechten Rand (spart Platz und beseitigt die linke Schalter-Spalte vollständig).
    - Wenn angemeldet: Zeigt `🚪 Log Out` (variant="error", leert Cache und Credentials).
    - Wenn nicht angemeldet & aktiv: Zeigt `Disable` (variant="default", schaltet die Plattform aus).
    - Wenn deaktiviert: Zeigt `Enable` (variant="success", schaltet die Plattform ein).
    - Git Sync: Reine Statuszeile ohne Action-Buttons im Auswahlmenü.
    - Dialogbreite auf schlanke `76` Spalten optimiert ohne jedes Clipping.
    - Deaktivierte Plattformen werden optisch als `[dim]Disabled[/dim]` gekennzeichnet und von Sync sowie LoginReminderModal ignoriert.
- **Login-Prüfung & LoginReminderModal bei jedem Sync**:
  - `get_platform_login_status` und `has_missing_logins` in `src/core/auth.py` bündeln die Authentifizierungsprüfung für Moodle, Teams und WebUntis an einer zentralen Stelle.
  - Neues Modal `LoginReminderModal` (auf Englisch) informiert am Ende jedes automatischen oder manuellen Syncs über nicht angemeldete Dienste mit Status-Badges (`✓ Signed in` vs. `✗ Not signed in`).
  - Direkte Weiterleitung ins Login-Auswahlmenü per `[🔑 Open Login Menu [ENTER]]` sowie Schließen per `[Dismiss [ESC]]` (erscheint beim nächsten Sync erneut, falls weiterhin Logins fehlen).
  - Erscheint nur auf dem Haupt-Dashboard, um laufende Aktionen in Einstellungen oder Detaildialogen nicht zu unterbrechen.
- 9 neue automatisierte Unit-Tests in `tests/test_auth_logins.py` und `tests/test_tui_app.py` (Gesamtsuite: 283 Tests, 100 % Erfolgsquote).

---

## [1.0.11] - 2026-10-21

### Added
- **Browserloses HTTP-Moodle-Login (`login_moodle_http`)**:
  - Moodle-Authentifizierung läuft primär über direkte HTTP-Requests (`requests.Session` mit dynamischer `logintoken`-Extraktion und Form-POST).
  - Funktioniert in unter 0,3s ohne vorinstallierten Playwright-Chromium-Browser (behebt Login-Fehlschläge auf Geräten, auf denen nur `pip install -r requirements.txt` ausgeführt wurde).
  - Automatischer Browser-Fallback mit System-Browsern (`chrome`, `msedge`, `chromium`) nur noch als sekundäre Stufe.
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

---

## [1.0.10] - 2026-10-21

### Added
- **Sync Performance & TUI Responsiveness Boost**:
  - `SyncSpinner` Animationsfrequenz von 80 ms (12,5 FPS) auf schonende 250 ms (4 FPS) reduziert, um Windows ConPTY ANSI-Terminalbelastung und Asyncio Event-Loop Verstopfung zu beheben.
  - Entkoppelte UI-Statistikaktualisierung (`update_info_bar`) mit 0,8 s Throttling für `refresh_table`, sodass schnelle Plattform-Syncs die `DataTable` nicht mehrfach pro Sekunde verwerfen.
  - Nicht-blockierendes Caching in `TaskManager.save_cache()` (Festplattenzugriff außerhalb des Cache-Locks) und gebündeltes Schreiben im `_prefetch_worker` (alle 5 Aufgaben statt nach jeder einzelnen).
  - Playwright Headless Chromium Optimierung mit `--disable-gpu`, `--disable-dev-shm-usage` und `--renderer-process-limit=2` für ressourcenschonenden Teams-Sync.
- **Automatisches Wiederherstellen der Getting-Started-Aufgabe bei Updates**:
  - `TaskManager._check_and_apply_version_update` erkennt Versions-Updates und stellt die Setup-Aufgabe (`manual_welcome_setup_guide`) automatisch wieder her.
  - Falls die Aufgabe zuvor als erledigt markiert oder gelöscht (`deleted_manual_ids`) wurde, wird sie ent-löscht, auf den Status `Open` zurückgesetzt und ganz oben platziert.
- **In-Terminal Update-Loop in `run.bat`**:
  - Fängt den Update-Exit-Code `42` sowie `%TEMP%\AufgabenDetector_Update\pending_update.txt` nativ im aktiven Konsolenfenster ab.
  - Führt das Setup stillschweigend (`start /wait`) im gleichen Terminal aus und startet `main.py` ohne externe Fenster oder Unterbrechungen neu.

### Changed
- **Getting Started Aufgabe auf Englisch & Button-basiert**:
  - Sämtliche Hotkey-Angaben wurden durch präzise Verweise auf die realen UI-Buttons ersetzt (`⚙️ Settings`, `⚙️ School & Student Config`, `🔑 Login`, `👥 Teams Login`, `🎓 Moodle Login`, `📅 WebUntis Login`, `🐙 Git Cloud-Sync`, `🔄 Sync`, `✓ Mark as Completed`, `🗑️ Delete`).
  - Vollständige Überarbeitung der Aufgabenbeschreibung in verständlichem Englisch.
- **Keine redundante Bibliotheksinstallation bei Updates**:
  - `setup.bat /silent` wurde vollständig aus dem Update-Prozess entfernt, da `dependency_checker.py` fehlende Bibliotheken automatisch beim Start von `main.py` prüft und bereitstellt.
  - Entfernung von `powershell`-Aufrufen beim Update-Prozess.

---

## [1.0.9] - 2026-10-20

### Added
- **Tesseract OCR-Optimierung für Fett- und Unterstrichenen Text**:
  - **Sauvola Binarisierung (`thresholding_method=2`)**: Lokale adaptive Schwellenwertbildung verhindert das Zulaufen fetter Buchstaben und isoliert Unterstreichungen sauber von Grundlinien.
  - **Nicht-lineare Strichdicken-Normierung (`classify_nonlinear_norm=1`)**: Skaliert Buchstabenzüge basierend auf Strichdichte, sodass fette Wörter und Überschriften präzise klassifiziert werden.
  - **Unterstreichungstrennung (`textord_restore_underlines=1` & `textord_underline_threshold=0.5`)**: Trennt horizontale Unterstreichungen gezielt von Unterlängen (`g`, `j`, `p`, `q`, `y`).
  - **Sanftes Kanten-Sharpening**: `ImageFilter.UnsharpMask(radius=1.2, percent=115, threshold=3)` vor der Übergabe an Tesseract schärft Kanten für maximale OCR-Präzision.
- **Digi4School Interaktive Seitenauswahl & 2-Thumb Range-Slider**:
  - **Automatische Buch- & Seitenzahlerkennung**: Neue Methode `Digi4SchoolService.inspect_book` loggt sich headless im Hintergrund ein und liest Buchtitel sowie die exakte Gesamtzahl der Buchseiten aus.
  - **Ladedialog `Digi4SchoolDetectModal`**: Kurze Ladeanzeige (*"Connecting to Digi4School and detecting book pages..."*) mit Lade-Spinner und Abbrechen-Möglichkeit.
  - **Menü `Digi4SchoolPageRangeModal`**: Kompaktes Auswahldialog-Layout mit Buchtitel, Zugangscode, 2-Thumb-Slider, synchronisierten Ziffernfeldern und zentriertem *All*-Button.
  - **Interaktives `TwoThumbRangeSlider` Widget**:
    - Stellt eine visuelle Schiene mit 2 Schiebern (Startseite und Endseite) im Catppuccin Mocha-Design dar.
    - Volle Mausbedienung (Klick auf Schiene zur Positionierung des nächstgelegenen Griffs sowie Halten und Ziehen per Drag & Drop).
    - Tastaturnavigation mit Pfeiltasten (`Left`/`Right`, `Shift` für 10er-Schritte, `Tab`/`1`/`2` zum Wechseln des aktiven Schiebers, `Home`/`End`).
  - **Synchronisierte Ziffernfelder**: Zwei Eingabefelder (*"From Page"* und *"To Page"*) zur Direkteingabe; bidirektional in Echtzeit mit dem Schieberegler synchronisiert.
  - **Range-Download & OCR**: Nahtlose Weitergabe des gewählten Seitenbereichs (z. B. `20-50`) an `Digi4SchoolProgressModal` und `Digi4SchoolService.download_book`.
  - 12 neue automatisierte Unit-Tests in `tests/test_page_range_slider.py` (insgesamt 264 Tests in der Gesamtsuite mit 100 % Erfolgsquote).

---

## [1.0.8] - 2026-10-20

### Fixed
- **Main Task Dashboard Formatierung, Sync-Uhrzeit & Spaltenpriorisierung (4K & 1440p Polish)**:
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

## [1.0.7] - 2026-10-20

### Fixed
- **UpdateReminderModal Englisch-Lokalisierung, Button-Layout & Text-Clipping**:
  - **Vollständige englische Lokalisierung**: Alle deutschen Texte, Versionsangaben (`Current Version`, `Latest Version`), Hinweistexte, Fortschrittsmeldungen, Fehlermeldungen und Button-Beschriftungen auf Englisch umgestellt.
  - **2-Zeilen-Button-Layout**: Der `Later [ESC]`-Button wurde unter den beiden Hauptaktionen (`Install Update Now` und `View in Browser`) zentriert platziert, damit kein Button mehr am Dialogrand abgeschnitten wird.
  - **Analoges Error-Buttons-Layout**: Auch bei Downloadfehlern sind die Aktionen nun 2-zeilig aufgeteilt (`Try Again` + `Download in Browser` in Zeile 1, `Close [ESC]` zentriert in Zeile 2).
  - **Hinweistext-Clipping behoben**: `width: 100%` auf `#update_hint` gesetzt für sauberen automatischen Mehrzeilenumbruch, und die Dialogbreite für harmonische Abstände leicht auf `70` Spalten erweitert.
  - **Rich Markup-Absicherung**: `\[ESC]`-Klammern in Button-Labels maskiert, damit Textuals Markup-Parser Tastatur-Shortcuts nicht verschluckt.
  - Neuer automatisierter Test `test_update_reminder_modal_layout_and_english_texts` in `tests/test_update_service.py` (insgesamt 250 Tests in der Gesamtsuite mit 100 % Erfolgsquote).

---

## [1.0.6] - 2026-10-20

### Fixed
- **Main Task Dashboard Vollbreiten-Spaltenverteilung & Beseitigung der horizontalen Scrollleiste**:
  - Dynamische proportionale Breitenberechnung aller 7 Spalten (`#`, `Platform`, `Subject`, `Assignment`, `Due Date`, `Status`, `Teacher`) basierend auf der tatsächlichen Fenster-/Container-Breite analog zum Exams-Screen.
  - Spaltenbreiten werden explizit auf den `DataTable`-Spalten gesetzt (`col.width`, `auto_width = False`), wodurch die Tabelle 100 % der Fensterbreite ausfüllt und horizontaler Überlauf sowie die Scrollleiste vollständig eliminiert werden.
  - Spalte *Assignment* erhält den flexiblen Mittelteil der Breite und wird bei Überschreitung sauber mit `...` (3 ASCII-Punkte) gekürzt (z. B. `OverTheWire/Bandit_0-6_Linux...`).
  - Zeilenumbrüche und überschüssige Whitespaces werden vor der Darstellung bereinigt, um Mehrzeiligkeit oder Formatierungsbrüche zu verhindern.
  - Reagiert sofort auf Terminalgrößenänderungen via `on_resize(term_w_override=...)`.
- **Moodle-Status-Negationsprüfung**:
  - Negationsabsicherung in `Task.is_completed` und `format_status_english`: Texte wie *„Bisher wurden keine Aufgaben abgegeben“* oder *„nicht abgegeben“* werden nicht mehr fälschlicherweise durch das Teilwort *„abgegeben“* als erledigt gewertet, sondern bleiben korrekt als `Open` erhalten.
- 3 neue automatisierte Tests in `tests/test_tui_app.py` (insgesamt 249 Tests in der Gesamtsuite mit 100 % Erfolgsquote).

---

## [1.0.5] - 2026-10-20

### Added
- **Automatische 1-Klick In-App Update-Funktion (`UpdateReminderModal`)**:
  - Direkter Download des offiziellen Release-Installers (`AufgabenDetector_Setup.exe`) innerhalb des Modals mit Textual `ProgressBar`, Byte-/MB- und Prozentanzeige sowie Abbruchmöglichkeit (`cancel_event`).
  - Robuste Fehlerbehandlung mit Retry- und Fallback-Button ("Im Browser herunterladen").
  - **Zielordner- & Konfigurationserhalt**: Installation erfolgt zwingend im aktuellen Programmverzeichnis (`WORKSPACE_DIR`); `config.json`, `data/`, Caches und persönliche Einstellungen bleiben unberührt.
  - **Keine PATH-Modifikation**: Durch Übergabe von `/NOTASKS=1` und `/UPDATE=1` an Inno Setup (`aufgaben_detector.iss`) wird `setup_command.bat` übersprungen und die `PATH`-Variable nicht verändert.
  - **Automatisches Abhängigkeiten-Update**: `setup.bat /silent` prüft und installiert neue pip requirements im Hintergrund ohne blockierende Pause-Abfragen.
  - **Entkoppelter Handoff & Auto-Neustart**: `%TEMP%\AufgabenDetector_Update\apply_update.cmd` wartet auf Beenden des Python-Prozesses, führt die Aktualisierung geräuschlos (`/VERYSILENT`) durch und startet `run.bat` neu.
  - 5 neue Unit- und UI-Tests in `tests/test_update_service.py` (insgesamt 246 Tests in der Gesamtsuite mit 100 % Erfolgsquote).
- **Per-Monitor DPI-Awareness v2 & Native Windows Explorer Dialoge**:
  - Neues Modul `src/core/win_dialogs.py` mit `enable_high_dpi_awareness()`, `pick_file()` und `pick_directory()`.
  - Aktiviert `SetProcessDpiAwarenessContext(HANDLE(-4))` (Per-Monitor DPI Aware v2) direkt beim Start von `main.py`, `src/main.py` und der TUI (`AufgabenApp.on_mount`) sowie vor jedem Dialogaufruf.
  - Echte native Windows COM `IFileOpenDialog`-Instanzen für Dateiauswahl (`/link` in Schulbüchern) und moderne Ordnerauswahl mit `FOS_PICKFOLDERS` (`/link` in Directories) mit nativer Schnellzugriff- und Adressleisten-Navigation.
  - Gestochen scharfe Text-, Icon- und UI-Darstellung auf 4K-, 1440p- und Multi-Monitor-Setups ohne bilineare DWM-Bitmap-Streckung („Low-Res-Explorer-Effekt“).
  - Graceful Fallback Cascade auf DPI-aware Tkinter (`filedialog`) und PowerShell Forms Dialoge bei Nicht-Windows-Systemen oder COM-Ausfällen.
  - 11 neue automatisierte Tests in `tests/test_win_dialogs.py`.

### Fixed
- **SettingsModal Button-Clipping, Abstände & Fensterproportionen**:
  - `ensure_terminal_window_size`: Startbreite auf 123 Spalten und Mindesthöhe dynamisch auf 33 Textzeilen skaliert (`effective_min_h`), angepasst an Windows Terminal und Per-Monitor DPI Awareness v2.
  - `SettingsModal`: Container `#settings_dialog` auf `VerticalScroll` umgestellt, Button-Abstände (`margin-bottom: 1;`, `padding: 1 2;`) exakt an `FilterMenuModal` angeglichen und maximale Höhe auf `96%` erweitert. Der `[↩️ Close [ESC]]`-Button bleibt jederzeit voll sichtbar und erreichbar.
- **ExamsScreen Vollbreiten-Spaltenverteilung & Beseitigung des rechten Leerraums**:
  - Dynamische proportionale Breitenberechnung aller 9 Spalten (`#`, `Type`, `Subject`, `Date`, `Time`, `Topic / Notes`, `Teacher`, `Room`, `Countdown`) basierend auf der tatsächlichen Fenster-/Container-Breite.
  - Spaltenbreiten werden direkt auf den `DataTable`-Spalten gesetzt (`col.width`, `auto_width = False`), wodurch die Tabelle nahtlos bündig bis an den rechten Rand abschließt und der blaue Zeilen-Cursor die gesamte Fensterbreite hervorhebt.
  - Thema / Notizen (`Topic / Notes`) erhält dynamisch bis zu 60 % des zusätzlichen Freiraums (z. B. 60+ Zeichen auf breiten Bildschirmen), wodurch lange Titel und Notizen ohne unnötige Abkürzung dargestellt werden.
  - Berücksichtigt Puffer für vertikale Scrollbars und reagiert sofort auf Fenster-Resize (`on_resize`).
  - Neuer Test `test_exams_screen_full_width_column_distribution_and_resize` in `tests/test_untis_exams.py` (insgesamt 247 bestandene Tests).
- **FilterMenuModal Bereinigung**: Die redundante Textzeile (`#filter_info`) unter dem Titel („Status: ... | Due Window: ...“) wurde entfernt, da die aktiven Filterzustände bereits direkt auf den jeweiligen Farb-Buttons übersichtlich dargestellt werden.
- **Dynamische Datumsabsicherung in `test_untis_exams.py`**: Ersetzung des statischen Testdatums durch relative `timedelta`-Offsets zur Vermeidung von Datumsüberläufen bei zukünftigen Testläufen.

---

## [1.0.4] - 2026-10-19

### Added
- **Directories Tab in Unified CommandPalette**: Neuer 3. Tab in der `Backspace`-Palette (`Courses` ➔ `Schoolbooks` ➔ `Directories` via `Tab`), um Ordner direkt mit nativem Windows-Auswahldialog (`/link`) zu verknüpfen und per `Enter` im Windows Explorer zu öffnen.
- **Headless CLI für Verzeichnisse**: Neue Unterbefehle `tasks dirs [list|open|add|remove] [--json]`.
- **Lokale Verzeichnis-Persistenz**: Speicherung in `data/directories.json` (automatisch via `.gitignore` von Git-Tracking ausgeschlossen).
- **OLED Theme**: Neues Theme `oled` mit reinem Tiefschwarz (`#000000` Background/Surface/Panel) kombiniert mit Flexoki-Farbakzenten.
- **Windows-Tastatur-Shortcuts für Texteingaben**: Umfassende Textbearbeitungs-Shortcuts (`Ctrl+A`, `Pos1`, `Ende`, `Shift+Pos1`, `Shift+Ende`, `Ctrl+Left/Right`, `Shift+Ctrl+Left/Right`, `Ctrl+Delete`, `Ctrl+Backspace`) über alle `Input`- und `TextArea`-Widgets.
- **5-Stufen-Absicherung für `Ctrl+Backspace`**:
  - Stufe 1: ConPTY Win32 Driver Event-Patch für Windows Terminal.
  - Stufe 2: Hardwarenahe OS-Abfrage via `GetAsyncKeyState(VK_CONTROL)` (`0x11`).
  - Stufe 3: Palette-Guard in `UnifiedCommandInput.action_delete_left`.
  - Stufe 4: App-Level Menü-Guard gegen versehentliches Palette-Öffnen.
  - Stufe 5: Fallback Terminal-Bindings (`ctrl+backspace`, `ctrl+w`, `ctrl+h`).
- 19 automatisierte Tests für Verzeichnisse, OLED-Styling und Keyboard-Shortcuts (insgesamt 230 Tests).

### Changed
- **OLED UI Polish**: Rahmen (`border`) von `Header`, `#info_bar` und `#button_bar` im OLED-Theme entfernt, um vertikales Clipping zu verhindern.
- **Button-Höhen normiert**: Feste Höhe von 3 Zeilen (`height: 3`) für alle Dialog- und Modal-Buttons im OLED-Theme für saubere Textzentrierung.
- **Tabellen-Header**: Tabellen-Spaltentitel auf kontrastreiches Weiß (`#ffffff`, bold) umgestellt.
- **Tabellen-Fokus**: Verhindert das Aufhellen des tiefschwarzen Hintergrunds beim Fokussieren (`Tab`) durch Textuals Standard-Fokus-Tint.

### Fixed
- Versehentliches Schließen der `UnifiedCommandPalette` beim Löschen markierter Texte oder beim Drücken von `Ctrl+Backspace`.

---

## [1.0.3] - 2026-10-19

### Added
- **Asynchroner Update-Checker**: Zero-Login GitHub REST API Versionsprüfung mit SemVer-Parser (`src/services/update_service.py`).
- **UpdateReminderModal**: Start-Modal bei neueren Releases mit Anzeige der aktuellen und neuen Version sowie 1-Klick-Download im Browser (`Enter`) und Abbrechen (`ESC`).
- **Versions-Badge in Settings**: Pinned Versions-Badge (`v1.0.3`) in der rechten oberen Ecke des `SettingsModal` (`[O]`).
- **Non-blocking Daemon-Thread**: Update-Prüfung erfolgt im Hintergrund; sofortiger Offline-Start (`< 0.1s`) bleibt vollständig erhalten.
- 9 automatisierte Unit- und UI-Tests in `tests/test_update_service.py` (insgesamt 206 Tests).

---

## [1.0.2] - 2026-10-19

### Added
- **Dependency Pre-flight Checker**: Zero-Dependency Vorabprüfung in `src/core/dependency_checker.py` mit ASCII-Warnbanner und interaktiver Auto-Installation (`[Y/n]`).
- **Theme-Bibliothek auf 21 Themes erweitert**: Gruvbox, Rosé Pine Varianten, Solarized, Catppuccin Varianten, Atom One, Flexoki, ANSI vintage u. v. m.
- **Theme-Favoriten (`⭐`) per Rechtsklick**: Favoriten-Verwaltung in `data/config.json`, Sortierung an den Anfang der Theme-Listen in `ThemeSelectModal` und Command Palette.
