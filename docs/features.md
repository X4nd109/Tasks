# Feature & UI Element Catalog — Tasks

> **Zweck**: Eindeutige, token-effiziente Begriffswelt für Buttons, UI-Elemente und Features zwischen Benutzer und Agent.  
> **Regel**: Maximal 1 prägnanter Satz pro Eintrag. Exakte Bezeichnungen gemäß TUI- und CLI-Codebase.

---

## 1. Screens & Hauptansichten

| Element / View | Typ | Kurzbeschreibung |
| :--- | :--- | :--- |
| `Main Task Dashboard` | Screen | Farbcodierte Haupttabelle aller offenen und fälligen Moodle- und Teams-Aufgaben (`TasksApp`) mit priorisierten Spalten (Due Date & Teacher voll erhalten, Assignment flexibel) und jitter-freier Einzeilen-Statusleiste. |
| `Tests & Exams Screen` (`[E]`) | Screen | WebUntis Prüfungskalender mit dynamischer Vollbreiten-Verteilung aller 9 Spalten ohne rechten Leerraum und horizontalem Scrollbar-Puffer. |
| `CommandPalette` (`Backspace` / `/`) | Overlay | Schnellsuchleiste mit `Tab`-Umschaltung zwischen *Courses*, *Schoolbooks* und *Directories*; `Backspace` bei leerer Leiste schließt das Menü; behält Suchtext beim Umschalten. |
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
| `ExamDetailModal` | Modal | Zeigt Prüfungsdetails und ermöglicht das Bearbeiten persönlicher Stoff-Notizen (`exam_notes.json`). |
| `AddExamModal` | Modal | Formular zum Eintragen manueller Prüfungstermine mit nativer Wochentagserkennung. |
| `SettingsModal` (`[O]`) | Modal | Scrollbarer Konfigurationsdialog mit Versionsanzeige in der oberen rechten Ecke (`v2.0.0`), Themes, Logins und Schülereinstellungen. |
| `DownloadLocationModal` | Modal | Englischer Auswahldialog für das Download-Ziel mit Hotkeys `[1]` (Auto-Dir Kursordner), `[2]` (Manuell via Windows Explorer), `[3]` (Standard Downloads-Ordner) und `[ESC]` (Abbrechen). |
| `AiChatScreen` (`[I]`) | Screen | Vollwertiges In-App AI-Chat-Interface mit Browser-Style Tab-Leiste für alle offenen Aufgaben, dynamischer Tab-Expansion, Unterhaltungsverlauf, PyMuPDF-Textextraktion aus Anhängen und direkter Gemini / OpenAI REST-Anbindung. |
| `AiConfigModal` / `AiExplainModal` | Modal | Konfigurationsdialog für den AI Assistant mit Provider-Auswahl (Google Gemini Free-Tier, OpenAI-kompatibel), API-Key, Modell-Name, Base-URL, Test-Verbindung-Button und Sprachumschalter (German/English). |
| `UpdateReminderModal` | Modal | Popup-Erinnerung bei neueren GitHub-Releases mit 1-Klick-In-App-Download, Fortschrittsbalken und automatischer Installation im selben Verzeichnis (ohne PATH-Änderung oder Datenverlust). |
| `LoginChoiceModal` (`[L]`) | Modal | Zentrales Auswahlmenü für Anmeldungen bei Moodle, Microsoft Teams und WebUntis. |
| `TeamsSetupModal` | Modal | Geführter Teams-Login via Playwright-Chromium mit Passkey-, 2FA- oder Kennwort-Unterstützung. |
| `MoodleLoginModal` | Modal | Eingabe von Moodle-Benutzername (oder E-Mail mit automatischem Domain-Stripping) und Passwort mit blitzschneller HTTP-Authentifizierung und Fehleranzeige. |
| `UntisSetupModal` | Modal | Konfiguration von WebUntis-Schulname (Standard: spengergasse, Domain-Bereinigung & API-Suche), Benutzer und Passwort mit exakter Fehlerrückmeldung. |
| `GitSetupModal` | Modal | Einrichtungsdialog für cloudbasierten Git-Sync über privates Repository mit Token-Verschleierung. |
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
| `Ai Assistant` | `[I]` / `btn_main_ai` | Öffnet das native In-App AI-Chat-Interface (`AiChatScreen`) mit allen offenen Aufgaben als Browser-Tabs. |
| `Ai Explain` | `[A]` / `btn_det_ai_explain` | Schließt die Aufgaben-Details, wechselt direkt in den In-App AI-Chat auf den Tab dieser Aufgabe und startet automatisch die Schritt-für-Schritt-Erklärung (dedupliziert: bereits erklärte Aufgaben öffnen direkt den bestehenden Chat, Reset bei Clear Chat). |
| `AI Configuration` | `[7/A]` / `btn_set_ai_explain` | Öffnet in den Settings den Konfigurationsdialog (`AiConfigModal`) für KI-Provider, API-Key, Modell, Base-URL und Verbindungstest. |
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
| `tasks sync` | `--deep` | Führt eine vollständige Plattform-Synchronisation im Hintergrund durch. |

---

## 6. Text-Eingabefelder & Windows-Shortcuts

Projektweit für alle einzeiligen `Input`-Widgets (CommandPalette, Suchleisten, Aufgaben- und Prüfungsformulare, Logins, Schulkonfiguration) sowie mehrzeilige `TextArea`-Notizen:

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
| `Inno Setup Shortcut-Icons` | Installer | Weist dem Installer und allen Startmenü- und Desktop-Verknüpfungen das App-Icon zu. |
| `Windows-Terminal Profil-Option` | Installer | Optionale Checkbox auf der Fertigstellen-Seite zur Registrierung des Tasks Profils mit Logo. |
| `scripts/setup_terminal_profile.bat` | Script | Autarkes Batch/PowerShell-Skript zur Eintragung des Profils in `settings.json`. |
| `scripts/remove_terminal_profile.bat` | Script | Autarkes Batch/PowerShell-Skript zur rückstandslosen Entfernung des Profils beim Deinstallieren. |


