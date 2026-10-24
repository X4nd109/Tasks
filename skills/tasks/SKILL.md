---
name: tasks
description: Manage and access school assignments, materials, books, and courses via the Aufgaben-Detector CLI.
---

# Aufgaben-Detector CLI Reference (tasks)

Use the `tasks` CLI to query assignments, download exercise files, link directories, and access schoolbooks without opening any GUI or browser.

All commands operate on a lightning-fast local cache (<0.1s). Always pass `--json` when parsing programmatically to save tokens and avoid ANSI terminal formatting.

---

## 1. Quick Workflow for Assignments

1. **List open assignments**:
   ```powershell
   tasks list -s open --json
   ```
   *Optional filters:* `-s all|completed|overdue`, `-f <fach>` (e.g. `-f amec`), `-p moodle|teams|manual`.

2. **Inspect details of an assignment**:
   ```powershell
   tasks show <id|index> --json
   ```
   *Supports either the 1-based index from the last `tasks list` or the exact ID (e.g. `1` or `moodle_10421`).*

3. **Download attachments & specification (`angabe.md`)**:
   ```powershell
   tasks download <id|index> [--auto-dir] [--dir "<zielpfad>"] --json
   ```
   *Downloads all PDFs, code files, and generates an `angabe.md`. Pass `--auto-dir` (`-a`) to automatically save into the matched linked course directory. If `--dir` and `--auto-dir` are omitted, saves to default Downloads.*

4. **Toggle completion status**:
   ```powershell
   tasks done <id|index> --json
   ```

5. **Hide or delete assignment**:
   ```powershell
   tasks delete <id|index> --json
   ```
   *Restore with:* `tasks restore <id|index> --json`

6. **Create a manual homework item**:
   ```powershell
   tasks add --title "<titel>" --subject "<fach>" --due "YYYY-MM-DD" --desc "<beschreibung>" --json
   ```

---

## 2. Live Network Synchronization

Querying `tasks list` reads from offline cache. To refresh live from Moodle & Teams:
```powershell
tasks sync --json
```
*Deep scan of all historical Moodle courses:* `tasks sync --deep --json`.

---

## 3. Courses & Web Navigation

- **List all enrolled Moodle & Teams courses**:
  ```powershell
  tasks courses --json
  ```
- **Open a course in default browser**:
  ```powershell
  tasks open <fach_oder_name>
  ```
  *(e.g. `tasks open amec` or `tasks open mathe`)*

---

## 4. Linked Directories & Schoolbooks

- **Directories** (Quick access to school project folders):
  - `tasks dirs list --json`: List all linked directories.
  - `tasks dirs open <id|index|name>`: Open folder in Windows Explorer.
  - `tasks dirs add "<path>" [--title "<name>"] --json`: Link a new directory.
  - `tasks dirs remove <id|index> --json`: Unlink a directory.

- **Schoolbooks** (PDFs & Digi4School):
  - `tasks books list --json`: List linked schoolbooks.
  - `tasks books open <id|index>`: Open book in PDF reader / browser.
  - `tasks books add "<path_oder_url>" [--title "<name>"] --json`: Link a book.
  - `tasks books download <12_digit_code> --email "..." --password "..." --json`: Download Digi4School book with OCR.

---

## 5. Skill Management

- **Update / Sync this skill globally**:
  ```powershell
  tasks skill sync --json
  ```
- **Check installation status**:
  ```powershell
  tasks skill status --json
  ```
