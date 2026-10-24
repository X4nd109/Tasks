# Architecture Decision Records (ADRs) — Aufgaben-Detector

This document records high-impact architectural choices, library selections, and design decisions to maintain technical consistency across development sessions and agent interactions.

---

## ADR-001: 2-Tier Modular Documentation & Session Memory Architecture

- **Date**: 2026-10-13
- **Status**: Accepted
- **Context**: Autonomous AI coding agents lose context across discrete sessions. Storing exhaustive documentation in a single prompt or root README leads to massive context bloat and token inefficiency.
- **Decision**: Adopt a strict 2-tier documentation hierarchy:
  1. `AGENTS.md` in the project root: Kept strictly under 3 KB (~500–800 tokens) as the master index loaded on every session start.
  2. `docs/`: Modular, on-demand markdown deep-dives (`project-overview.md`, `architecture.md`, `conventions.md`, `current-state.md`, `decisions.md`) retrieved via `view_file` only when required.
  3. `docs/current-state.md` serves as the persistent cross-session handoff log.
- **Consequences**:
  - Positive: Instant session bootstrap, zero token wastage, clear navigation pathways.
  - Negative: Agents must actively maintain and update `docs/current-state.md` upon completing work.

---

## ADR-002: Dual-Interface Architecture (Textual TUI & Headless Agent CLI)

- **Date**: 2026-10-06
- **Status**: Accepted
- **Context**: The tool is used by human students on their desktop PCs as well as by autonomous AI coding assistants and automation scripts. A GUI or interactive TUI is ideal for human students, but unusable or token-expensive for agents and terminal pipes.
- **Decision**: Implement a unified entry point (`main.py` / `tasks.bat`) that dynamically dispatches between:
  - **Headless Agent CLI (`src/core/agent_cli.py`)**: Activated whenever CLI arguments or subcommands are provided (`tasks list`, `tasks show 1`, `tasks sync`, etc.). Emits compact tables or pure JSON (`--json`).
  - **Textual TUI (`src/ui/tui_app.py`)**: Activated when invoked with zero arguments or `--tui`. Provides a mouse- and keyboard-interactive terminal application.
- **Consequences**:
  - Positive: Perfect experience for both human users and AI agents without duplicating data logic.
  - Negative: Requires maintaining both Textual widget states and CLI flag handlers.

---

## ADR-003: Playwright Persistent Browser Context for Microsoft Teams

- **Date**: 2026-10-04
- **Status**: Accepted
- **Context**: Microsoft Teams Education assignments cannot be queried via standard Graph API without tenant-wide administrator consent (which students cannot obtain). Students must also handle 2-Factor Authentication (2FA) and school SSO portals.
- **Decision**: Use Playwright with Chromium and a persistent user profile directory (`cache/teams_browser_profile/`). The user performs a one-time interactive login in a visible browser (`tasks -teams-login` or `[T]`), after which all background scrapers run in headless mode reusing session cookies and tokens.
- **Consequences**:
  - Positive: Completely bypasses Graph API permission hurdles; supports MFA/SSO seamlessly.
  - Negative: Requires Chromium browser installation (`playwright install chromium`), adding ~150 MB disk footprint.

---

## ADR-004: Direct WebUntis JSON-RPC with Timetable Lesson Matching

- **Date**: 2026-10-05
- **Status**: Accepted
- **Context**: WebUntis reports absence periods as raw calendar timestamps. However, students need to know the exact number of missed teaching units, accounting for free periods, room changes, cancelled classes (*Entfall*), and split workshop/laboratory groups (`1x` vs. `1y`).
- **Decision**: Directly communicate with the WebUntis JSON-RPC API (`getTimetable`, `getAbsences`, `getKlassen`). Map each absence period against the student's actual timetable for that day, filter group divisions according to `untis_group` in `config.json`, and count cancelled lessons appropriately.
- **Consequences**:
  - Positive: 100% accurate absence calculations matching the official school register.
  - Negative: Requires parsing both timetable lesson objects and absence intervals simultaneously.

---

## ADR-005: Local-First JSON Caching with Sub-100ms Read Performance

- **Date**: 2026-10-05
- **Status**: Accepted
- **Context**: Querying Moodle, Teams, and WebUntis over the network on every command execution introduces 2–10 seconds of latency, which ruins CLI and TUI responsiveness.
- **Decision**: Implement an offline-first caching layer (`cache/tasks_cache.json` and `cache/untis_cache.json`). All read operations load local JSON data synchronously (< 0.1s). Network operations are strictly decoupled and executed on explicit demand (`tasks sync` or `[R]`).
- **Consequences**:
  - Positive: Instant CLI output (`< 0.1s`), full offline capability, zero battery drain.
  - Negative: Cache may become stale until the next explicit or background sync.

---

## ADR-006: Hardware-ID Bound Licensing with HMAC-SHA256 for Distribution

- **Date**: 2026-10-07
- **Status**: Superseded by ADR-011
- **Context**: When sharing packaged installers (`setup_<Name>.exe`) with friends and classmates, individual configuration and access must be managed without sharing master credentials or allowing uncontrolled re-distribution.
- **Decision**: Implement hardware fingerprinting (`src/core/license.py`) using CPU ID, motherboard UUID, and MAC address. Generate activation keys via `installer/generate_license.py` using HMAC-SHA256 and an offline secret key (`license_secret.key`). Pre-built setups require valid activation upon first launch.
- **Consequences**:
  - Positive: Ensures distributed builds remain bound to authorized devices without cloud activation servers.
  - Negative: Hardware changes (e.g., motherboard replacement) require re-issuing an activation code.

---

## ADR-007: Reentrant Locking and Non-Interactive Subprocess Hardening for Git Cloud-Sync

- **Date**: 2026-10-13
- **Status**: Accepted
- **Context**: `GitSyncService` coordinates repository initialization, remote pulling, smart merging, and pushing across background threads and modal UI interactions. A standard non-reentrant mutex (`threading.Lock`) caused recursive self-deadlocks whenever `setup_repository()` called `pull_and_sync()` and `push_changes()`. Furthermore, unhandled git interactive prompts or GUI credential helpers could block background threads indefinitely under Windows.
- **Decision**:
  1. Use `threading.RLock()` for `_sync_lock` across all Git sync routines to safely permit recursive and reentrant service calls.
  2. Enforce strict headless execution in `_run_git_cmd()` by configuring `-c credential.helper=` and `-c core.askPass=` in conjunction with `GIT_TERMINAL_PROMPT=0`, `SSH_ASKPASS=""`, and `GCM_INTERACTIVE=never`.
  3. Wrap UI background threads (`GitSetupWorker`) in comprehensive exception guards to ensure interactive modals always receive completion signals and re-enable controls on failure.
  4. Skip redundant fetch calls on empty remotes and re-clone cleanly when the configured repository URL changes.
- **Consequences**:
  - Positive: Eliminates thread lockups, ensures sub-second failure reporting instead of indefinite hangs, and allows nested repository lifecycle operations safely.
  - Negative: Requires careful thread safety awareness when nested methods modify shared disk files.

---

## ADR-008: Dual-Mode CommandPalette with Dynamic Provider Isolation and Local-Only Schoolbook Storage

- **Date**: 2026-10-17
- **Status**: Accepted
- **Context**: Students need rapid access to local PDF textbooks and online school platforms (Trauner, Veritas, ÖBV) without navigating folder trees or browser bookmarks. The feature needs to be unified with the existing `Backspace` quick-jump modal while keeping absolute local filesystem paths strictly isolated per machine (avoiding broken links across multi-device Git synchronization).
- **Decision**:
  1. Subclass Textual's `CommandPalette` as `UnifiedCommandPalette` with a priority `Tab` keybinding to toggle between **Kurse** (displayed in turquoise `bold cyan`) and **Schulbücher** (displayed in `bold red`).
  2. Implement `UnifiedQuickOpenProvider` with dynamic mode binding via `UnifiedCommandPalette.current_mode`, strictly isolating course search hits from schoolbook hits so switching modes completely replaces list contents.
  3. Support `/` in Schulbücher mode to immediately list all management commands (`/link`, `/url`, `/unlink`) and existing books.
  4. Perform Windows Explorer PDF file picking thread-safely in background workers using Tkinter (`filedialog.askopenfilename`) with a PowerShell fallback.
  5. Store textbook metadata locally in `data/schoolbooks.json` and enforce complete Git isolation via `.gitignore`, `data/.gitignore`, and explicit exclusion from `GitSyncService.push_changes()`.
  6. Expose headless CLI commands `tasks books [list|open|add|remove]` for agentic workflows and scripts.
- **Consequences**:
  - Positive: Instant access (<0.05s) to schoolbooks without adding new global hotkeys; clean separation of machine-specific paths from cloud sync; thread-safe file dialogs without UI freezing.
  - Negative: Moving or deleting local PDF files outside the application requires updating or unlinking the stored entry.

---

## ADR-009: In-Palette Digi4School Book Grabber with OCR, TOC & Live Dynamic ETA

- **Date**: 2026-10-17
- **Status**: Accepted
- **Context**: Students access digital schoolbooks on Digi4School, but require searchable offline PDFs for study, offline reading, and note-taking. Digi4School enforces single-session constraints (Fehler 911), and publisher redirects route through external viewers (Hölzel-Pichler-Tempsky, Trauner, ÖBV). Users need to trigger downloads seamlessly from the search bar without persistent disk storage of credentials.
- **Decision**:
  1. Integrate `/download` (aliases `/d4s`, `/digi4school`) directly into the Schulbuch search palette, prefilling access codes when provided (e.g. `/download 26s7dbu5qxvw`).
  2. Prompt for Digi4School credentials and 12-digit code interactively on each download run via `Digi4SchoolDownloadModal` with immediate memory deletion after authentication (zero plain-text credential persistence on disk).
  3. Validate host system Tesseract OCR installation before initiating headless browser sessions; abort with an explicit `winget` installation guide if absent.
  4. Encapsulate download logic in `Digi4SchoolService` (`src/services/digi4school_service.py`), handling publisher redirects, LTI forms, automatic popup dismissal, parallel multi-core OCR (`ProcessPoolExecutor`), PDF bookmark outlines, in-page TOC hyperlinks, and page label synchronization.
  5. Provide `Digi4SchoolProgressModal` in the Textual TUI displaying live page & OCR progress, dynamic remaining time (ETA) calculations, and an error-911 warning banner.
  6. Automatically save output PDFs directly to `%USERPROFILE%\Downloads\` with a 1-click folder button in the completion screen.
  7. Expose headless CLI commands `tasks books download <code_or_index> [--email <m>] [--password <p>] [--json]` for automated scripts.
- **Consequences**:
  - Positive: Complete textbook grabber directly accessible in TUI and CLI without switching programs; produces 100% searchable OCR sandwich PDFs with interactive navigation; non-blocking UI with live ETA feedback.
  - Negative: Downloading full textbooks (300+ pages) requires moderate network bandwidth and intensive CPU utilization during parallel OCR processing.

---

## ADR-010: English-First UI & System Localization Architecture

- **Date**: 2026-10-17
- **Status**: Accepted
- **Context**: The codebase historically contained a mix of German and English UI labels, error strings, toasts, and CLI outputs. A clean, professional, and globally readable developer experience requires a consistent language across all program components, while respecting Austrian school requirements.
- **Decision**:
  1. **Standardized English**: All UI views, Textual modals, command palettes, buttons, table headers, toasts, CLI outputs/flags, logging, and error messages must be authored strictly in English. All future features and bug fixes must adhere to this standard.
  2. **Official Excuse Letter Exemption**: The generated excuse letter PDF (`src/services/excuse_service.py`) remains in Austrian German (*"Entschuldigung über das Fernbleiben vom Unterricht"*), as it is an official legal HTL school document. The surrounding modal UI (`ExcuseLetterModal`) remains in English.
  3. **Preservation of External School Data**: Incoming school data (course names, assignment titles, instructions from Moodle, Teams, or WebUntis) must be preserved in its original language and not machine-translated. Web scrapers must support dual-language DOM matchers for robust operation.
---

## ADR-011: Decommissioning Proprietary Licensing for Open-Source (MIT) & GitHub Release CI/CD

- **Date**: 2026-10-17
- **Status**: Accepted
- **Context**: The project was migrated from OneDrive to a public Git repository. Proprietary device-activation locks (HMAC-SHA256, hardware ID scanning, secret key embedding) are counterproductive in an open-source codebase. Releases should be distributed transparently via GitHub.
- **Decision**:
  1. Remove hardware-fingerprint scanning and activation gates completely (`src/core/license.py`, startup dialogs in `src/main.py`).
  2. Adopt the permissive **MIT License** for all source code.
  3. Standardize the Inno Setup installer builder (`installer/build_installer.py`) to produce universal installers (`AufgabenDetector_Setup.exe`) without needing recipient names or secret keys.
  4. Automatically download `python_installer.exe` on demand instead of checking 26 MB binaries into the Git repository.
  5. Establish an automated GitHub Actions workflow (`.github/workflows/release.yml`) to compile and attach installers to GitHub Releases on tag pushes (`v*`).
- **Consequences**:
  - Positive: Eliminates developer friction, enables open-source contribution, prevents binary bloat in Git, and automates multi-version installer releases.
  - Negative: None; access control is no longer required for an open-source community tool.

---

## ADR-012: Ultra-HD DeviceScaleFactor & Adaptive DPI Normalization for Digi4School Grabber

- **Date**: 2026-10-18
- **Status**: Accepted
- **Context**: Digital schoolbooks frequently contain fine vector graphics, mathematical symbols, and small typography. At standard resolution (scale 2.0), formulas appeared slightly blurry when zoomed in. Furthermore, users require flexibility to toggle OCR (e.g. for pure image archives), skip TOC extraction, customize quality presets, or manually adjust page numbering offsets.
- **Decision**:
  1. Set default Playwright `device_scale_factor` to **4.0** (Ultra-HD / Retina class) in `Digi4SchoolService`.
  2. Implement dynamic DPI coupling (`effective_dpi = dpi if dpi else int(150 * scale)`), yielding 600 DPI for Scale 4.0 and 300 DPI for Scale 2.0.
  3. Keep the physical PDF page size normalized to standard dimensions (A4/B5) by calculating `(median_px / effective_dpi) * 72.0` pt, so page size remains standard while embedded image sharpness is quadrupled.
  4. Expose CLI flags in `tasks books download`: `--scale` (float), `--quality` (standard, high, ultra), `--dpi` (int), `--no-ocr`, `--no-toc`, `--page-offset` (auto or int), `--visible`, and `--tesseract-cmd`.
  5. Add immediate in-memory password disposal (`del password`) right after filling authentication inputs for zero-knowledge safety.
- **Consequences**:
  - Positive: Crystal-clear 4K/Retina pages for reading on high-DPI tablets and monitors without PDF geometry distortion; versatile options for speed vs. quality.
  - Negative: Higher RAM and processing overhead during parallel OCR when rendering at Ultra-HD (Scale 4.0), which can be tuned down with `--quality standard` when needed.

---

## ADR-013: Pre-Flight Dependency Checker, PyMuPDF Modernization & Theme Favorite Sync

- **Date**: 2026-10-19
- **Status**: Accepted
- **Context**: 
  1. If optional or mandatory dependencies from `requirements.txt` were uninstalled or missing, the application previously fell back silently to the legacy CLI, confusing users who expected the modern Textual TUI.
  2. Legacy `import fitz` triggered a noisy `FutureWarning` deprecation warning from PyMuPDF v1.25+.
  3. Expanding the theme palette from 5 to 21 themes required a way to quickly access favorite themes, which also needed to sync seamlessly across multiple devices via Git Sync.
- **Decision**:
  1. **Pre-Flight Checker (`src/core/dependency_checker.py`)**: Implement a zero-dependency module check before launching the TUI. When requirements are missing, render a structured ASCII warning box with the exact Windows installation command (`python -m pip install -r requirements.txt`) and an interactive `[Y/n]` prompt to install via pip automatically.
  2. **PyMuPDF Modernization**: Standardize imports to `try: import pymupdf as fitz except ImportError: import fitz` across all services (`digi4school_service.py`, `test_excuse_service.py`), eliminating the `FutureWarning` deprecation.
  3. **Favorite Themes Persistence & Multi-Device Sync**: Persist favorite theme IDs in `data/config.json` (`favorite_themes`). Render golden stars (`⭐`) and sort favorites to the top of theme pickers. Support right-click toggling with Textual MRO click suppression (`event.stop()` & `event.prevent_default()`). Update `GitSyncService.merge_config_files` to perform list unions on `favorite_themes`, and trigger async git pushes when favorites change.
- **Consequences**:
  - Positive: Transparent environment diagnostics for end users; deprecation-free console; personal theme favorites synchronize seamlessly across machines without losing custom additions.
  - Negative: Pre-flight check adds ~15ms startup overhead using Python's standard `importlib.util.find_spec`.

---

## ADR-014: Asynchronous GitHub Release Update Notification & Zero-Login Semantic Versioning

- **Date**: 2026-10-19
- **Status**: Accepted
- **Context**: As an open-source project with regular GitHub releases and Inno Setup installer builds, users must be kept informed when new features or bug fixes are published. The notification must not block the fast `< 0.1s` offline launch, must require zero authentication credentials, and must cleanly display installed vs. latest versions in the UI.
- **Decision**:
  1. **Centralized Version Declaration**: Declare `APP_VERSION = "1.0.3"` and `GITHUB_REPO = "X4nd109/Aufgaben-Detector"` in `src/core/config.py`. Expose `get_app_version()`.
  2. **Zero-Login Public GitHub API Query**: Use Python standard `urllib.request` in `src/services/update_service.py` targeting `https://api.github.com/repos/{repo}/releases/latest`. With a 3.0s timeout and unauthenticated GET request, no Git CLI or GitHub account is required. All network errors, timeouts, and rate limits fail silently (`None`).
  3. **Robust Semver Comparison**: Implement `parse_version` and `is_newer_version` using digit tuple extraction and zero-padding (`(1, 0, 3) > (1, 0, 2)`), eliminating extra third-party packaging dependencies.
  4. **Non-Blocking Startup Thread**: In `AufgabenDetectorApp.on_mount()`, launch `_start_update_checker()` in a background daemon thread. When an update is detected, post `UpdateReminderModal` to the UI thread via `self.call_from_thread`.
  5. **UI Integration**:
     - Render white bold version badge in the top-right corner of `SettingsModal` (`#settings_version_tag`).
     - Display `UpdateReminderModal` centered on screen with 1-click `🌐 Open Release in Browser` (`Enter`) and `↩️ Dismiss` (`ESC`).
- **Consequences**:
  - Positive: Seamless, non-intrusive update discovery; 100% offline-friendly with zero login barriers; clean visual version tracking.
  - Negative: Unauthenticated GitHub API calls are subject to IP-level rate limits (60 requests/hr), which fail silently without impacting user workflow.

---

## ADR-015: 5-Tier Hybrid Architecture for Windows Terminal Shortcut Normalization

- **Date**: 2026-10-19
- **Status**: Accepted
- **Context**: 
  1. Standard Windows text editing shortcuts (`Ctrl+Backspace`, `Ctrl+Delete`, `Ctrl+A`, `Home`, `End`, `Shift+Ctrl+Arrows`) are expected by Windows desktop users across all inputs.
  2. In terminal emulators (Windows Terminal, conhost, ConPTY, xterm), modifier states for control codes (especially `Ctrl+Backspace`, which transmits `\x08` or `\x7f`) are frequently swallowed or mapped to plain `backspace` by Textual's parser.
  3. When mapped to `backspace`, key events bubbled to global App bindings, causing `Ctrl+Backspace` to erroneously trigger `action_open_courses_palette` (opening the menu) on the main screen or `action_delete_left` (closing the palette) in `UnifiedCommandInput`.
- **Decision**: Implement a 5-tier hybrid defense architecture:
  1. **Win32 Driver Patch (`patch_win32_event_monitor`)**: Monkeypatch Textual's `win32.EventMonitor.run` to intercept `VK_BACK` / `\x08` / `\x7f` with `dwControlKeyState & 0x000C` and emit the Kitty sequence `\x1b[127;5u`. Ensure synthesized ConPTY events with `wVirtualKeyCode == 0` containing characters are not discarded.
  2. **Hardware Keyboard Hook (`is_ctrl_pressed_win32`)**: Hook `Input._on_key` and `TextArea._on_key`. Query the OS directly via `user32.GetAsyncKeyState(0x11)` (`VK_CONTROL`). When `backspace` or `delete` is detected while Ctrl is down, immediately stop event propagation (`event.stop()`, `event.prevent_default()`) and trigger word deletion.
  3. **CommandPalette Guard**: In `UnifiedCommandInput.action_delete_left()`, check `is_ctrl_pressed_win32()`; if active, delegate to `action_delete_left_word()` to prevent accidental palette dismissal.
  4. **App Menu Guard**: In `AufgabenDetectorApp.action_open_courses_palette()`, verify `is_ctrl_pressed_win32()` is False before opening the palette.
  5. **Standard Bindings**: Maintain explicit bindings for `ctrl+backspace,ctrl+w,ctrl+h` and `ctrl+delete,alt+delete` across all inputs.
- **Consequences**:
  - Positive: 100% reliable word deletion across all terminal emulators on Windows; zero collisions with global Backspace shortcuts; graceful fallback on non-Windows platforms.
  - Negative: Direct Win32 API calls (`ctypes.windll.user32`) are platform-specific, guarded by `if os.name == "nt"`.

---

## ADR-016: Per-Monitor DPI-Awareness v2 & Native Windows COM Dialog Architecture

- **Date**: 2026-10-20
- **Status**: Accepted
- **Context**: 
  1. On modern multi-monitor and high-DPI displays (4K, 1440p, 125%–200% scaling), legacy file/folder dialogs (e.g. Tkinter `filedialog` or default Windows Forms) appeared blurry due to DWM bitmap stretching („Low-Res-Explorer-Effekt“) and lacked native Windows Shell navigation (Quick Access, Search, breadcrumbs).
  2. The application required true native Windows 11/10 Explorer picker dialogs for linking schoolbooks (files) and course directories (folders) without external GUI dependencies.
- **Decision**:
  1. **Central Windows Dialog Module (`src/core/win_dialogs.py`)**: Implement `enable_high_dpi_awareness()` invoking `user32.SetProcessDpiAwarenessContext(HANDLE(-4))` (`DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2`) at startup and prior to dialog invocation.
  2. **Native COM `IFileOpenDialog` Implementation**: Implement direct COM vtable calls via `ctypes` (`CLSID_FileOpenDialog`, `IID_IFileOpenDialog`) with `FOS_PICKFOLDERS` for directory selection and file filters for PDF selection.
  3. **Multi-Tier Fallback Cascade**: If COM initialization fails or runs in headless/cross-platform environments, fall back gracefully to DPI-aware Tkinter and PowerShell Windows Forms.
- **Consequences**:
  - Positive: Crystal-clear, native Windows Explorer dialogs with Quick Access and address bar search; zero third-party GUI library dependencies (PyQt/wxWidgets).
  - Negative: Direct COM vtable dispatch via `ctypes` requires careful memory management (`Release()` calls in `finally` blocks).

---

## ADR-017: In-App Auto-Update Pipeline via Detached Runner & Proportional Full-Width Layout

- **Date**: 2026-10-20
- **Status**: Accepted
- **Context**:
  1. When a new GitHub release is available, downloading the `.exe` manually from the browser creates unnecessary friction for users.
  2. Installing updates must strictly preserve the existing installation directory, existing user settings (`config.json`), user data (`data/`), and caches (`cache/`), while avoiding changes to the Windows User `PATH` (skipping `tasks` command setup).
  3. When running on wide screens (e.g. 140–180 columns), `ExamsScreen` previously left large empty areas on the right side and truncated topic descriptions prematurely.
- **Decision**:
  1. **1-Click In-App Downloader**: Add chunk-based downloading with Textual `ProgressBar`, real-time MB and speed tracking, and cancellation events directly into `UpdateReminderModal`.
  2. **Detached Runner Architecture (`apply_update.cmd`)**: Generate a temporary batch script in `%TEMP%\AufgabenDetector_Update\apply_update.cmd`. The script waits for the active Python PID to exit, executes Inno Setup silently (`/DIR="<dir>" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOTASKS=1 /UPDATE=1`), runs `setup.bat /silent` for background pip updates, and restarts the TUI via `run.bat`.
  3. **Preservation & Path Guards**: Configure `installer/aufgaben_detector.iss` to check `/NOTASKS=1` and skip running `setup_command.bat`.
  4. **Proportional Full-Width Column Distribution**: Calculate available width dynamically in `ExamsScreen`, assign explicit column widths (`col.width`, `auto_width = False`), allocate 60 % of extra width to `Topic / Notes`, and reserve a 1-character buffer for vertical scrollbars to prevent horizontal scrollbars on any screen width.
- **Consequences**:
  - Positive: Frictionless 1-click updates without leaving the terminal; zero data loss; clean full-width UI utilization on widescreen displays.
  - Negative: Inno Setup compilation is required for testing end-to-end silent installer execution.

---

## ADR-018: Column Prioritization Budgeting & Jitter-Free Single-Line Info Bar

- **Date**: 2026-10-20
- **Status**: Accepted
- **Context**:
  1. On multi-monitor setups (e.g. 4K with 150% scaling alongside 1440p displays), starting a background sync dynamically toggled `SyncSpinner` visibility, shrinking available horizontal width and pushing the sync timestamp (`19:09:06`) onto a second line.
  2. The table column header `Teacher` (7 letters) had a hardcoded base width of 6 characters, truncating it to `Teache`.
  3. Under standard window widths, `Assignment` previously consumed ~73 % of extra space, forcing full due dates (e.g. `Montag, 2. November, 23:59`) and teacher abbreviations to truncate prematurely.
- **Decision**:
  1. **Strict Single-Line Info Bar with Spacing**: Lock `#info_bar` and `#info_stats` to `height: 1` with `overflow-y: hidden; overflow-x: hidden;` and add `margin-bottom: 1;` to guarantee an empty separator line above the table without allowing text wrapping.
  2. **Zero-Layout-Shift Sync Spinner**: Assign `SyncSpinner` a permanent `display: block; width: 3; height: 1;` footprint so activating background sync alters available width by exactly 0 characters.
  3. **Priority Column Budgeting**:
     - Preserve full `Due Date` (base 28–32 chars) and full `Teacher` (min. 8 chars, 7 on tiny windows).
     - Allocate all remaining flexible width to `Assignment` (`avail_content - sum(others)`), making it the primary column to absorb window shrinkage with clean `...` truncation.
  4. **Post-Mount 4K/1440p Viewport Calibration**: In `_sync_initial_viewport()`, trigger `refresh_table()` once Textual finishes the DOM layout pass and true container dimensions are measured.
- **Consequences**:
  - Positive: Zero visual jitter during background sync; no truncation of headers or complete due dates; immediate adaptation on 4K and 1440p monitors upon launch.
  - Negative: On unusually narrow terminals (< 80 columns), `Assignment` titles are heavily truncated with `...` to preserve due dates and teacher codes.

---

## ADR-019: In-Terminal Synchronous Update Loop & Multi-Tier Sync Lag Elimination

- **Date**: 2026-10-21
- **Status**: Accepted
- **Context**:
  1. In-app updating previously relied on detached background helper scripts or external PowerShell commands, which popped up secondary windows, interrupted the user workflow, and re-executed `setup.bat /silent` (redundant pip dependency resolution).
  2. The onboarding Getting Started guide was permanently lost if a user had previously marked it done or deleted it before updating.
  3. During live background sync across Moodle and Teams, the TUI experienced extreme lag:
     - `SyncSpinner` fired every 80 ms (12.5 FPS), flooding Textual's Asyncio loop and Windows ConPTY ANSI parser.
     - Rapid multi-platform sync callbacks triggered multiple back-to-back `dt.clear()` table rebuilds.
     - `save_cache()` held the synchronization lock across disk writes, and the prefetcher saved to disk after every single item.
     - Headless Chromium spiked CPU without renderer limits or GPU disabling.
- **Decision**:
  1. **In-Terminal Update Loop (Exit Code 42 & `run.bat`)**:
     - `UpdateReminderModal` drops `%TEMP%\AufgabenDetector_Update\pending_update.txt` and exits with code 42.
     - `run.bat` catches exit code 42 and executes the silent Inno Setup installer via `start /wait` in the existing console without spawning extra windows, then loops to re-launch `main.py`.
     - Omit `setup.bat` during updates, relying on `dependency_checker.py` at launch.
  2. **Getting Started Auto-Restoration**:
     - `TaskManager._check_and_apply_version_update` detects updates via version delta or update markers, restoring `manual_welcome_setup_guide` to `Open` at index 0.
     - Rewrote guide text to reference actual UI buttons (`⚙️ Settings`, `🔑 Login`, `🔄 Sync`, `✓ Mark as Completed`, `🗑️ Delete`) in English.
  3. **Multi-Tier Sync Performance Optimizations**:
     - Throttled `SyncSpinner` animation to 250 ms (4 FPS), reducing event loop overhead by >65%.
     - Decoupled stats bar into `update_info_bar()` and throttled `refresh_table()` to max once every 0.8s during batch sync updates.
     - Unlocked atomic cache disk writes (`save_cache()`) and batched prefetch disk writes (every 5 tasks).
     - Configured `--disable-gpu`, `--disable-dev-shm-usage`, and `--renderer-process-limit=2` in Chromium headless args.
     - Relaxed mouse-back polling from 25 ms to 60 ms.
- **Consequences**:
  - Positive: Zero UI lag during sync; responsive 60 FPS interactions; clean in-terminal update without secondary popups; automatic onboarding guide recovery.
  - Negative: Table rows during multi-platform sync update at up to 0.8s intervals rather than per item (status bar updates immediately).

---

## ADR-020: Browserless HTTP Moodle Authentication & Resilient WebUntis Discovery

- **Date**: 2026-10-21
- **Status**: Accepted
- **Context**:
  1. On freshly set up devices where users simply ran `pip install -r requirements.txt`, Moodle login failed because `login_moodle_direct` unconditionally invoked Playwright's headless Chromium (`p.chromium.launch(headless=True)`). The Playwright Python package does not install Chromium binaries by default (`~150MB` download), causing silent failures and misleading error messages.
  2. WebUntis URL parsing was brittle: entering domains (`spengergasse.webuntis.com`) resulted in duplicated subdomains (`https://spengergasse.webuntis.com.webuntis.com`), and school display names with spaces (`HTL Spengergasse`) threw unhandled `InvalidURL` exceptions. Furthermore, leaving the school field empty failed instead of falling back to the configured school.
  3. Students frequently enter their full school email address (`user@spengergasse.at`) rather than their student ID (`user`), which both Moodle and WebUntis API reject with `bad credentials`.
- **Decision**:
  1. **Pure HTTP Moodle Authentication (`login_moodle_http`)**:
     - Perform direct HTTP form POST to `/login/index.php` using `requests.Session`.
     - Dynamically extract the hidden CSRF `logintoken` from the login page.
     - Persist `MoodleSession` cookies directly.
     - Fall back to Playwright (with fallback channels: system Chrome, Edge, and Chromium) only if HTTP authentication fails or JS challenges are encountered.
  2. **Resilient WebUntis Server Resolution (`resolve_webuntis_server`)**:
     - Normalize school identifiers via `clean_school_identifier` to strip protocol, paths, and duplicated `.webuntis.com` domains.
     - Integrate the official WebUntis School Search API (`https://mobile.webuntis.com/ms/schoolquery2`) to automatically look up `loginName` and official `serverUrl` when display names or spaces are provided.
     - Default to the configured school (`spengergasse`) when the dialog school input is left blank.
  3. **Automatic School Username Sanitization (`clean_school_username`)**:
     - Strip school email domain suffixes (`@spengergasse.at` or any `@...`) before submitting credentials to Moodle and WebUntis.
  4. **Rich Status Feedback (`AuthResult`)**:
     - Return an `AuthResult` tuple subclass `(success: bool, message: str)` that propagates specific server error messages (e.g. invalid credentials, unreachable host) directly into TUI login status labels while maintaining 100% backward compatibility with boolean checks (`if res:`).
  5. **Pre-Flight Playwright Chromium Detection**:
     - Add `check_playwright_chromium_installed` via `p.chromium.executable_path` without process launches, and auto-install browser binaries during `run_pip_install` if missing.
- **Consequences**:
  - Positive: Moodle login works instantly (<0.3s) on any clean Python environment without needing a 150 MB Playwright Chromium download; WebUntis login accepts all common URL, domain, or display name formats; clear and actionable error messages in the UI; prevents user credential errors from email suffixes.
  - Negative: If Moodle ever introduces JavaScript-heavy bot challenges or Captchas, the HTTP login will fail and trigger the heavier Playwright browser fallback.

---

## ADR-021: Agent Harness Decommissioning in Favor of Global Skill and Smart Download Auto-Dir

- **Date**: 2026-10-23
- **Status**: Accepted
- **Context**:
  1. The built-in Agent button (`[G]`) exported assignments and launched local IDEs/tools via a dedicated harness. However, autonomous coding agents (Antigravity, Claude Code, Cursor) already leverage the token-efficient global `/tasks` skill (`skills/tasks/SKILL.md`) for headless programmatic interaction, rendering an in-app agent launcher redundant and cluttering the UI.
  2. Manual folder selection for assignment downloads was repetitive and slow, requiring users to navigate through Windows file picker trees repeatedly.
- **Decision**:
  1. **Decommission Agent Button & Harness**:
     - Remove the TUI Agent button (`#btn_det_agent`), keybinding `[G]`, `action_agent_open`, `AiAgentConfigModal`, and the intermediate `AiConfigChoiceModal`.
     - Remove CLI subcommand `tasks agent` and service `src/services/ai_agent_service.py`.
     - Direct Settings option `🤖 AI Explain Config` straight to `AiExplainModal`.
  2. **Smart Download Destination Selection (`DownloadLocationModal`)**:
     - When pressing `Download [D]`, display a streamlined modal with 1-keypress hotkeys (`[1]`, `[2]`, `[3]`, `[ESC]`).
     - Option 1 (`[1]`): Automatically matches the linked course directory (`DirectoryService.find_matching_directory_for_course`), creates a dedicated task subfolder, and downloads files there. Disabled with clear feedback if no folder is linked.
     - Option 2 (`[2]`): Opens native Windows Explorer folder picker for custom destinations.
     - Option 3 (`[3]`): Default Windows Downloads folder (`Downloads/<Subject> - <Title>/`).
  3. **Headless CLI Auto-Dir**:
     - Introduce `--auto-dir` (`-a`) flag for `tasks download <id>`.
- **Consequences**:
  - Positive: Drastically cleaner UI and reduced code footprint; downloads are fast and directly organized into course folder hierarchies; seamless integration with the global agent skill.
  - Negative: None; users needing full agent workflows use the dedicated global skill.

---

## ADR-022: On-Demand Lazy Subsystem Loading & Non-Blocking Startup Optimization

- **Date**: 2026-10-23
- **Status**: Accepted
- **Context**:
  1. Cold start of the TUI application required ~1.88 seconds. Profiling revealed that top-level imports of heavy third-party packages (`fpdf2` in `excuse_service`: ~0.68s, `PyMuPDF`/`fitz`, `PIL`, `pytesseract` in `digi4school_service`: ~0.27s, and `playwright` + `requests` in `auth`: ~0.38s) accounted for over 85% of launch latency, even though 99% of user sessions do not immediately generate excuse PDFs or grab Digi4School textbooks.
  2. The pre-render browser cache maintenance function (`clean_browser_profile_caches()`) synchronously walked profile directory trees (`os.walk`), adding ~0.22 seconds of disk latency on every launch.
  3. The `FilterMenuModal` did not support vertical scrolling on smaller terminal heights (e.g. 80x20), causing buttons and dialog footers to clip.
- **Decision**:
  1. **Lazy Loading of Heavy Subsystems**:
     - Remove eager top-level imports for `excuse_service` (`create_excuse_pdf`, `open_pdf_in_system_viewer`) and `digi4school_service` (`Digi4SchoolService`, `find_tesseract`) in `src/ui/tui_app.py`. Import them on-demand strictly inside the functions and modal handlers where they are actively used.
     - Remove eager `auth` setup imports from `src/main.py`, importing them only if explicit login CLI flags (`--moodle-login`, `--teams-login`) are invoked.
  2. **Non-Blocking Background Cache Cleanup**:
     - Wrap `clean_browser_profile_caches()` in an asynchronous daemon thread inside `run_tui()`:
       ```python
       if AUTO_CLEAN_BROWSER_CACHE:
           threading.Thread(target=clean_browser_profile_caches, daemon=True, name="BrowserCacheCleanup").start()
       ```
  3. **Responsive Filter Menu Viewport**:
     - Upgrade `#filter_dialog` in `FilterMenuModal` to use `VerticalScroll` with `overflow-y: auto;` and `scrollbar-gutter: stable;`.
- **Consequences**:
  - Positive: Application startup latency is reduced by ~40% (from 1.88s down to 1.12s); memory and token footprints are reduced; Filter dialog is fully responsive across small terminal windows.
  - Negative: Import or configuration errors in lazy-loaded subsystems will surface when the respective feature is first invoked rather than during application bootstrap.
