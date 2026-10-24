# 📚 Aufgaben-Detector (Moodle, Teams & WebUntis)

[![Release](https://img.shields.io/github/v/release/X4nd109/Aufgaben-Detector?color=blue&label=Release)](https://github.com/X4nd109/Aufgaben-Detector/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6.svg)](https://microsoft.com/windows)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![Tests: 381 passing](https://img.shields.io/badge/Tests-381%20passing-brightgreen.svg)](tests/)

Modern terminal workspace (Interactive TUI & Headless CLI) consolidating all school assignments from **Moodle** and **Microsoft Teams**, timetable absences and exam schedules from **WebUntis**, as well as schoolbooks and **Digi4School** in one unified view.

> 📖 **Comprehensive Documentation:** Persistent 2-tier session memory located in [**`docs/`**](docs/project-overview.md) ([Project Overview](docs/project-overview.md) • [Architecture](docs/architecture.md) • [Conventions](docs/conventions.md) • [Current State](docs/current-state.md) • [Decisions (ADRs)](docs/decisions.md)) and the master index [`AGENTS.md`](AGENTS.md).

---

## ✨ Features

1. **Consolidated Assignment Feed (Moodle & Teams):**
   - Unified view of assignments from Moodle (🟧) and Microsoft Teams (🟦) in a color-coded table.
   - Automatic urgency warnings (Red = Overdue, Yellow = Due within 24 hours).
   - Rich filtering by completion status (*Open Only*, *Overdue*, *Completed*, *All*), school subject (*SWP*, *AMEC*, *NWES*, *BET*...), or platform.

2. **Assignment Details & Smart Auto-Dir Downloads:**
   - Full task instructions rendered as clean, formatted Markdown.
   - **Smart Download Dialog (`[D]`):** Choose between **[1] Auto-Dir** (automatically downloads attachments into your linked school subject folder, e.g. `OneDrive\Schule\HTL\3. Klasse\<Subject>\`), **[2] Explorer** (pick destination via Windows File Explorer), or **[3] Standard Downloads** (`%USERPROFILE%\Downloads\<Subject> - <Title>\`).
   - Automatically opens the target folder in Windows File Explorer upon completion.
   - 1-Click navigation directly to the official Moodle or Teams submission portal in your browser (`[O]`).

3. **Native In-App AI Assistant & Explain Screen (`AiChatScreen`):**
   - **🤖 Interactive Full-Screen AI Assistant (`[I]`):** Dedicated chat interface with browser-style tabs for all active assignments. Automatically remembers your last opened task.
   - **Deep Context & Auto-Attachment Text Extraction:** Automatically extracts text from attached PDFs (via PyMuPDF / `fitz`), Markdown files, and source code (`.py`, `.c`, `.java`, etc.) into the AI system prompt. The assistant understands the exact requirements and questions without user re-explanation.
   - **Rich Markdown & Syntax Highlighting:** Assistant responses render with native Markdown, syntax-highlighted code fences (`MarkdownFence`), and inline code blocks across both standard and OLED themes.
   - **Fluid Input Experience:** Direct Enter-to-send, `Shift+Enter` multi-line expansion (up to 3 rows with auto-scrollbar), and an animated 3-dot thinking indicator (`Thinking.` $\rightarrow$ `Thinking..` $\rightarrow$ `Thinking...`).
   - **🤖 Seamless Ai Explain (`[A]`):** In any assignment detail modal, click `[A]` to immediately transition into the AI assistant with that task active and step-by-step guidance.
   - **AI Configuration Hub (`Settings` -> `[7]` / `[A]`):** Configure Google Gemini Free-Tier (`gemini-2.0-flash`) or OpenAI-compatible models, auto-fetch available models, test connection, and switch languages (DE/EN).

4. **WebUntis Absence Tracking & Timetable Reconciliation:**
   - Split absence view accessible via `[U]` or by clicking `[📅 Absences]`.
   - Reconciles raw absence intervals with the exact timetable of the respective day.
   - Handles split workshop/lab classes (e.g. `1x` vs `1y`) as well as cancelled lessons (*Entfall*) and substitutions.
   - **Automated Excuse Generator:** Generates official PDF excuse letters for school submission (HTL Spengergasse).

5. **WebUntis Exam & Test Planner:**
   - Dedicated exam overview via `[E]` showing date, subject, period, exam type, and classroom.
   - Live countdown timer for upcoming exams and major tests.
   - Record custom preparation notes and revision topics stored locally.

6. **Quick-Jump & Schoolbooks Palette (`Backspace` / `/`):**
   - CommandPalette for instant opening of Moodle course pages in your browser.
   - **Schoolbooks Tab:** Press `Tab` to switch seamlessly between *Courses* and *Schoolbooks*.
   - Link local PDF textbooks (`/link`) or online digital books (`/url`).
   - 1-Click opening in your OS default PDF viewer or browser.

7. **Digi4School Book Grabber (`/download`):**
   - Built-in Digi4School book grabber integrated directly into the search palette.
   - Quick download via access code: `/download <access_code>` (or through the interactive `/` command menu).
   - Downloads all high-resolution pages and compiles a fully searchable **OCR sandwich PDF** with table of contents (bookmarks), clickable hyperlinks, and synchronized page numbering.
   - Saved directly to your Windows Downloads folder with a 1-click button to reveal the file.

8. **Headless Agent CLI (`tasks`):**
   - Token-efficient CLI dispatcher designed for AI coding agents (Antigravity), terminal enthusiasts, and automated scripts.
   - Subcommands include `tasks list`, `tasks show <id>`, `tasks download <id>`, `tasks books`, `tasks sync`, and `tasks open <subject>`.
   - `--json` flag for machine-readable integrations.

9. **Zero-Knowledge & Local-First Security:**
   - All credentials, session tokens, browser cookies, and caches remain strictly on your local machine.
   - No plaintext passwords, no telemetry, no cloud dependency.
   - Fully open source under the **MIT License**.

---

## 🚀 Installation & Getting Started

### Option 1: Windows Installer (Recommended)
Download the latest standalone setup wizard directly from GitHub:  
👉 **[Download AufgabenDetector_Setup.exe (GitHub Releases)](https://github.com/X4nd109/Aufgaben-Detector/releases/latest)**

* **On-Demand Python Setup:** Automatically detects Python or silently installs official Python 3.12 if missing.
* **Zero Configuration:** Creates Desktop and Start Menu shortcuts, and registers the global `tasks` command in your User PATH.
* No administrator privileges required (Installs into `%LOCALAPPDATA%` by default).

---

### Option 2: Running from Source (Developer / Portable)

1. **Clone the repository:**
   ```powershell
   git clone https://github.com/X4nd109/Aufgaben-Detector.git
   cd Aufgaben-Detector
   ```

2. **Run setup:**
   ```powershell
   .\setup.bat
   ```
   *(Verifies Python, installs requirements from `requirements.txt`, and sets up Playwright Chromium).*

3. **Launch the application:**
   - Interactive Terminal UI (TUI):
     ```powershell
     .\run.bat
     # or
     python main.py
     ```
   - Register global terminal command (`tasks`):
     ```powershell
     .\scripts\setup_command.bat
     ```

---

## ⚙️ Configuration

Copy the example configuration file before your first launch:
```powershell
Copy-Item config.example.json config.json
```

Customize profile details for the excuse generator and WebUntis in `config.json`:
```json
{
  "excuse_profile": {
    "student_name": "Max Mustermann",
    "student_class": "1AHIT",
    "teacher_name": "Prof. Example",
    "school_address": "School Street 1",
    "school_district": "1010 Vienna"
  },
  "untis_group": "X",
  "untis_school": "my-school",
  "untis_url": "https://mese.webuntis.com/WebUntis/?school=my-school",
  "theme": "catppuccin-mocha"
}
```

---

## ⌨️ Keyboard Shortcuts (TUI)

### Main Screen
| Key | Action |
|---|---|
| `I` | 🤖 Open In-App AI Assistant (`AiChatScreen`) |
| `1` - `9` | View details for task 1 to 9 |
| `A` | Add a manual custom task |
| `E` | Open WebUntis Exams & Tests calendar |
| `Backspace` / `/` | Open Quick-Jump Palette (Courses & Schoolbooks) |
| `F` | Open Filter Menu (Status, Subject, Timeframe) |
| `R` | Synchronize assignments from Moodle & Teams |
| `U` | Open WebUntis Absences & Excuse PDF Generator |
| `G` | Open Trash (Hidden / Deleted assignments) |
| `L` | Open Login Menu (Moodle, Teams, WebUntis) |
| `O` | Open Settings (Themes, Untis group, Excuse profile, AI config) |
| `T` / `Ctrl+P` | Switch color theme (22 curated themes with instant preview) |
| `Q` | Quit Aufgaben-Detector |

### Assignment Details Modal
| Key | Action |
|---|---|
| `O` | Open submission portal in web browser |
| `D` | Download all attachments & instructions (Auto-Dir [1], Explorer [2], Downloads [3]) |
| `A` | 🤖 Ai Explain (switch directly to In-App AI Assistant for this task) |
| `E` | Toggle task completion status (Done / Open) |
| `L` | Hide assignment / move to Trash |
| `W` | Restore deleted assignment |
| `Esc` / `Z` | Close details modal |

### Schoolbooks Palette Commands (`Backspace` -> `Tab`)
| Command | Action |
|---|---|
| `/link` | Link local PDF textbook via native file dialog |
| `/url <URL>` | Link online textbook or digital e-book |
| `/download <Code>` | Download Digi4School book & compile OCR PDF |
| `/unlink` | Remove linked schoolbook |

---

## 🤖 Headless CLI (`tasks`)

Designed for AI coding agents (Antigravity), terminal power users, and shell scripts:

```powershell
# List assignments
tasks list
tasks list -s open -f SWP
tasks list --json

# View assignment details
tasks show 1
tasks show <task_id> --json

# Generate AI explanation prompt
tasks explain 1
tasks explain <task_id> --lang en --copy-only

# Download attachments & problem statement (optional --auto-dir to auto-match linked folder)
tasks download 1
tasks download 1 --auto-dir
tasks download <task_id> --dir "C:\School\SWP"

# Manage & open schoolbooks
tasks books list
tasks books open 1
tasks books add "C:\School\MathBook.pdf"
tasks books download 26s7dbu5qxvw

# Open Moodle course in browser
tasks open SWP

# Trigger background sync
tasks sync
```

---

## 📂 Project Structure

```text
Aufgaben-Detector/
├── assets/                     # Static assets (fonts, icons)
│   └── fonts/                  # GentiumPlus font family for PDF generation
├── cache/                      # Local browser profiles & cache files (untracked)
├── data/                       # Local user data (JSON, untracked)
│   ├── custom_tasks.json       # User-created manual tasks
│   ├── custom_exams.json       # User-created exams
│   ├── deleted_tasks.json      # Hidden / soft-deleted tasks
│   ├── exam_notes.json         # User exam notes & revision topics
│   └── schoolbooks.json        # Linked digital textbooks
├── docs/                       # Standardized 2-Tier Project Documentation
│   ├── project-overview.md     # Vision, Features & Tech Stack
│   ├── architecture.md         # Architecture, Data Flow & Caching
│   ├── conventions.md          # Code Conventions, Testing & Localization
│   ├── current-state.md        # Session Handoff & Active Milestones
│   └── decisions.md            # Architecture Decision Records (ADRs)
├── installer/                  # Inno Setup 6 Packaging Pipeline
│   ├── build_installer.py      # Builds AufgabenDetector_Setup.exe
│   └── aufgaben_detector.iss   # Inno Setup script template
├── scripts/                    # Windows helper scripts
│   ├── setup_command.bat       # Adds global 'tasks' command to User PATH
│   └── remove_command.bat      # Removes 'tasks' command from User PATH
├── src/                        # Application source code
│   ├── core/                   # Core business logic & storage
│   │   ├── agent_cli.py        # Token-efficient headless CLI
│   │   ├── auth.py             # Authentication & session storage
│   │   ├── config.py           # Dynamic path resolution, themes & config
│   │   ├── models.py           # Data models (Task, UntisExam, Lesson)
│   │   └── task_manager.py     # Aggregation, sorting & caching
│   ├── services/               # Platform adapters & generators
│   │   ├── ai_chat_service.py    # In-App AI assistant: attachment extraction & Gemini/OpenAI API
│   │   ├── ai_explain_service.py # AI prompt generator & provider dispatcher
│   │   ├── digi4school_service.py # Digi4School grabber & OCR engine
│   │   ├── directory_service.py  # Linked subject directories & Explorer integration
│   │   ├── excuse_service.py   # PDF excuse letter generator
│   │   ├── git_sync_service.py # Git cloud synchronization
│   │   ├── moodle_service.py   # Moodle HTTP scraper & API
│   │   ├── schoolbook_service.py # Schoolbook registry & launcher
│   │   ├── teams_service.py    # Microsoft Teams Playwright automation
│   │   └── untis_service.py    # WebUntis JSON-RPC & timetable matcher
│   └── ui/                     # Terminal User Interface (Textual)
│       ├── tui_app.py          # Interactive TUI (screens, modals, palettes)
│       └── ui.py               # Rich terminal formatting helpers
├── tests/                      # Automated unit & integration test suite (381 tests)
├── AGENTS.md                   # Lean master index (< 3 KB) for Antigravity agents
├── config.example.json         # Example user configuration template
├── LICENSE                     # MIT License
├── main.py                     # Primary entry point (TUI & CLI dispatcher)
├── requirements.txt            # Python dependencies
├── run.bat                     # 1-Click interactive launcher for Windows
├── setup.bat                   # Automated installation & repair script
└── tasks.bat / .cmd            # Windows wrapper for 'tasks' terminal command
```

---

## 🔨 Building the Installer & CI/CD

Aufgaben-Detector provides an automated packaging workflow using Inno Setup 6 and GitHub Actions:

1. Install **Inno Setup 6**: [https://jrsoftware.org/isdl.php](https://jrsoftware.org/isdl.php)
2. Execute the build script:
   ```powershell
   python installer/build_installer.py
   ```
   * Automatically downloads the official Python 3.12 installer on demand.
   * Produces the universal `installer/dist/AufgabenDetector_Setup.exe`.

Every Git tag push (e.g. `git tag v1.0.0 && git push origin v1.0.0`) triggers the GitHub Actions workflow (`.github/workflows/release.yml`), compiling the installer on a Windows virtual runner and attaching the output binary to the GitHub Release.

---

## ⚖️ Legal Disclaimer

* **Personal Study & Private Use Only**: The Digi4School integration and textbook downloader are provided exclusively for individual, personal study and offline learning by students who hold lawful licenses and valid access codes (in accordance with the private copy exception under § 42 of the Austrian Copyright Act / UrhG).
* **No DRM Circumvention or Piracy**: This project does not crack copy protection, bypass paywalls, or distribute copyrighted textbook contents. All downloads require the user's own active, legitimate credentials and access codes entered locally on their machine.
* **Prohibition of Redistribution**: Users must never upload, share, distribute, or publicly rehost downloaded textbooks (e.g. to cloud drives, chat groups, or file-sharing platforms). Doing so constitutes copyright infringement.
* **Independent Project**: *Aufgaben-Detector* is an independent open-source project and is not affiliated with, authorized, maintained, or endorsed by Digi4School, the Austrian Federal Ministry (BMBWF), Moodle Pty Ltd, Microsoft Corporation, or Untis GmbH. All registered trademarks belong to their respective owners.

---

## 📄 License

This project is licensed under the **[MIT License](LICENSE)** – see the `LICENSE` file for details.  
Copyright (c) 2026 Alexander Endl.
