# Project Overview — Tasks

## 1. Vision & Purpose

### Problem Statement
Students in technical colleges (specifically HTL Spengergasse, Class 3AHWII) must manage coursework across three disparate, fragmented platforms:
1. **Moodle**: Complex course hierarchies, homework assignments, deadlines, and attached templates.
2. **Microsoft Teams Education**: Class teams, assignment notifications, and submission statuses.
3. **WebUntis**: Timetables, cancellations (*Entfälle*), room shifts, exam schedules, and absence accounting.

Checking each portal manually is tedious, prone to missed deadlines, and lacks unified offline search and quick access. Furthermore, autonomous AI agents requiring homework context need a fast, low-overhead interface rather than dealing with slow, interactive browser sessions.

### Vision
**Tasks** provides a unified, local-first command hub that aggregates all assignments, absences, and exams into a single pane of glass. It provides both:
- An interactive **Textual Terminal User Interface (TUI)** with full mouse, keyboard, and color theme support.
- A blazing-fast (`< 0.1s`), token-efficient **Headless Agent CLI** (`tasks.bat`) designed for autonomous agents and developer automation.

### Target Audience & Personas
- **HTL Students**: Quick daily review of pending homework, 1-click downloads to Windows `Downloads`, and automatic generation of signed excuse letters.
- **Autonomous AI Coding Agents**: Rapid CLI inspection of school tasks, course materials, and syllabus details with zero token bloat.
- **Classmates & Friends**: Portable standalone Windows-installer packages with hardware-bound activation.

---

## 2. Core Features & Scope

### In-Scope Capabilities
- **Consolidated Assignment Management**:
  - Color-coded deadline status (Red = Overdue, Yellow = Due today/tomorrow, Green = Future).
  - Multi-dimensional filtering by platform (`moodle`, `teams`, `manual`), subject (`SWP`, `SESD`, `BET`, etc.), and completion status.
  - Hiding/trashing of team assignments already submitted by classmates (`[L]` / `tasks delete`).
- **WebUntis Timetable-Matched Absence Tracking**:
  - Maps calendar absences against scheduled lessons to compute exact missed lesson units.
  - Filters group divisions (e.g., `1x` vs. `1y` workshop groups) based on `config.json`.
  - Distinguishes between excused absences, unexcused periods, and timetable cancellations (*Entfall*).
- **Automated PDF Excuse Generator (`excuse_service.py`)**:
  - Generates official school absence excuse PDFs formatted with school address, student name, class, and missed lesson tables.
- **1-Click File Downloader**:
  - Downloads all task attachments and formats the assignment text into `angabe.md` directly inside `%USERPROFILE%\Downloads\<Subject> - <Title>\`.
  - Automatically pops open Windows Explorer to the target folder.
- **Quick Jump Course Navigation**:
  - Fuzzy-matching search (`tasks open <query>` or `Backspace` in TUI) to jump directly into the relevant Moodle or Teams portal in the default browser.
- **Schulbuch-Schnellzugriff (Schoolbooks Quick-Open)**:
  - Fast dual-mode access via `Backspace` + `Tab` to launch local PDF textbooks in default OS viewer or online schoolbook portals in the browser.
  - Local management via `/link` (Explorer file picker), `/url`, `/unlink`, and headless CLI (`tasks books [list|open|add|remove]`).
- **Dual-Interface Dispatch**:
  - Interactive Textual TUI (`src/ui/tui_app.py`) for desktop usage.
  - Headless CLI (`src/core/agent_cli.py`, `tasks`) supporting subcommands and shorthands (`tasks list`, `tasks show 1`, `tasks download 1`, `tasks sync`, etc.).
- **Zero-Knowledge Privacy & Security**:
  - 100% local execution; credentials remain in local browser profiles or OS credential stores.
  - No secret tokens, credentials, or cookies exposed to AI contexts or remote servers.
- **Open-Source Distribution & Automated Releases**:
  - MIT licensed for transparent community use and development.
  - Generates universal Windows installers (`Tasks_Setup.exe`) via Inno Setup with automatic Python bundling.
  - Automated CI/CD release workflow via GitHub Actions.

### Non-Goals (Out of Scope)
- **Automatic Submission**: The tool does not automatically upload homework files or submit assignments to Moodle or Teams without explicit student action.
- **Centralized Cloud Backend**: There is no remote database or cloud server; all state is preserved in local JSON caches (`cache/`, `data/`).
- **Grade Manipulation**: Read-only consumption of official course portals; does not alter grades or official school register entries.

---

## 3. Technology Stack Summary

| Layer | Technologies | Role / Rationale |
| :--- | :--- | :--- |
| **Language** | Python 3.10+ | Robust scripting, extensive ecosystem, cross-version Windows compatibility |
| **TUI Interface** | Textual 0.50+, Rich 13.7+ | Modern terminal application framework with widgets, reactive styling, mouse and key support |
| **Web Automation** | Playwright (Chromium) | Headless browser execution for MS Teams and Moodle SSO where public REST APIs are absent |
| **Networking** | Requests | Fast HTTP REST communication with Moodle endpoints and WebUntis JSON-RPC |
| **Document Generation** | ReportLab, fpdf2, PyMuPDF | Exact layout rendering for official school excuse PDFs |
| **Data Storage** | Local JSON (`cache/`, `data/`) | Zero-dependency, instantaneous offline read access (< 0.1s startup) |
| **Packaging & Installer** | Inno Setup 6, PowerShell, Batch | Standalone Windows distribution with automated PATH registration and offline Python bundling |
