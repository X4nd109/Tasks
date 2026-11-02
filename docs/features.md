# Feature & UI Element Catalog — Tasks

> **Zweck**: Eindeutige, token-effiziente Begriffswelt für Buttons, UI-Elemente und Features zwischen Benutzer und Agent.  
> **Regel**: Maximal 1 prägnanter Satz pro Eintrag. Exakte Bezeichnungen gemäß TUI- und CLI-Codebase.

---

## 1. Screens & Hauptansichten

| Element / View | Typ | Kurzbeschreibung |
| :--- | :--- | :--- |
| `Main Task Dashboard` | Screen | Farbcodierte Haupttabelle aller offenen und fälligen Moodle- und Teams-Aufgaben (`TasksApp`) mit priorisierten Spalten, interaktiver Spaltensortierung (Mausklick auf Spaltenheader mit 2-Wege-Toggle `↑`/`↓`, sequenzieller 1..N Zeilennummerierung und Hover-Highlighting) und zentrierter Status-Pill-Leiste. |
| `Tests & Exams Screen` (`[E]`) | Screen | WebUntis Prüfungskalender mit dynamischer Vollbreiten-Verteilung aller 9 Spalten ohne rechten Leerraum und horizontalem Scrollbar-Puffer. |
| `CommandPalette` (`Backspace` / `/`) | Overlay | Schnellsuchleiste bündig an der Fensteroberkante (`margin-top: 0`) mit 3 festen Tab-Boxen nebeneinander (*Courses* links, *Schoolbooks* Mitte, *Directories* rechts); Tab-Umschaltung über `Tab` (vorwärts), `Shift+Tab` (rückwärts) sowie direkten Mausklick auf jede der Boxen; aktiver Tab in Akzentfarbe (Courses = Cyan, Books = Rot, Directories = Grün) mit weißem Text, inaktive Tabs dezent ausgegraut; `Backspace` bei leerer Leiste schließt das Menü; behält Suchtext beim Umschalten. |
| `Trash / Hidden Screen` (`[G]`) | Modal | Übersicht aller ausgeblendeten oder gelöschten Aufgaben mit Wiederherstellungsoption (`TrashModal`). |

---

## 2. Modals & Dialoge

| Dialog / Modal | Typ | Kurzbeschreibung |
| :--- | :--- | :--- |
| `TaskDetailModal` | Modal | Zeigt formatierte Angabe (`angabe.md`), Metadaten und Aktions-Buttons für eine gewählte Aufgabe. |
| `AddTaskModal` (`[A]`) | Modal | Eingabemaske zur manuellen Erstellung eigener Hausübungen oder Notizen mit Fälligkeitsdatum. |
| `FilterMenuModal` (`[F]`) | Modal | Kompakter, scrollbarer Filter-Dialog für Status, Fach, Zeitfenster und Plattform mit Statusanzeige direkt auf den Buttons. |
| `SubjectFilterModal` | Modal | Listen-Auswahl zur Einschränkung der Tabelle auf ein spezifisches Schulfach. |
| `ExcuseLetterModal` (`[U]`) | Modal | Fehlstunden-Übersicht mit Stundenplan-Abgleich und 1-Klick-PDF-Export für die Schule. |
| `ExamDetailModal` | Modal | Zeigt Prüfungsdetails, ermöglicht das Bearbeiten persönlicher Stoff-Notizen (`exam_notes.json`) und bietet 1-Klick-Zugriff auf den verknüpften Fachordner (`📁 Open Folder [F]`). |
| `AddExamModal` | Modal | Formular zum Eintragen manueller Prüfungstermine mit nativer Wochentagserkennung. |
| `SettingsModal` (`[O]`) | Modal | Scrollbarer Konfigurationsdialog mit Versionsanzeige in der oberen rechten Ecke (`v2.3.4`), Themes, Logins und Schülereinstellungen. |
| `NotificationConfigModal` | Modal | Untermenü in den Settings zur Konfiguration von nativen Windows-Benachrichtigungen für neue Aufgaben, Fälligkeitswarnungen und täglichen Prüfungs-Erinnerungen (mit konsistenter Rückkehr zu Settings beim Verlassen). |
| `TrayConfigModal` | Modal | Konfigurationsdialog für Hintergrundbetrieb, Minimieren in den System Tray, Windows-Autostart und automatisches Synchronisationsintervall. |
| `DownloadLocationModal` | Modal | Englischer Auswahldialog für das Download-Ziel mit Hotkeys `[1]` (Auto-Dir Kursordner), `[2]` (Manuell via Windows Explorer), `[3]` (Standard Downloads-Ordner) und `[ESC]` (Abbrechen). |
| `AiChatScreen` (`[I]`) | Screen | Vollwertiges In-App AI-Chat-Interface mit Browser-Style Tab-Leiste für alle offenen Aufgaben, dynamischer Tab-Expansion, Unterhaltungsverlauf, PyMuPDF-Textextraktion aus Anhängen, konstanter 3-Zeilen-Schreibleiste mit Zeilensprung (Mitte -> Oben/Mitte -> Oben/Mitte/Unten -> Bottom-Scroll), 3-Zeilen Back-Button (`↩️ Back`) unten rechts mit bündig darüber gestapeltem 1-Zeilen Clear-Button (`🗑️ Clear`, Tastenkürzel `[Ctrl+L]`), vorgeschaltetem Sicherheits-Bestätigungsdialog (`ClearChatConfirmModal`) und vollständiger Entfernung der oberen Toolbar zur Rückgewinnung von Chat-Zeilen sowie direkter Gemini / OpenAI REST-Anbindung. |
| `AgentHubModal` | Modal | Zentrales englischsprachiges Zwischenmenü für AI Agents mit Optionen `🛠️ Setup Guide` (öffnet `AgentSkillSetupModal`) und `📊 Skill State` (dynamisch ausgegraut, wenn kein Skill installiert ist). |
| `AgentSkillStatusModal` | Modal | Status- und Verwaltungsdialog für den AI Agent Skill mit Anzeige des Zielpfads, Auto-Update-Status und Aktionen zum Verschieben (`📦 Move Skill`) oder Löschen (`🗑️ Remove Skill`). |
| `ConfirmSkillRemovalModal` | Modal | Sicherheits-Bestätigungsdialog vor dem Löschen der `SKILL.md` und Deaktivieren der automatischen Updates. |
| `AgentSkillSetupModal` | Modal | 3-stufiger interaktiver Einrichtungs-Assistent auf Englisch zur Konfiguration und zum schlüssellosen On-Demand-Download des Tasks Agent Skills direkt von GitHub. |
| `ClearChatConfirmModal` | Modal | Englischer Sicherheits-Bestätigungsdialog vor dem Leeren des Chat-Verlaufs (`🗑️ Clear` / `Cancel [ESC]`). |
| `AiConfigModal` / `AiExplainModal` | Modal | Konfigurationsdialog für den AI Assistant mit Provider-Auswahl (Google Gemini Free-Tier, OpenAI-kompatibel), API-Key, Modell-Name, Base-URL, Test-Verbindung-Button und Sprachumschalter (German/English). |
| `UpdateReminderModal` | Modal | Popup-Erinnerung bei neueren GitHub-Releases (auch via Windows Toast & `tasks://update`), In-App-Download mit Fortschrittsbalken und Start des isolierten Catppuccin-PowerShell-Update-Runners (`update_runner.ps1`). |
| `LoginChoiceModal` (`[L]`) | Modal | Zentrales Auswahlmenü für Anmeldungen bei Moodle, Microsoft Teams und WebUntis. |
| `TeamsSetupModal` | Modal | Geführter Teams-Login via Playwright-Chromium mit Passkey-, 2FA- oder Kennwort-Unterstützung. |
| `MoodleLoginModal` | Modal | Eingabe von Moodle-Benutzername (oder E-Mail mit automatischem Domain-Stripping) und Passwort mit blitzschneller HTTP-Authentifizierung und Fehleranzeige. |
| `UntisSetupModal` | Modal | Konfiguration von WebUntis-Schulname (Standard: spengergasse, Domain-Bereinigung & API-Suche), Benutzer und Passwort mit exakter Fehlerrückmeldung. |
| `GitSetupModal` | Modal | Einrichtungsdialog für cloudbasierten Git-Sync über privates Repository mit Token-Verschleierung und integriertem Link zum Setup-Guide (`docs/tutorials/git-sync.md`). |
| `SchoolbookUrlModal` | Modal | Dialog zur Vergabe von Buchtitel und Web-URL für digitale Schulbücher. |
| `Digi4SchoolDownloadModal` | Modal | Anmelde- und Zugangscode-Eingabe für den automatischen Digi4School-Buchdownload. |
| `Digi4SchoolDetectModal` | Modal | Ladedialog zur automatischen Vorab-Erkennung von Buchtitel und Gesamtseitenzahl über Digi4School. |
| `Digi4SchoolPageRangeModal` | Modal | Grafischer Dialog zur flexiblen Auswahl des Seitenbereichs mit 2-Thumb-Slider (`TwoThumbRangeSlider`), synchronisierten Ziffernfeldern und Schnellwahl. |
| `Digi4SchoolProgressModal` | Modal | Fortschrittsanzeige mit Multi-Core OCR-Status, Seitenbereichsanzeige, verbleibender Zeit (ETA) und Abbruch-Option. |

---

## 3. Buttons & Interaktions-Elemente

| Button / Control | ID / Key | Kurzbeschreibung |
| :--- | :--- | :--- |
| `Open in browser` | `[O]` / `btn_open_browser` | Öffnet die offizielle Abgabeseite der Aufgabe direkt im Standard-Webbrowser. |
| `Download files` | `[D]` / `btn_det_download` | Öffnet das englischsprachige `DownloadLocationModal` zur Zielwahl (Auto-Dir [1], Explorer [2], Downloads [3]). |
| `Open Folder` | `[F]` / `btn_open_exam_folder` | Öffnet in `ExamDetailModal` den im System verknüpften lokalen Ordner für das Schulfach des Tests direkt im Windows Explorer. |
| 🤖 Agent | [Alt+A] / tn_ai_agent_skill | Öffnet im AiChatScreen das zentrale Hub-Menü (AgentHubModal) zur Verwaltung und Einrichtung des AI Agent Skills. |
| Setup Guide | tn_hub_setup | Öffnet im AgentHubModal den 3-stufigen Setup-Wizard (AgentSkillSetupModal). |
| Skill State | tn_hub_state | Öffnet im AgentHubModal das Status- und Verwaltungsmodal (AgentSkillStatusModal); dynamisch ausgegraut (disabled), wenn noch kein Skill installiert ist. |
| Move Skill | tn_status_move | Öffnet in AgentSkillStatusModal den Ordnerdialog und verschiebt die SKILL.md mitsamt Auto-Update-Pfad an das neue Ziel. |
| Remove Skill | tn_status_remove | Öffnet die Bestätigung (ConfirmSkillRemovalModal), löscht SKILL.md von der Festplatte und entfernt den Pfad aus den automatischen Updates. |
| `Ai Explain` | `[A]` / `btn_det_ai_explain` | Schließt die Aufgaben-Details, wechselt direkt in den In-App AI-Chat auf den Tab dieser Aufgabe und startet automatisch die Schritt-für-Schritt-Erklärung (dedupliziert: bereits erklärte Aufgaben öffnen direkt den bestehenden Chat, Reset bei Clear Chat). |
| `AI Configuration` | `[7/A]` / `btn_set_ai_explain` | Öffnet in den Settings den Konfigurationsdialog (`AiConfigModal`) für KI-Provider, API-Key, Modell, Base-URL und Verbindungstest. |
| `Notifications` | `[9/N]` / `btn_set_notifications` | Öffnet das Untermenü `NotificationConfigModal` zur Konfiguration von Windows Toast-Benachrichtigungen (Neue Aufgaben, Fälligkeitswarnungen, tägliche Prüfungs-Erinnerungen). |
| `System Tray & Autostart` | `[8/T]` / `btn_set_tray` | Öffnet `TrayConfigModal` für Hintergrund-Betrieb, Autostart und automatisches Sync-Intervall (`5min`, `10min`, `30min`, `1h`, `never`). |
| `Sort Column Header` | Klick auf Spalten-Header | Interaktives 2-Wege-Sortieren der Haupttabelle nach `Platform`, `Subject`, `Due Date`, `Status` oder `Teacher` (Aufsteigend `↑` / Absteigend `↓`). Automatische Start-Sortierung mit `Due Date ↓`, sichtbare Pfeile auf allen Spalten, sequenzielle 1..N Nummerierung. Spalten `#` und `Assignment` bleiben unberührt. |
| `Toggle status` | `[E]` / `btn_toggle_status` | Schaltet den Erledigt-Status einer Aufgabe zwischen offen und abgeschlossen um. |
| `Hide / Delete` | `[L]` / `btn_delete_task` | Verschiebt eine Aufgabe in den lokalen Papierkorb (`deleted_tasks.json`). |
| `Restore` | `[W]` / `btn_restore_task` | Stellt eine gelöschte Aufgabe aus dem Papierkorb wieder her. |
| `Generate Excuse PDF` | `btn_generate_excuse` | Erzeugt das druckfertige Entschuldigungsschreiben als PDF und öffnet den System-Betrachter. |
| `Hide Lateness` | `[L]` / `btn_el_filter_lateness` | Blendet im Entschuldigungsschreiben Verspätungen (< 50 min) ein oder aus (standardmäßig aktiv: ON). |
| `Synchronize` | `[R]` / `btn_sync` | Startet den sofortigen Hintergrund-Abgleich mit Moodle, Teams und WebUntis. |
| `Change Theme` | `[T]` / `Ctrl+P` | Rotiert durch die 22 Themes oder öffnet die Theme-Palette (`search_themes`) mit Rechtsklick-Favoriten (`⭐`). |
| `ThemeSelectModal` | Modal | Menü zur Auswahl aus allen 22 Themes (inkl. `OLED`); Rechtsklick markiert ein Theme als Favorit (`⭐`), Favoriten stehen ganz oben. |
| `Render Quality` | `digi_select_quality` | Wählt die Renderqualität im Digi4School-Download-Dialog (Ultra-HD 4.0x, High-Res 3.0x, Standard 2.0x). |
| `Next: Select Pages ➡️` | `btn_start_digi_download` | Prüft Tesseract OCR und leitet die automatische Buchanalyse zur Seitenauswahl ein. |
| `All Pages (1 - N)` | `btn_all_pages` | Setzt den Schieberegler im Seitenauswahl-Menü auf den vollen Buchumfang. |
| `TwoThumbRangeSlider` | `range_slider_widget` | Interaktiver 2-Schieber-Slider zur Festlegung von Start- und Endseite via Maus oder Tastatur. |
| `Start Download` | `btn_start_download_from_range` | Startet den Download und die OCR-Verarbeitung für den exakt ausgewählten Seitenbereich. |
| `Show in Downloads folder` | `btn_open_folder_d4s` | Öffnet den Downloads-Ordner nach erfolgreichem Buchdownload direkt im Windows Explorer. |
| `Install Update Now` | `btn_update_install` | Startet den automatischen In-App-Download des Installers und die Aktualisierung im Hintergrund. |
| `View in Browser` | `btn_update_open` | Öffnet die GitHub-Release-Seite der neuen Version im Standard-Webbrowser. |
| `Later [ESC]` | `btn_update_dismiss` | Schließt das Update-Erinnerungsmodal ohne Aktualisierung (ESC-Taste oder Mausklick). |

---

## 4. CommandPalette Befehle (Kurse, Schulbücher & Ordner)

| Befehl / Syntax | Modus | Kurzbeschreibung |
| :--- | :--- | :--- |
| `<Suchbegriff>` | Courses (Cyan) | Filtert Moodle-Kurse nach Fach oder Name und öffnet den gewählten Kurs im Browser. |
| `<Suchbegriff>` | Books (Rot) | Durchsucht die verknüpfte Schulbuch-Bibliothek und öffnet das gewählte Buch (PDF oder Web). |
| `/link` | Books | Öffnet den nativen Windows-Dateidialog zum Verknüpfen einer lokalen Schulbuch-PDF. |
| `/url <URL>` | Books | Öffnet den Eingabedialog zum Hinterlegen eines webbasierten Schulbuchs. |
| `/download <Code>` | Books | Startet den Digi4School Grabber und erzeugt ein durchsuchbares OCR-Sandwich-PDF. |
| `/unlink` | Books | Entfernt ein verknüpftes Buch aus der lokalen Liste (`data/schoolbooks.json`). |
| `<Suchbegriff>` | Directories (Grün) | Durchsucht verknüpfte Ordner nach Name oder Pfad und öffnet sie im Explorer. |
| `/link` | Directories | Öffnet den nativen Windows-Ordnerauswahldialog zum Verknüpfen eines lokalen Ordners. |
| `/unlink` | Directories | Entfernt eine Ordnerverknüpfung aus der lokalen Liste (`data/directories.json`). |

---

## 5. Headless Agent CLI Befehle (`tasks`)

| CLI Befehl | Optionen / Flags | Kurzbeschreibung |
| :--- | :--- | :--- |
| `tasks list` | `-s <status> -f <fach> --json` | Listet Aufgaben tabellarisch oder als JSON für KI-Agenten auf. |
| `tasks show <id>` | `--json` | Gibt vollständige Metadaten und Aufgabenstellung einer Aufgabe im Terminal aus. |
| `tasks download <id>` | `[--auto-dir] [--dir <pfad>] [--json]` | Lädt Anhänge und Angabe herunter; `--auto-dir` (-a) ermittelt automatisch das verknüpfte Kursverzeichnis. |
| `tasks explain <id>` | `[--lang de\|en] [--copy-only] [--no-browser] [--json]` | Generiert einen strukturierten KI-Erklärungsprompt, kopiert ihn in die Zwischenablage und öffnet den Browser. |
| `tasks open <fach>` | — | Öffnet den Moodle-Kurs des angegebenen Fachs im Standard-Webbrowser. |
| `tasks books list` | `--json` | Gibt alle verknüpften Schulbücher aus. |
| `tasks books open <id>` | — | Startet das angegebene Schulbuch im OS-Standardviewer oder Webbrowser. |
| `tasks books add <pfad>` | `--title <titel>` | Verknüpft eine lokale PDF-Datei oder Web-URL headless als Schulbuch. |
| `tasks books download <code>` | `[--quality <q>] [--scale <s>] [--dpi <d>] [--no-ocr] [--no-toc] [--page-offset <o>] [--visible]` | Lädt ein Digi4School-Buch im Terminal herunter und generiert ein OCR-PDF (Ultra-HD Standard). |
| `tasks dirs list` | `--json` | Gibt alle verknüpften lokalen Ordner aus. |
| `tasks dirs open <id\|name>` | — | Öffnet das verknüpfte Verzeichnis im System-Dateimanager (Windows Explorer). |
| `tasks dirs add <pfad>` | `--title <name>` | Verknüpft einen lokalen Ordnerpfad headless mit automatischer oder manueller Benennung. |
| `tasks dirs remove <id\|name>` | — | Entfernt eine Ordnerverknüpfung aus der lokalen Liste (`data/directories.json`). |
| `tasks skill sync` | `[--target <pfad>] [--json]` | Synchronisiert den Tasks-Skill in das gespeicherte Zielverzeichnis (fragt einmalig via Windows Explorer nach, falls nicht gesetzt). |
| `tasks skill set-dir` | `[<pfad>] [--set-dir [<pfad>]]` | Ändert das Zielverzeichnis für den Skill (öffnet bei leerem Argument den Explorer-Ordnerauswahldialog). |
| `tasks skill status` | `[--json]` | Zeigt den aktuellen Installationsstatus und Speicherort des Skills an. |
| `tasks tray` | `[status\|enable\|disable\|show\|quit\|sync-interval [VAL]] [--json]` | Steuert System-Tray, Auto-Sync-Intervall (`5min`, `10min`, `30min`, `1h`, `never`) und sendet `SHOW`/`QUIT`/`STATUS` an die Hintergrund-Instanz. |
| `tasks autostart` | `[status\|enable\|disable] [--json]` | Verwaltet den Windows-Autostart-Eintrag unter `HKCU\...\Run`. |
| `tasks sync` | `--deep` | Führt eine vollständige Plattform-Synchronisation im Hintergrund durch. |
| `tasks update` | `[--force\|--reinstall] [--json]` | Prüft auf neuere GitHub-Releases oder stößt bei `--force` eine sofortige Neuinstallation/Reparatur über den Update Manager an. |
| `update.bat` | — | Eigenständige Batch-Datei im Programmordner zur Reparatur und Drüber-Installation auch bei beschädigter `Tasks.exe`. |

---

## 6. Text-Eingabefelder, 3-Zeilen-Verhalten & Windows-Shortcuts

Projektweit für alle Dialog- und Formular-Eingabefelder (`ChatInputArea`), einzeiligen `Input`-Widgets (CommandPalette, Suchleisten, Passwortmasken) sowie Notizen:

### 3-Zeilen-Verhalten mit dynamischem Zeilensprung & Randlinie (`ChatInputArea`)
- **Einsatzbereiche**: Exklusiv für Freitext- und Notizfelder:
  - **AI Chat Menü**: `#ai_chat_input` (AI-Prompteingabe mit Back-Button auf gleicher Höhe)
  - **Aufgabe hinzufügen (`AddTaskModal`)**: `#inp_add_desc` (Beschreibung)
  - **Prüfung hinzufügen (`AddExamModal`)**: `#inp_add_exam_topics` (Stoff / Themen)
  - **Prüfungsdetails (`ExamDetailModal`)**: `#inp_exam_topics` (Stoff / Notizen)
- **Dünne Randlinie rundherum**: Feine, geschlossene Randlinie (`border: solid #45475a`, bei Fokus hervorgehoben in `#89b4fa`; im OLED-Theme `#343331` bzw. `#58a6ff`), die das Schreibfeld sauber einrahmt, ohne den Text zu berühren oder zu überlappen.
- **Feste 3-Zeilen-Tipphöhe**: Gesamthöhe `height: 5` (1 Zeile oberer Rand, 3 Zeilen Textinhalt, 1 Zeile unterer Rand).
- **Zeilensprung & Zentrierung**:
  - **1 Zeile (auch leer/Platzhalter)**: Text und Cursor starten vertikal zentriert in der mittleren Zeile (`padding: 1 1 1 1`).
  - **2 Zeilen**: Zeile 1 springt in die obere Zeile, Zeile 2 wird in der mittleren Zeile getippt (`padding: 0 1 1 1`).
  - **3 Zeilen**: Zeilen 1–3 füllen das Feld von oben nach unten (`padding: 0 1 0 1`).
  - **> 3 Zeilen**: Das Schreiben verbleibt fix in der untersten Zeile, frühere Zeilen scrollen nach oben weg und die Scrollbar wird automatisch aktiv.
- **Tastenbelegung**: `Enter` bestätigt/sendet das Formular (`Submitted`); `Shift+Enter` (sowie `Ctrl+Enter` / `Ctrl+J`) fügt einen Zeilenumbruch ein.
- **Alle anderen Formularfelder**: Standardmäßige, 1-zeilige `Input`-Widgets (wie Titel, Fach, Datum, Uhrzeit, Lehrer, URLs, Credentials).

| Shortcut | Aktion | Beschreibung |
| :--- | :--- | :--- |
| `STRG + ←` / `STRG + →` | Wortweise springen | Bewegt den Cursor um ein ganzes Wort nach links oder rechts (`cursor_left_word` / `cursor_right_word`). |
| `SHIFT + STRG + ←` / `→` | Wortweise markieren | Bewegt den Cursor wortweise und markiert dabei den Textbereich (`cursor_left_word(True)` / `cursor_right_word(True)`). |
| `Pos1` (`Home`) / `Ende` (`End`) | Zeilenanfang / Zeilenende | Springt direkt an den Anfang oder das Ende der aktuellen Zeile (`home` / `end`). |
| `SHIFT + Pos1` / `SHIFT + Ende` | Bis Anfang/Ende markieren | Markiert vom aktuellen Cursor bis zum Zeilenanfang oder Zeilenende (`home(True)` / `end(True)`). |
| `STRG + A` | Alles markieren | Markiert den gesamten Inhalt des Textfeldes (ersetzt Textuals Default `home`). |
| `STRG + Backspace` | Wort links löschen | Löscht das gesamte Wort links vom Cursor (`delete_left_word` / `delete_word_left`). Funktioniert in allen Terminals dank Win32-Treiber-Patch und Aliase `ctrl+w` & `ctrl+h`. |
| `STRG + Entf` | Wort rechts löschen | Löscht das gesamte Wort rechts vom Cursor (`delete_right_word` / `delete_word_right`). |
| `Tippen / Backspace` | Markierung überschreiben | Ersetzt oder löscht aktive Textauswahlen sofort bei der nächsten Eingabe. |
| `STRG + C` / `X` / `V` | Clipboard | Kopiert, schneidet aus oder fügt aus der Windows-Zwischenablage ein. |

---

## 7. Installer & Windows-Terminal Integration

| Feature / Steuerung | Typ | Kurzbeschreibung |
| :--- | :--- | :--- |
| `Quantum Prism App-Icon` | Asset | 3D-Vektor-App-Icon im Fluent-Squircle-Design; dual bereitgestellt als `app_icon.ico` (Desktop/Startmenü) und `app_icon.png` (Windows Terminal Profil). |
| `Inno Setup Wizard (English)` | Installer | Vollständig englischsprachiger Installations-Assistent (`compiler:Default.isl`) mit Playwright-Browser-Setup und Silent-Modus. |
| `Add 'tasks' command to PATH` | Installer | Optionale Checkbox auf der Abschlussseite zur Registrierung des Installationsverzeichnisses im Benutzer-PATH (standardmäßig aktiv). |
| `Configure Windows Terminal profile` | Installer | Optionale Checkbox auf der Abschlussseite zur automatischen Registrierung des Tasks-Profils mit Icon (standardmäßig aktiv). |
| `Add Tasks to Start Menu` | Installer | Optionale Checkbox auf der Abschlussseite zur Erstellung einer Startmenü-Verknüpfung via PowerShell `WScript.Shell` (standardmäßig aktiv). |
| `Rückstandslose Deinstallation` | Uninstaller | Bereinigt alle Runtime-Caches, Daten, `config.json`, das URL-Protokoll (`tasks://`), Windows-Terminal-Profile, Startmenü-Einträge und den Autostart-Registry-Key. |


