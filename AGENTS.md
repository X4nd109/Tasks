# AGENTS.md — Tasks Master Index & Guidelines

> **Project**: Tasks (Moodle, Microsoft Teams & WebUntis)  
> **Tech Stack**: Python 3.10+, Textual, Playwright, Requests, ReportLab / PyMuPDF  
> **Documentation Root**: `docs/`

---

## 1. Quick Reference & Commands

- **Run TUI (Development)**: `python main.py`
- **CLI (Dev)**: `python main.py <cmd>`
  - `list [-s all|open|overdue] [-f <fach>] [--json]` | `show <id|index> [--json]`
  - `download <id|index> [--auto-dir]` | `explain <id|index>` | `sync [--deep]`
  - `books [list|open|download|compact]` | `dirs [list|open]` | `open <fach>`
  - `tray [status|enable|disable]` | `autostart [status|enable|disable]` | `skill [sync|status|set-dir]`
  - `update [--force]` | `.\update.bat`
- **Installed Distribution (End-User)**: `tasks <cmd>` / `Tasks.exe` (aus `dist\Tasks\`)
- **Build Standalone Binaries**: `.\build.bat` or `python scripts/build_exe.py`
- **Tests**: `python -m unittest discover tests` | **Dependencies**: `pip install -r requirements.txt`

---

## 2. Documentation Matrix (Progressive Disclosure)

> [!IMPORTANT]
> **Do not load all doc files at once!** Read ONLY the file relevant to your immediate task via `view_file`.

| Document | Purpose / Topics Covered | When to Read |
| :--- | :--- | :--- |
| [`docs/current-state.md`](docs/current-state.md) | **Session Handoff**, aktive Meilensteine, nächste Schritte | Jeder Session-Start / Status |
| [`docs/project-overview.md`](docs/project-overview.md) | Vision, Scope, Features & Plattformen | Beginn neuer Major Features |
| [`docs/architecture.md`](docs/architecture.md) | Komponenten (`core`, `services`, `ui`), Datenflüsse | Architektur- & API-Änderungen |
| [`docs/conventions.md`](docs/conventions.md) | Code-Style, Zero-Knowledge-Regeln, CLI-Standards | Beim Schreiben von Code/Tests |
| [`docs/decisions.md`](docs/decisions.md) | Architecture Decision Records (ADRs) | Vor Architekturentscheidungen |
| [`docs/features.md`](docs/features.md) | Feature- & UI-Katalog (Buttons, Shortcuts, Views) | Bearbeitung von UI/Features |
| [`docs/tutorials/git-sync.md`](docs/tutorials/git-sync.md) | Git Cloud-Sync Setup Guide | Cloud-Sync Einrichtung & Support |
| [`docs/changelog.md`](docs/changelog.md) | Versionierung & Historie (Keep a Changelog) | Releases & Versionsvergleiche |

---

## 3. Agent Protocol & Memory Maintenance

1. **Start of Task**: Consult [`docs/current-state.md`](docs/current-state.md) to pick up with zero knowledge loss.
2. **During Task**: Strictly follow rules in [`docs/conventions.md`](docs/conventions.md) and respect [`docs/decisions.md`](docs/decisions.md).
3. **End of Task / Session Handoff**:
   - Update [`docs/current-state.md`](docs/current-state.md) (mark finished items `[x]`, list next steps `[ ]`).
   - If architecture, APIs, or conventions change, update the corresponding `docs/*.md` file.
   - Keep this `AGENTS.md` lean (< 3 KB).
