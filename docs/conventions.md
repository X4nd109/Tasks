# Development Conventions & Standards — Tasks

## 1. Code Style & Formatting

### General Python Standards
- **Target Version**: Python 3.10+ (compatible up to 3.12+).
- **Style Guide**: Adherence to **PEP 8** for naming, layout, and whitespace.
- **Type Annotations**: Mandatory type hinting for all public functions, methods, and dataclasses (`from typing import Optional, List, Dict, Tuple, Any`).
- **Encapsulation**: Internal functions and private helpers must use leading underscores (e.g., `_score_course_match`).

### Naming Conventions
| Entity | Case Convention | Example |
| :--- | :--- | :--- |
| **Modules / Files** | `snake_case.py` | `task_manager.py`, `moodle_service.py` |
| **Classes / Dataclasses** | `PascalCase` | `TaskManager`, `UntisExam`, `ExcuseService` |
| **Functions / Methods** | `snake_case` | `get_filtered_tasks()`, `download_task_files()` |
| **Constants** | `UPPER_SNAKE_CASE` | `CONFIG_DIR`, `AUTO_CLEAN_BROWSER_CACHE` |
| **CLI Commands** | Lowercase kebab/single | `tasks list`, `tasks open`, `tasks sync` |

### Language & Localization Standards (English-First UI)
- **Mandatory English for Program Features**: All newly created and modified UI elements, screens, modals, buttons, table headers, CLI help texts, outputs, status messages, toasts, log messages, and error banners **MUST be written in English**.
- **Exception 1 (Official Legal Documents)**: The generated Excuse Letter PDF (`src/services/excuse_service.py`) remains in Austrian German (*"Entschuldigung über das Fernbleiben vom Unterricht"*), as it is an official document submitted to Austrian schools. The surrounding UI dialogs and modals remain strictly in English.
- **Exception 2 (External School Data)**: Dynamic course names, assignment titles, and descriptions coming from school platforms (Moodle, Teams, WebUntis) are displayed as provided by the school system and must NOT be altered or machine-translated. Scraper DOM selectors must support both German and English school portal interfaces.

---

## 2. Architecture & Design Principles

### Strict Layer Separation
1. **Core Layer (`src/core/`)**:
   - Contains pure business logic, data models, caching mechanisms, and configuration loading.
   - Core modules must never depend on UI code (`ui.py` or `tui_app.py`).
2. **Service Layer (`src/services/`)**:
   - Contains adapters for external systems (Moodle, Teams, WebUntis, ReportLab).
   - Must handle network failures gracefully, falling back to cached snapshots where applicable.
3. **Presentation Layer (`src/ui/` & `agent_cli.py`)**:
   - Implements the user and agent interfaces.
   - Dispatches user intent directly to the `TaskManager`.

### Offline-First & Sub-100ms Execution
- **Instant Cache Read**: Any read-only operation (`tasks list`, `tasks show`, launching TUI) must read from local JSON files (`cache/tasks_cache.json`) without blocking on network requests.
- **Explicit Network Operations**: Network-intensive actions (scraping Moodle, spinning up Playwright for Teams) must be triggered explicitly via `--sync`, `[R]`, or login flags.

### Headless Agent Token-Efficiency
- When invoked in CLI mode (via `tasks.bat` or `python main.py <subcommand>`), output must be strictly token-efficient:
  - Tabular rows formatted compactly with fixed column widths.
  - Zero decorative ASCII banners or conversational pleasantries.
  - Support for raw, machine-readable JSON via `--json` or `-json`.

### Zero-Knowledge Credential Handling
- Never write credentials, session tokens, cookies, or user passwords to console logs, error messages, or Git repositories.
- Keep `config.json` free of sensitive plaintext authentication secrets; delegate authentication to Playwright's persistent storage state.
- Keep `installer/license_secret.key` strictly untracked and private.

---

## 3. Platform & Filesystem Conventions

- **Encoding**: Always specify `encoding="utf-8"` on all file read and write operations.
- **Paths**: Use `os.path.join` or `pathlib.Path` exclusively to prevent backslash/forward-slash breakage on Windows.
- **Download Location**:
  - Downloaded assignment bundles must resolve to:
    `%USERPROFILE%\Downloads\<Fach> - <Aufgabenname>\`
  - Generate an `angabe.md` containing the assignment description and deep-link.
  - Reveal downloaded files using `os.startfile(folder_path)` inside a protected try-except block.

---

## 4. Testing & Verification Guidelines

- **Framework**: Standard `unittest` and `pytest`.
- **Location**: Test files must be located inside the `tests/` directory matching `test_*.py`.
- **Offline Guarantee**: Automated tests must never make real outbound network requests to live school systems. Always mock network endpoints, WebUntis JSON-RPC responses, and Playwright browsers.
- **Running Tests**:
  ```powershell
  # Using unittest
  python -m unittest discover tests

  # Using pytest (if installed)
  pytest tests/ -v
  ```

---

## 5. Git & Commit Guidelines

- **Atomic Commits**: Each commit should address a single logical change.
- **Commit Prefixes**:
  - `feat:` New features or commands.
  - `fix:` Bug fixes or crash resolutions.
  - `refactor:` Code improvements without altering external behavior.
  - `docs:` Documentation updates in `AGENTS.md` or `docs/`.
  - `test:` Test additions or test infrastructure updates.
