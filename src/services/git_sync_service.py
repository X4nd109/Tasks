"""
git_sync_service.py - Synchronisation von Aufgaben, Prüfungen, Notizen und Konfiguration
über ein privates Git-Repository (GitHub, GitLab, etc.).
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

from config import (
    CONFIG_FILE,
    APP_CONFIG_FILE,
    DATA_DIR,
    GIT_SYNC_CONFIG_FILE,
    GIT_SYNC_WORK_DIR,
    CUSTOM_TASKS_FILE,
    APP_CUSTOM_TASKS_FILE,
    CUSTOM_EXAMS_FILE,
    APP_CUSTOM_EXAMS_FILE,
    DELETED_TASKS_FILE,
    APP_DELETED_TASKS_FILE,
    DELETED_MANUAL_TASKS_FILE,
    APP_DELETED_MANUAL_TASKS_FILE,
    HIDDEN_TASKS_FILE,
    APP_HIDDEN_TASKS_FILE,
    APP_UNTIS_EXAM_NOTES_FILE,
    UNTIS_EXAM_NOTES_FILE,
    load_saved_theme,
    save_saved_theme,
    get_git_sync_config,
    save_git_sync_config,
    remove_git_sync_config,
)

logger = logging.getLogger("GitSyncService")

# Windows flag: keine schwarze CMD-Konsole im Hintergrund aufpoppen lassen
_NO_WINDOW_FLAG = 0x08000000 if sys.platform == "win32" else 0
_sync_lock = threading.RLock()

# Sicherstellen, dass _sync_lock über alle Import-Pfade geteilt wird
for _mod_name in ["git_sync_service", "src.services.git_sync_service", "services.git_sync_service"]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = sys.modules.get(__name__)


def is_git_available() -> bool:
    """Prüft, ob 'git' auf dem System installiert und im PATH verfügbar ist."""
    try:
        res = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            creationflags=_NO_WINDOW_FLAG,
            timeout=5,
        )
        return res.returncode == 0
    except Exception:
        return False


def is_git_configured() -> bool:
    """Prüft, ob ein Git-Repository eingerichtet und aktiviert ist."""
    cfg = get_git_sync_config()
    return bool(cfg.get("enabled") and cfg.get("repo_url"))


def mask_git_url(url: str) -> str:
    """Maskiert Tokens oder Passwörter in einer Git-URL für sichere Logs und UI-Ausgaben."""
    if not url:
        return ""
    # Erkennt URLs wie https://TOKEN@github.com/... oder https://USER:TOKEN@github.com/...
    pattern = r"(https?://)([^@:]+)(:[^@]+)?@"
    return re.sub(pattern, r"\1***@", url)


def build_authenticated_url(repo_url: str, token: str) -> str:
    """
    Baut aus einer Standard-HTTPS-URL und einem Personal Access Token
    eine authentifizierte URL, z. B. https://<token>@github.com/user/repo.git
    """
    clean_url = repo_url.strip()
    clean_token = token.strip()
    if not clean_token:
        return clean_url

    parsed = urlparse(clean_url)
    if parsed.scheme in ["http", "https"]:
        # Wenn bereits ein Benutzername/Token in der URL war, ersetzen wir ihn
        host = parsed.netloc.split("@")[-1]
        auth_netloc = f"{clean_token}@{host}"
        return urlunparse((
            parsed.scheme,
            auth_netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        ))
    return clean_url


def _clean_stale_git_locks(work_dir: str) -> None:
    """Entfernt verwaiste Git-Lock-Dateien (.git/index.lock etc.), falls ein Vorprozess unerwartet beendet wurde."""
    git_dir = os.path.join(work_dir, ".git")
    if not os.path.exists(git_dir):
        return
    for root, _, files in os.walk(git_dir):
        for f in files:
            if f.endswith(".lock"):
                lock_file = os.path.join(root, f)
                try:
                    os.remove(lock_file)
                except Exception:
                    pass


def _run_git_cmd(
    args: List[str],
    cwd: Optional[str] = None,
    timeout: int = 30,
) -> Tuple[bool, str, str]:
    """Führt einen Git-Befehl aus und fängt Ausgaben ab."""
    target_cwd = cwd or GIT_SYNC_WORK_DIR
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = ""
    env["SSH_ASKPASS"] = ""
    env["GCM_INTERACTIVE"] = "never"
    try:
        os.makedirs(target_cwd, exist_ok=True)
        cmd = ["git", "-c", "credential.helper=", "-c", "core.askPass="] + args
        proc = subprocess.run(
            cmd,
            cwd=target_cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_NO_WINDOW_FLAG,
            timeout=timeout,
        )
        if proc.returncode != 0 and ("index.lock" in proc.stderr or "Unable to create" in proc.stderr):
            # Verwaiste Lock-Datei entfernen und Befehl einmal wiederholen
            _clean_stale_git_locks(target_cwd)
            proc = subprocess.run(
                cmd,
                cwd=target_cwd,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_NO_WINDOW_FLAG,
                timeout=timeout,
            )
        return (proc.returncode == 0, proc.stdout.strip(), proc.stderr.strip())
    except subprocess.TimeoutExpired:
        return (False, "", "Git command timed out.")
    except Exception as e:
        return (False, "", str(e))


def _safe_rmtree(path: str) -> None:
    """Löscht einen Ordner sicher unter Windows, auch wenn schreibgeschützte .git-Dateien enthalten sind."""
    if not os.path.exists(path):
        return
    import stat
    def _onerror(func, p, excinfo):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass
    try:
        shutil.rmtree(path, onerror=_onerror)
    except Exception:
        pass


def is_valid_git_repo(work_dir: str) -> bool:
    """Prüft, ob work_dir ein voll funktionsfähiges, nicht-korruptes Git-Repository ist."""
    if not work_dir or not os.path.exists(work_dir):
        return False
    git_dir = os.path.join(work_dir, ".git")
    if not os.path.exists(git_dir):
        return False
    head_file = os.path.join(git_dir, "HEAD")
    if not os.path.exists(head_file):
        return False
    ok, out, _ = _run_git_cmd(["rev-parse", "--is-inside-work-tree"], cwd=work_dir, timeout=5)
    return ok and out.strip() == "true"


def cleanup_legacy_sync_repo_files(work_dir: str) -> bool:
    """
    Erkennt veraltete 'aufgaben_detector_*.json'-Dateien im Git-Sync-Repository,
    migriert deren Inhalt bei Bedarf in die Standarddateien und entfernt sie per 'git rm -f',
    damit das Remote-Repository sauber bereinigt wird.
    """
    if not work_dir or not os.path.exists(work_dir):
        return False
    repo_data_dir = os.path.join(work_dir, "data")
    os.makedirs(repo_data_dir, exist_ok=True)
    cleaned = False

    # 1. Config: aufgaben_detector_config.json -> config.json
    for old_cfg in [
        os.path.join(work_dir, "aufgaben_detector_config.json"),
        os.path.join(repo_data_dir, "aufgaben_detector_config.json"),
    ]:
        if os.path.exists(old_cfg):
            target_cfg = os.path.join(work_dir, "config.json")
            if not os.path.exists(target_cfg):
                try:
                    shutil.copy2(old_cfg, target_cfg)
                except Exception:
                    pass
            rel = os.path.relpath(old_cfg, work_dir).replace("\\", "/")
            try:
                os.remove(old_cfg)
            except Exception:
                pass
            _run_git_cmd(["rm", "-f", rel], cwd=work_dir)
            cleaned = True

    # 2. Data files: aufgaben_detector_*.json -> data/*.json
    mapping = [
        ("aufgaben_detector_custom_tasks.json", "custom_tasks.json"),
        ("aufgaben_detector_custom_exams.json", "custom_exams.json"),
        ("aufgaben_detector_deleted_manual_tasks.json", "deleted_manual_tasks.json"),
        ("aufgaben_detector_hidden_tasks.json", "hidden_tasks.json"),
        ("aufgaben_detector_deleted_tasks.json", "deleted_tasks.json"),
    ]
    for old_name, new_name in mapping:
        for old_dir in [work_dir, repo_data_dir]:
            old_p = os.path.join(old_dir, old_name)
            if os.path.exists(old_p):
                new_p = os.path.join(repo_data_dir, new_name)
                if not os.path.exists(new_p):
                    try:
                        shutil.copy2(old_p, new_p)
                    except Exception:
                        pass
                rel = os.path.relpath(old_p, work_dir).replace("\\", "/")
                try:
                    os.remove(old_p)
                except Exception:
                    pass
                _run_git_cmd(["rm", "-f", rel], cwd=work_dir)
                cleaned = True

    # 3. Alle weiteren aufgaben_detector_*.json im gesamten Repo entfernen
    for root, _, files in os.walk(work_dir):
        if ".git" in root:
            continue
        for f in files:
            if f.startswith("aufgaben_detector_") and f.endswith(".json"):
                f_p = os.path.join(root, f)
                rel = os.path.relpath(f_p, work_dir).replace("\\", "/")
                try:
                    os.remove(f_p)
                except Exception:
                    pass
                _run_git_cmd(["rm", "-f", rel], cwd=work_dir)
                cleaned = True

    return cleaned


# ---------------------------------------------------------
# Smart JSON-Merge Hilfsfunktionen
# ---------------------------------------------------------

def merge_custom_tasks(
    local_tasks: List[dict],
    remote_tasks: List[dict],
    deleted_ids: Optional[set] = None,
) -> List[dict]:
    """
    Führt zwei Listen von Aufgaben anhand ihrer IDs zusammen.
    Bei ID-Gleichheit gewinnt der Datensatz mit neuerem Status oder Zeitstempel.
    Aufgaben in deleted_ids werden strikt herausgefiltert.
    """
    del_set = {str(x).strip() for x in deleted_ids} if deleted_ids else set()
    task_map: Dict[str, dict] = {}

    for t in local_tasks:
        tid = str(t.get("id", "")).strip()
        if tid and tid not in del_set:
            task_map[tid] = dict(t)

    for rt in remote_tasks:
        tid = str(rt.get("id", "")).strip()
        if not tid or tid in del_set:
            continue
        if tid not in task_map:
            task_map[tid] = dict(rt)
        else:
            local_item = task_map[tid]
            if rt.get("status") in ["erledigt", "completed"] and local_item.get("status") not in ["erledigt", "completed"]:
                task_map[tid] = dict(rt)
            elif local_item.get("status") in ["erledigt", "completed"]:
                pass
            else:
                rt_ts = float(rt.get("due_timestamp") or 0)
                lt_ts = float(local_item.get("due_timestamp") or 0)
                if rt_ts > lt_ts and rt.get("description"):
                    task_map[tid] = dict(rt)

    merged = [t for t in task_map.values() if str(t.get("id", "")).strip() not in del_set]
    merged.sort(key=lambda x: (float(x.get("due_timestamp") or 0) <= 0, float(x.get("due_timestamp") or 0)))
    return merged


def merge_custom_exams(
    local_exams: List[dict],
    remote_exams: List[dict],
    deleted_ids: Optional[set] = None,
) -> List[dict]:
    """Führt Klausuren/Tests anhand ihrer IDs zusammen."""
    del_set = {str(x).strip() for x in deleted_ids} if deleted_ids else set()
    exam_map: Dict[str, dict] = {}
    for ex in local_exams:
        eid = str(ex.get("id", "")).strip()
        if eid and eid not in del_set:
            exam_map[eid] = dict(ex)

    for rex in remote_exams:
        eid = str(rex.get("id", "")).strip()
        if not eid or eid in del_set:
            continue
        if eid not in exam_map:
            exam_map[eid] = dict(rex)
        else:
            if len(str(rex.get("custom_topics", ""))) > len(str(exam_map[eid].get("custom_topics", ""))):
                exam_map[eid] = dict(rex)

    return [e for e in exam_map.values() if str(e.get("id", "")).strip() not in del_set]


def merge_exam_notes(local_notes: dict, remote_notes: dict) -> dict:
    """Führt Prüfungsnotizen zusammen. Bevorzugt nicht-leere Notizen."""
    merged = dict(local_notes)
    for k, v in remote_notes.items():
        if k not in merged or not merged[k]:
            merged[k] = v
        elif v and len(str(v)) > len(str(merged[k])):
            merged[k] = v
    return merged


def merge_deleted_tasks(local_del: List[str], remote_del: List[str]) -> List[str]:
    """Set-Union der gelöschten Aufgaben-IDs, damit Löschungen geräteübergreifend wirksam bleiben."""
    return sorted(list(set(local_del) | set(remote_del)))


def merge_config_files(local_cfg: dict, remote_cfg: dict) -> dict:
    """
    Führt anwendungsspezifische Konfigurationen zusammen (Themes, Stundenplan-Gruppe, Schul- und Schülerdaten).
    Remote-Werte aus der Git-Cloud haben Vorrang vor lokalen Default-Werten.
    """
    merged = dict(local_cfg)
    safe_keys = [
        "theme",
        "moodle_base_url",
        "untis_url",
        "untis_group",
        "untis_school",
        "student_name",
        "student_class",
        "teacher_name",
        "school_address",
        "school_district",
    ]
    for k in safe_keys:
        if k in remote_cfg and remote_cfg[k]:
            if k == "theme":
                merged["theme"] = str(remote_cfg["theme"]).strip().lower().replace("_", "-")
            else:
                val_str = str(remote_cfg[k]).strip()
                if val_str:
                    merged[k] = val_str

    # favorite_themes synchronisieren (Reihenfolge bewahren, Duplikate vermeiden)
    rem_favs = remote_cfg.get("favorite_themes")
    loc_favs = local_cfg.get("favorite_themes")
    if isinstance(rem_favs, list):
        if not isinstance(loc_favs, list) or not loc_favs:
            merged["favorite_themes"] = [str(t).strip().lower().replace("_", "-") for t in rem_favs if isinstance(t, str)]
        else:
            seen = set()
            combined = []
            for t in loc_favs + rem_favs:
                if isinstance(t, str):
                    c = t.strip().lower().replace("_", "-")
                    if c and c not in seen:
                        seen.add(c)
                        combined.append(c)
            merged["favorite_themes"] = combined

    # excuse_profile synchronisieren
    loc_profile = merged.get("excuse_profile")
    if not isinstance(loc_profile, dict):
        loc_profile = {}
    rem_profile = remote_cfg.get("excuse_profile")
    if isinstance(rem_profile, dict):
        for p_key, p_val in rem_profile.items():
            if p_val is not None and str(p_val).strip():
                loc_profile[p_key] = str(p_val).strip()

    # Synchronisiere Profil-Felder und Top-Level Felder konsistent (Remote hat Vorrang)
    for prof_field in ["student_name", "student_class", "teacher_name", "school_address", "school_district"]:
        rem_val = None
        if isinstance(rem_profile, dict) and rem_profile.get(prof_field):
            rem_val = str(rem_profile[prof_field]).strip()
        elif remote_cfg.get(prof_field):
            rem_val = str(remote_cfg[prof_field]).strip()

        if rem_val:
            loc_profile[prof_field] = rem_val
            merged[prof_field] = rem_val
        else:
            loc_val = loc_profile.get(prof_field) or merged.get(prof_field)
            if loc_val:
                loc_profile[prof_field] = str(loc_val).strip()
                merged[prof_field] = str(loc_val).strip()

    merged["excuse_profile"] = loc_profile
    return merged



# ---------------------------------------------------------
# Git-Synchronisations-Logik
# ---------------------------------------------------------

class GitSyncService:
    """Zentraler Dienst für die Git-Synchronisation."""

    @staticmethod
    def test_connection(repo_url: str, token: str) -> Tuple[bool, str]:
        """Prüft die Erreichbarkeit und Authentifizierung des Git-Repositories."""
        if not is_git_available():
            return (False, "Git is not installed on this system or not found in PATH.")

        auth_url = build_authenticated_url(repo_url, token)
        ok, stdout, stderr = _run_git_cmd(["ls-remote", "--heads", auth_url], timeout=15)
        if ok:
            return (True, "Connected to Git repository successfully!")
        
        # Fehlermeldung säubern
        err_clean = mask_git_url(stderr or stdout or "Unknown error")
        if "could not read Username" in err_clean or "terminal prompts disabled" in err_clean:
            return (False, "Authentication required! Please provide a Personal Access Token (PAT).")
        if "Authentication failed" in err_clean or "Invalid username or password" in err_clean:
            return (False, "Authentication failed! Please check your Personal Access Token (PAT).")
        if "Repository not found" in err_clean:
            return (False, "Repository not found. Please check repository URL and permissions ('repo' scope).")
        return (False, f"Git error: {err_clean}")


    @staticmethod
    def setup_repository(
        repo_url: str,
        token: str = "",
        branch: str = "main",
    ) -> Tuple[bool, str]:
        """
        Richtet das lokale Git-Repository ein (Klonen oder Initialisieren),
        synchronisiert den ersten Stand und speichert die Konfiguration.
        """
        with _sync_lock:
            if not is_git_available():
                return (False, "Git ist nicht installiert.")

            auth_url = build_authenticated_url(repo_url, token)
            branch = branch.strip() or "main"

            # 1. Verbindungstest
            ok, test_msg = GitSyncService.test_connection(repo_url, token)
            if not ok:
                return (False, test_msg)

            # 2. Lokalen Klon vorbereiten
            work_dir = GIT_SYNC_WORK_DIR
            os.makedirs(work_dir, exist_ok=True)

            needs_reclone = True
            has_remote_branches = True

            # Falls bereits ein gültiges Repo geklont war, prüfen ob es dieselbe Repo-URL ist
            if is_valid_git_repo(work_dir):
                ok_rem, cur_rem, _ = _run_git_cmd(["remote", "get-url", "origin"], cwd=work_dir)
                if ok_rem and cur_rem:
                    cur_clean = re.sub(r"https?://([^@]+@)?", "", cur_rem.strip()).lower().rstrip(".git")
                    new_clean = re.sub(r"https?://([^@]+@)?", "", repo_url.strip()).lower().rstrip(".git")
                    if cur_clean == new_clean:
                        needs_reclone = False
                        _run_git_cmd(["remote", "set-url", "origin", auth_url], cwd=work_dir)

            if needs_reclone:
                _safe_rmtree(work_dir)
                os.makedirs(work_dir, exist_ok=True)

                # Prüfen, ob Remote leer ist
                ok_ls, out_ls, _ = _run_git_cmd(["ls-remote", "--heads", auth_url], timeout=15)
                has_remote_branches = bool(out_ls.strip())

                if has_remote_branches:
                    # Klonen in temporären Ordner und verschieben
                    parent_dir = os.path.dirname(work_dir)
                    tmp_clone_dir = os.path.join(parent_dir, "git_sync_tmp")
                    _safe_rmtree(tmp_clone_dir)

                    ok_clone, _, err_clone = _run_git_cmd(
                        ["clone", "--branch", branch, auth_url, tmp_clone_dir],
                        timeout=45,
                    )
                    if not ok_clone:
                        # Fallback ohne expliziten Branch
                        ok_clone, _, err_clone = _run_git_cmd(
                            ["clone", auth_url, tmp_clone_dir],
                            timeout=45,
                        )

                    if ok_clone and os.path.exists(tmp_clone_dir):
                        _safe_rmtree(work_dir)
                        try:
                            os.rename(tmp_clone_dir, work_dir)
                        except OSError:
                            shutil.copytree(tmp_clone_dir, work_dir, dirs_exist_ok=True)
                            _safe_rmtree(tmp_clone_dir)
                    else:
                        return (False, f"Cloning failed: {mask_git_url(err_clone)}")
                else:
                    # Remote ist komplett leer: Initiales git init, branch, remote
                    _run_git_cmd(["init"], cwd=work_dir)
                    _run_git_cmd(["checkout", "-B", branch], cwd=work_dir)
                    _run_git_cmd(["remote", "add", "origin", auth_url], cwd=work_dir)

            # Git Identität für automatische Commits setzen
            _run_git_cmd(["config", "user.name", "Tasks"], cwd=work_dir)
            _run_git_cmd(["config", "user.email", "tasks@local"], cwd=work_dir)
            # Verhindert LF/CRLF Warnungen
            _run_git_cmd(["config", "core.autocrlf", "false"], cwd=work_dir)

            # 3. Konfiguration speichern
            now_iso = datetime.now().isoformat()
            save_git_sync_config(
                repo_url=repo_url,
                token=token,
                branch=branch,
                enabled=True,
                last_sync=now_iso,
            )

            # 4. Initialer Sync: Remote-Stand herunterladen & mergen (nur wenn Remote nicht leer), danach initialen Stand hochladen
            if has_remote_branches:
                pull_ok, pull_msg, _ = GitSyncService.pull_and_sync()
                if not pull_ok and "not configured" not in pull_msg and "nicht eingerichtet" not in pull_msg:
                    logger.warning(f"Initialer Pull-Hinweis: {pull_msg}")

            push_ok, push_msg = GitSyncService.push_changes("Initial setup: Synchronize repository")
            if not push_ok:
                logger.warning(f"Initialer Push-Hinweis: {push_msg}")

            return (True, "Git repository successfully connected and synchronized!")

    @staticmethod
    def disconnect() -> Tuple[bool, str]:
        """Trennt die Git-Synchronisation und löscht die Anmeldedaten."""
        with _sync_lock:
            remove_git_sync_config()
            # Arbeitsverzeichnis optional bereinigen
            if os.path.exists(GIT_SYNC_WORK_DIR):
                try:
                    _safe_rmtree(GIT_SYNC_WORK_DIR)
                except Exception:
                    pass
            return (True, "Git-Synchronisation wurde getrennt.")

    @staticmethod
    def pull_and_sync() -> Tuple[bool, str, bool]:
        """
        Führt einen reinen Download/Pull vom Git-Repository durch und verschmilzt
        die entfernten Daten mit den lokalen Live-Daten (Smart Merge).
        Wird beim Programmstart und beim Klick auf Synchronisieren aufgerufen.
        Pusht NIEMALS zu Git!
        """
        with _sync_lock:
            cfg = get_git_sync_config()
            if not cfg.get("enabled") or not cfg.get("repo_url"):
                return (False, "Git-Sync ist nicht eingerichtet.", False)

            work_dir = GIT_SYNC_WORK_DIR
            if not is_valid_git_repo(work_dir):
                # Repo existiert noch nicht lokal oder ist beschädigt -> neu aufsetzen
                ok, msg = GitSyncService.setup_repository(
                    repo_url=cfg["repo_url"],
                    token=cfg.get("token", ""),
                    branch=cfg.get("branch", "main"),
                )
                return (ok, msg, True)

            branch = cfg.get("branch", "main")
            auth_url = build_authenticated_url(cfg["repo_url"], cfg.get("token", ""))
            _run_git_cmd(["remote", "set-url", "origin", auth_url], cwd=work_dir)

            # 1. Fetch vom Remote-Branch
            ok_fetch, _, err_fetch = _run_git_cmd(["fetch", "origin", branch], cwd=work_dir, timeout=20)
            if not ok_fetch:
                err_clean = mask_git_url(err_fetch)
                logger.warning(f"Git fetch failed: {err_clean}")
                return (False, f"Git fetch failed: {err_clean}", False)

            # 2. Prüfen, ob Aufgaben/Exams im Remote-Repo seit dem letzten Sync gelöscht wurden
            remote_deleted_task_ids = set()
            remote_deleted_exam_ids = set()
            ok_head, head_hash, _ = _run_git_cmd(["rev-parse", "HEAD"], cwd=work_dir)
            ok_rem, rem_hash, _ = _run_git_cmd(["rev-parse", f"origin/{branch}"], cwd=work_dir)
            if ok_head and ok_rem and head_hash.strip() != rem_hash.strip():
                ok_old_t, old_t_raw, _ = _run_git_cmd(["show", "HEAD:data/custom_tasks.json"], cwd=work_dir)
                ok_new_t, new_t_raw, _ = _run_git_cmd(["show", f"origin/{branch}:data/custom_tasks.json"], cwd=work_dir)
                if ok_old_t and ok_new_t:
                    try:
                        old_t_list = json.loads(old_t_raw)
                        new_t_list = json.loads(new_t_raw)
                        old_ids = {str(t["id"]).strip() for t in old_t_list if isinstance(t, dict) and t.get("id")}
                        new_ids = {str(t["id"]).strip() for t in new_t_list if isinstance(t, dict) and t.get("id")}
                        remote_deleted_task_ids = old_ids - new_ids
                    except Exception:
                        pass

                ok_old_e, old_e_raw, _ = _run_git_cmd(["show", "HEAD:data/custom_exams.json"], cwd=work_dir)
                ok_new_e, new_e_raw, _ = _run_git_cmd(["show", f"origin/{branch}:data/custom_exams.json"], cwd=work_dir)
                if ok_old_e and ok_new_e:
                    try:
                        old_e_list = json.loads(old_e_raw)
                        new_e_list = json.loads(new_e_raw)
                        old_e_ids = {str(e["id"]).strip() for e in old_e_list if isinstance(e, dict) and e.get("id")}
                        new_e_ids = {str(e["id"]).strip() for e in new_e_list if isinstance(e, dict) and e.get("id")}
                        remote_deleted_exam_ids = old_e_ids - new_e_ids
                    except Exception:
                        pass

            # 3. Lokales Zwischenspeicher-Repo auf den exakten Stand von origin/branch setzen
            _run_git_cmd(["merge", "--abort"], cwd=work_dir)
            _run_git_cmd(["reset", "--hard", f"origin/{branch}"], cwd=work_dir)
            _run_git_cmd(["clean", "-fd"], cwd=work_dir)

            repo_data_dir = os.path.join(work_dir, "data")
            repo_config_file = os.path.join(work_dir, "config.json")
            os.makedirs(repo_data_dir, exist_ok=True)
            cleanup_legacy_sync_repo_files(work_dir)

            has_updates = False

            # 4. Getrennt einlesen: deleted_manual_tasks.json und hidden_tasks.json
            # (Inklusive automatischer Migration aus Legacy deleted_tasks.json)
            legacy_repo_del = os.path.join(repo_data_dir, "deleted_tasks.json")
            legacy_items = []
            if os.path.exists(legacy_repo_del):
                try:
                    with open(legacy_repo_del, "r", encoding="utf-8") as f:
                        d = json.load(f)
                        if isinstance(d, list):
                            legacy_items.extend(str(x).strip() for x in d if str(x).strip())
                    os.remove(legacy_repo_del)
                except Exception:
                    pass

            # 4a. deleted_manual_tasks.json
            local_manual_del = []
            for dp in [DELETED_MANUAL_TASKS_FILE, APP_DELETED_MANUAL_TASKS_FILE]:
                if dp and os.path.exists(dp):
                    try:
                        with open(dp, "r", encoding="utf-8") as f:
                            d = json.load(f)
                            if isinstance(d, list):
                                local_manual_del.extend(d)
                    except Exception:
                        pass
            repo_manual_del = []
            repo_man_del_path = os.path.join(repo_data_dir, "deleted_manual_tasks.json")
            if os.path.exists(repo_man_del_path):
                try:
                    with open(repo_man_del_path, "r", encoding="utf-8") as f:
                        rd = json.load(f)
                        if isinstance(rd, list):
                            repo_manual_del.extend(rd)
                except Exception:
                    pass

            legacy_manual = [x for x in legacy_items if x.startswith("manual_")]
            merged_manual_del = merge_deleted_tasks(local_manual_del, repo_manual_del + legacy_manual)
            if remote_deleted_task_ids:
                merged_manual_del = sorted(list(set(merged_manual_del) | remote_deleted_task_ids))

            deleted_manual_set = set(merged_manual_del)
            if set(merged_manual_del) != set(local_manual_del):
                has_updates = True
                for dp in [DELETED_MANUAL_TASKS_FILE, APP_DELETED_MANUAL_TASKS_FILE]:
                    if dp:
                        try:
                            os.makedirs(os.path.dirname(dp), exist_ok=True)
                            with open(dp, "w", encoding="utf-8") as f:
                                json.dump(merged_manual_del, f, indent=2)
                        except Exception:
                            pass

            # 4b. hidden_tasks.json (Plattform-Aufgaben aus Moodle & Teams)
            local_hidden = []
            for hp in [HIDDEN_TASKS_FILE, APP_HIDDEN_TASKS_FILE]:
                if hp and os.path.exists(hp):
                    try:
                        with open(hp, "r", encoding="utf-8") as f:
                            d = json.load(f)
                            if isinstance(d, list):
                                local_hidden.extend(d)
                    except Exception:
                        pass
            repo_hidden = []
            repo_hid_path = os.path.join(repo_data_dir, "hidden_tasks.json")
            if os.path.exists(repo_hid_path):
                try:
                    with open(repo_hid_path, "r", encoding="utf-8") as f:
                        rd = json.load(f)
                        if isinstance(rd, list):
                            repo_hidden.extend(rd)
                except Exception:
                    pass

            legacy_hidden = [x for x in legacy_items if not x.startswith("manual_")]
            merged_hidden = merge_deleted_tasks(local_hidden, repo_hidden + legacy_hidden)
            if set(merged_hidden) != set(local_hidden):
                has_updates = True
                for hp in [HIDDEN_TASKS_FILE, APP_HIDDEN_TASKS_FILE]:
                    if hp:
                        try:
                            os.makedirs(os.path.dirname(hp), exist_ok=True)
                            with open(hp, "w", encoding="utf-8") as f:
                                json.dump(merged_hidden, f, indent=2)
                        except Exception:
                            pass

            # 5. Dateien einlesen und Smart Merge mit den lokalen Live-Dateien durchführen
            files_to_sync = [
                ("custom_tasks.json", [CUSTOM_TASKS_FILE, APP_CUSTOM_TASKS_FILE], lambda l, r: merge_custom_tasks(l, r, deleted_ids=deleted_manual_set), []),
                ("custom_exams.json", [CUSTOM_EXAMS_FILE, APP_CUSTOM_EXAMS_FILE], lambda l, r: merge_custom_exams(l, r, deleted_ids=remote_deleted_exam_ids), []),
                ("exam_notes.json", [APP_UNTIS_EXAM_NOTES_FILE, UNTIS_EXAM_NOTES_FILE], merge_exam_notes, {}),
            ]

            for fname, live_paths, merge_func, default_val in files_to_sync:
                repo_file_path = os.path.join(repo_data_dir, fname)

                # Lokale Live-Daten laden
                live_data = default_val
                for lp in live_paths:
                    if lp and os.path.exists(lp):
                        try:
                            with open(lp, "r", encoding="utf-8") as f:
                                loaded = json.load(f)
                                if loaded:
                                    live_data = loaded
                                    break
                        except Exception:
                            pass

                # Remote-Daten aus dem Repo-Ordner laden
                repo_data = default_val
                if os.path.exists(repo_file_path):
                    try:
                        with open(repo_file_path, "r", encoding="utf-8") as f:
                            repo_data = json.load(f)
                    except Exception:
                        repo_data = default_val

                # Smart Merge
                merged_data = merge_func(live_data, repo_data)

                # Falls merged_data Neuerungen gegenüber live_data enthält: lokale Dateien updaten!
                if merged_data != live_data:
                    has_updates = True
                    for lp in live_paths:
                        if lp:
                            try:
                                os.makedirs(os.path.dirname(lp), exist_ok=True)
                                with open(lp, "w", encoding="utf-8") as f:
                                    json.dump(merged_data, f, indent=2, ensure_ascii=False)
                            except Exception:
                                pass

            # Config.json verschmelzen
            live_cfg_data = {}
            for p in [APP_CONFIG_FILE, CONFIG_FILE]:
                if os.path.exists(p):
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            c = json.load(f)
                            if isinstance(c, dict):
                                live_cfg_data.update(c)
                    except Exception:
                        pass

            repo_cfg_data = {}
            if os.path.exists(repo_config_file):
                try:
                    with open(repo_config_file, "r", encoding="utf-8") as f:
                        repo_cfg_data = json.load(f)
                except Exception:
                    pass

            merged_cfg = merge_config_files(live_cfg_data, repo_cfg_data)
            if merged_cfg != live_cfg_data:
                has_updates = True
                for cp in [CONFIG_FILE, APP_CONFIG_FILE]:
                    try:
                        os.makedirs(os.path.dirname(cp), exist_ok=True)
                        with open(cp, "w", encoding="utf-8") as f:
                            json.dump(merged_cfg, f, indent=2, ensure_ascii=False)
                    except Exception:
                        pass

            # Veraltete theme.json im Repo bereinigen, falls vorhanden
            for old_t in [os.path.join(work_dir, "theme.json"), os.path.join(repo_data_dir, "theme.json")]:
                if os.path.exists(old_t):
                    try:
                        os.remove(old_t)
                    except Exception:
                        pass

            # Letzten Sync-Zeitpunkt aktualisieren
            save_git_sync_config(
                repo_url=cfg["repo_url"],
                token=cfg.get("token", ""),
                branch=branch,
                enabled=True,
                last_sync=datetime.now().isoformat(),
            )

            # WICHTIG: Hier wird bewusst NICHT gepusht oder gecommittet!
            return (True, "Synchronization successfully completed.", has_updates)

    @staticmethod
    def push_changes(commit_message: str = "Update tasks & exams") -> Tuple[bool, str]:
        """
        Kopiert aktuelle lokale Live-Daten ins Repo, committet und pusht zu Git.
        Wird NUR aufgerufen, wenn der Benutzer aktiv eine Änderung vornimmt!
        """
        with _sync_lock:
            cfg = get_git_sync_config()
            if not cfg.get("enabled") or not cfg.get("repo_url"):
                return (False, "Git-Sync is not enabled.")

            work_dir = GIT_SYNC_WORK_DIR
            # Wenn Repo fehlt oder beschädigt ist: automatisch neu initialisieren
            if not is_valid_git_repo(work_dir):
                logger.info("Git-Repository nicht vorhanden oder beschädigt. Richte automatisch neu ein...")
                ok_setup, msg_setup = GitSyncService.setup_repository(
                    repo_url=cfg["repo_url"],
                    token=cfg.get("token", ""),
                    branch=cfg.get("branch", "main"),
                )
                if not ok_setup:
                    return (False, f"Repository initialization failed: {msg_setup}")

            repo_data_dir = os.path.join(work_dir, "data")
            os.makedirs(repo_data_dir, exist_ok=True)
            cleanup_legacy_sync_repo_files(work_dir)

            # README sicherstellen
            readme_path = os.path.join(work_dir, "README.md")
            if not os.path.exists(readme_path):
                try:
                    with open(readme_path, "w", encoding="utf-8") as f:
                        f.write(
                            "# Tasks - Private Cloud Sync\n\n"
                            "Automatisches Backup- und Synchronisations-Repository für **Tasks**.\n\n"
                            "Beinhaltet:\n"
                            "- `config.json`: Benutzereinstellungen, Farb-Theme & Stundenplan-Konfiguration\n"
                            "- `data/custom_tasks.json`: Manuell erstellte Aufgaben\n"
                            "- `data/custom_exams.json`: Manuell erstellte Prüfungen & Tests\n"
                            "- `data/exam_notes.json`: Lernstoff & Prüfungsnotizen\n"
                            "- `data/deleted_tasks.json`: Gelöschte Aufgaben\n"
                        )
                except Exception:
                    pass

            # Veraltete theme.json im Repo entfernen
            for old_t in [os.path.join(work_dir, "theme.json"), os.path.join(repo_data_dir, "theme.json")]:
                if os.path.exists(old_t):
                    try:
                        os.remove(old_t)
                    except Exception:
                        pass

            # Live-Dateien ins Repo kopieren
            # 1. Config aus beiden Speicherorten konsolidieren
            full_live_cfg = {}
            for cp in [APP_CONFIG_FILE, CONFIG_FILE]:
                if os.path.exists(cp):
                    try:
                        with open(cp, "r", encoding="utf-8") as f:
                            d = json.load(f)
                            if isinstance(d, dict):
                                full_live_cfg.update(d)
                    except Exception:
                        pass
            
            repo_cfg_path = os.path.join(work_dir, "config.json")
            if full_live_cfg:
                try:
                    with open(repo_cfg_path, "w", encoding="utf-8") as f:
                        json.dump(full_live_cfg, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

            # 2. Aufgaben, Tests, Notizen und Papierkorb ins Repo kopieren
            # Veraltete deleted_tasks.json im Repo entfernen
            old_repo_del = os.path.join(repo_data_dir, "deleted_tasks.json")
            if os.path.exists(old_repo_del):
                try:
                    os.remove(old_repo_del)
                except Exception:
                    pass

            file_map = [
                ([CUSTOM_TASKS_FILE, APP_CUSTOM_TASKS_FILE], os.path.join(repo_data_dir, "custom_tasks.json")),
                ([CUSTOM_EXAMS_FILE, APP_CUSTOM_EXAMS_FILE], os.path.join(repo_data_dir, "custom_exams.json")),
                ([APP_UNTIS_EXAM_NOTES_FILE, UNTIS_EXAM_NOTES_FILE], os.path.join(repo_data_dir, "exam_notes.json")),
                ([DELETED_MANUAL_TASKS_FILE, APP_DELETED_MANUAL_TASKS_FILE], os.path.join(repo_data_dir, "deleted_manual_tasks.json")),
                ([HIDDEN_TASKS_FILE, APP_HIDDEN_TASKS_FILE], os.path.join(repo_data_dir, "hidden_tasks.json")),
            ]

            for src_candidates, dst in file_map:
                copied = False
                for src in src_candidates:
                    if src and os.path.exists(src):
                        try:
                            shutil.copy2(src, dst)
                            copied = True
                            break
                        except Exception:
                            pass
                if not copied and not os.path.exists(dst):
                    try:
                        with open(dst, "w", encoding="utf-8") as f:
                            json.dump({} if "notes" in dst else [], f)
                    except Exception:
                        pass

            _run_git_cmd(["add", "."], cwd=work_dir)
            ok_status, status_out, err_status = _run_git_cmd(["status", "--porcelain"], cwd=work_dir)
            if not ok_status:
                return (False, f"Git status failed: {mask_git_url(err_status)}")

            branch = cfg.get("branch", "main")
            auth_url = build_authenticated_url(cfg["repo_url"], cfg.get("token", ""))
            _run_git_cmd(["remote", "set-url", "origin", auth_url], cwd=work_dir)
            _run_git_cmd(["config", "user.name", "Tasks"], cwd=work_dir)
            _run_git_cmd(["config", "user.email", "tasks@local"], cwd=work_dir)

            if status_out.strip():
                ok_com, _, err_com = _run_git_cmd(["commit", "-m", commit_message], cwd=work_dir)
                if not ok_com:
                    return (False, f"Git commit failed: {mask_git_url(err_com)}")

            # Prüfen, ob noch unvollendete Commits zum Pushen vorhanden sind
            ok_ahead, ahead_count, _ = _run_git_cmd(["rev-list", "--count", f"origin/{branch}..HEAD"], cwd=work_dir)
            if ok_ahead and ahead_count.strip() == "0" and not status_out.strip():
                return (True, "No changes to commit.")

            ok_push, _, err_push = _run_git_cmd(["push", "origin", branch], cwd=work_dir, timeout=25)
            if not ok_push:
                # Falls Push abgewiesen wurde (Remote hat neuere Commits):
                # Remote-Stand herunterladen & mergen, danach erneut ins Repo kopieren & pushen
                logger.info("Push initially rejected. Fetching remote changes and retrying...")
                GitSyncService.pull_and_sync()
                if full_live_cfg:
                    with open(repo_cfg_path, "w", encoding="utf-8") as f:
                        json.dump(full_live_cfg, f, indent=2, ensure_ascii=False)
                for src_candidates, dst in file_map:
                    for src in src_candidates:
                        if src and os.path.exists(src):
                            shutil.copy2(src, dst)
                            break
                _run_git_cmd(["add", "."], cwd=work_dir)
                _run_git_cmd(["commit", "-m", commit_message], cwd=work_dir)
                ok_push, _, err_push = _run_git_cmd(["push", "origin", branch], cwd=work_dir, timeout=25)
                if not ok_push:
                    return (False, f"Push failed: {mask_git_url(err_push)}")

            save_git_sync_config(
                repo_url=cfg["repo_url"],
                token=cfg.get("token", ""),
                branch=branch,
                enabled=True,
                last_sync=datetime.now().isoformat(),
            )
            return (True, "Changes successfully pushed to Git.")

    @staticmethod
    def async_pull(
        on_complete: Optional[Callable[[bool, str, bool], None]] = None,
    ) -> threading.Thread:
        """Startet die Synchronisation asynchron in einem Hintergrund-Thread."""
        def _target():
            try:
                ok, msg, has_updates = GitSyncService.pull_and_sync()
                if on_complete:
                    on_complete(ok, msg, has_updates)
            except Exception as e:
                if on_complete:
                    on_complete(False, f"Unexpected error during Git sync: {e}", False)

        t = threading.Thread(target=_target, daemon=True, name="GitAsyncPull")
        t.start()
        return t

    @staticmethod
    def async_push(
        commit_message: str = "Update tasks & exams",
        on_complete: Optional[Callable[[bool, str], None]] = None,
    ) -> threading.Thread:
        """Startet den Push asynchron in einem Hintergrund-Thread."""
        def _target():
            try:
                ok, msg = GitSyncService.push_changes(commit_message)
                if on_complete:
                    on_complete(ok, msg)
            except Exception as e:
                if on_complete:
                    on_complete(False, f"Unexpected error during Git push: {e}")

        t = threading.Thread(target=_target, daemon=True, name="GitAsyncPush")
        t.start()
        return t
