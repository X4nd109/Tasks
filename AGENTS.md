# AGENTS.md — Tasks Master Index & Guidelines

> **Project**: Tasks (Moodle, Microsoft Teams & WebUntis)  
> **Tech Stack**: Python 3.10+, Textual, Playwright, Requests, ReportLab / PyMuPDF  
> **Documentation Root**: `docs/`

---

## 1. Quick Reference & Commands

- **Run TUI (Interactive)**: `python main.py` or `.\run.bat`
- **Run CLI (Agent / Headless)**: `.\tasks.bat <cmd>` or `python main.py <cmd>`
  - `tasks list [-s all|open|overdue|completed] [-f <fach>] [--json]`
  - `tasks show <id|index> [--json]` | `tasks download <id|index> [--auto-dir] [--dir <path>]`
  - `tasks explain <id|index> [--lang de|en] [--copy-only] [--json]`
  - `tasks books [list|open|add|remove|download] [--json]` | `tasks dirs [list|open|add|remove] [--json]`
  - `tasks sync [--deep]` | `tasks open <fach>` | `tasks skill [sync|status] [--json]`
- **Tests**: `python -m unittest discover tests` or `pytest tests/`
- **Setup & Dependencies**: `.\setup.bat`

---

## 2. Documentation Matrix (Progressive Disclosure)

> [!IMPORTANT]
> **Do not load all doc files at once!** Consult this matrix and read ONLY the file relevant to your immediate task via `view_file`.

| Document | Purpose / Topics Covered | When to Read (Trigger Condition) |
| :--- | :--- | :--- |
| [`docs/current-state.md`](docs/current-state.md) | **Session Handoff**, aktive Meilensteine, nächste Schritte | **Jeder Session-Start** / Statusabfragen |
| [`docs/project-overview.md`](docs/project-overview.md) | Vision, Scope, Features & Plattformen | Beginn neuer Major Features |
| [`docs/architecture.md`](docs/architecture.md) | Komponenten (`core`, `services`, `ui`), Datenflüsse & Caching | Architektur- & API-Änderungen |
| [`docs/conventions.md`](docs/conventions.md) | Code-Style, Zero-Knowledge-Regeln, CLI-Standards | Beim Schreiben von Code/Tests |
| [`docs/decisions.md`](docs/decisions.md) | Architecture Decision Records (ADRs) | Vor Architekturentscheidungen |
| [`docs/features.md`](docs/features.md) | Feature- & UI-Katalog (Buttons, Shortcuts, Views) | Bearbeitung von UI/Features |
| [`docs/tutorials/git-sync.md`](docs/tutorials/git-sync.md) | Schritt-für-Schritt Git Cloud-Sync Setup Guide | Cloud-Sync Einrichtung & Support |
| [`docs/changelog.md`](docs/changelog.md) | Versionierung & Historie (Keep a Changelog) | Releases & Versionsvergleiche |

---

## 3. Agent Protocol & Memory Maintenance

1. **Start of Task**: Consult [`docs/current-state.md`](docs/current-state.md) to pick up with zero knowledge loss.
2. **During Task**: Strictly follow rules in [`docs/conventions.md`](docs/conventions.md) and respect [`docs/decisions.md`](docs/decisions.md).
3. **End of Task / Session Handoff**:
   - Update [`docs/current-state.md`](docs/current-state.md) (mark finished items `[x]`, list next steps `[ ]`).
   - If architecture, APIs, or conventions change, update the corresponding `docs/*.md` file.
   - Keep this `AGENTS.md` lean (< 3 KB).
