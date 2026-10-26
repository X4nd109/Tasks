"""
config.py - Konfiguration und Pfade für Tasks.
"""

import contextlib
import json
import os
import re
import sys
from pathlib import Path
import threading
from typing import Optional, List

# Basis-Verzeichnisse:
CORE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(CORE_DIR)
WORKSPACE_DIR = os.path.dirname(SRC_DIR)
USERPROFILE = os.environ.get("USERPROFILE") or os.path.expanduser("~")

# Anwendungs-Version & GitHub Repository
APP_VERSION = "2.1.1"
GITHUB_REPO = "X4nd109/Tasks"


def get_app_version(prefix: bool = True) -> str:
    """Gibt die aktuelle Anwendungsversion formatiert zurück (z. B. 'v1.0.2' oder '1.0.2')."""
    return f"v{APP_VERSION}" if prefix else APP_VERSION

# Pfade im PYTHONPATH registrieren für verlässliche modulübergreifende Imports
for _p in [WORKSPACE_DIR, SRC_DIR, CORE_DIR, os.path.join(SRC_DIR, "services"), os.path.join(SRC_DIR, "ui")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

DATA_DIR = os.path.join(WORKSPACE_DIR, "data")
ASSETS_DIR = os.path.join(WORKSPACE_DIR, "assets")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(FONTS_DIR, exist_ok=True)

# Automatische Migration von alten Root-Dateien nach data/
for _legacy_fname in ["custom_tasks.json", "custom_exams.json", "deleted_tasks.json", "exam_notes.json"]:
    _old_p = os.path.join(WORKSPACE_DIR, _legacy_fname)
    _new_p = os.path.join(DATA_DIR, _legacy_fname)
    if os.path.exists(_old_p) and not os.path.exists(_new_p):
        try:
            import shutil
            shutil.copy2(_old_p, _new_p)
        except Exception:
            pass


def _get_writable_cache_dir() -> str:
    """
    Ermittelt ein beschreibbares Cache-Verzeichnis.
    Bevorzugt den Ordner neben den Programm-Dateien (Installations-Ordner).
    Falls dieser nicht beschreibbar ist (z.B. C:\\Program Files), wird
    %LOCALAPPDATA%\\Tasks\\cache als Fallback verwendet.
    """
    local_cache = os.path.join(WORKSPACE_DIR, "cache")
    try:
        os.makedirs(local_cache, exist_ok=True)
        test_file = os.path.join(local_cache, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return local_cache
    except (PermissionError, OSError):
        appdata = os.environ.get("LOCALAPPDATA", USERPROFILE)
        fallback = os.path.join(appdata, "Tasks", "cache")
        os.makedirs(fallback, exist_ok=True)
        return fallback


# Lokales Cache- und Datenverzeichnis (automatisch beschreibbar)
CONFIG_DIR = _get_writable_cache_dir()

# Konfigurationsdatei für Benutzer-Einstellungen & Themes
CONFIG_FILE = os.path.join(WORKSPACE_DIR, "config.json")
# Automatische Migration von bestehenden aufgaben_detector_*.json nach tasks_*.json (Backup bleibt erhalten)
for _legacy_cfg_name, _new_cfg_name in [
    ("aufgaben_detector_config.json", "tasks_config.json"),
    ("aufgaben_detector_cache.json", "tasks_cache.json"),
    ("aufgaben_detector_deleted_tasks.json", "tasks_deleted_tasks.json"),
    ("aufgaben_detector_deleted_manual_tasks.json", "tasks_deleted_manual_tasks.json"),
    ("aufgaben_detector_hidden_tasks.json", "tasks_hidden_tasks.json"),
    ("aufgaben_detector_custom_tasks.json", "tasks_custom_tasks.json"),
    ("aufgaben_detector_custom_exams.json", "tasks_custom_exams.json"),
    ("aufgaben_detector_schoolbooks.json", "tasks_schoolbooks.json"),
    ("aufgaben_detector_directories.json", "tasks_directories.json"),
]:
    _legacy_p = os.path.join(CONFIG_DIR, _legacy_cfg_name)
    _migrated_p = os.path.join(CONFIG_DIR, _new_cfg_name)
    if os.path.exists(_legacy_p) and not os.path.exists(_migrated_p):
        try:
            import shutil
            shutil.copy2(_legacy_p, _migrated_p)
        except Exception:
            pass

APP_CONFIG_FILE = os.path.join(CONFIG_DIR, "tasks_config.json")


def _load_moodle_base_url() -> str:
    for p in [CONFIG_FILE, APP_CONFIG_FILE]:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "moodle_base_url" in data and data["moodle_base_url"]:
                        return data["moodle_base_url"].rstrip("/")
            except Exception:
                pass
    return os.environ.get("MOODLE_BASE_URL", "https://moodle.spengergasse.at")


def save_moodle_base_url(url: str) -> str:
    """Speichert eine geänderte Moodle-Base-URL persistent in die Konfigurationsdateien."""
    global MOODLE_BASE_URL
    clean_url = url.strip().rstrip("/")
    if not clean_url:
        return MOODLE_BASE_URL
    if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
        clean_url = "https://" + clean_url
    MOODLE_BASE_URL = clean_url
    for p in [CONFIG_FILE, APP_CONFIG_FILE]:
        data = {}
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data["moodle_base_url"] = clean_url
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    return clean_url


def _load_untis_url() -> str:
    for p in [CONFIG_FILE, APP_CONFIG_FILE]:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "untis_url" in data and data["untis_url"]:
                        return data["untis_url"].rstrip("/")
            except Exception:
                pass
    return os.environ.get("UNTIS_URL", "https://spengergasse.webuntis.com/WebUntis/?school=spengergasse")


def _load_untis_group() -> str:
    for p in [CONFIG_FILE, APP_CONFIG_FILE]:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "untis_group" in data and data["untis_group"]:
                        val = str(data["untis_group"]).strip().upper()
                        return "X" if "X" in val else ("Y" if "Y" in val else val)
            except Exception:
                pass
    val = os.environ.get("UNTIS_GROUP", "X").strip().upper()
    return "X" if "X" in val else ("Y" if "Y" in val else val)


def save_untis_group(group: str, auto_push: bool = True) -> None:
    for p in [CONFIG_FILE, APP_CONFIG_FILE]:
        data = {}
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data["untis_group"] = group
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    if auto_push:
        try:
            from git_sync_service import is_git_configured, GitSyncService
            if is_git_configured():
                GitSyncService.async_push(f"Update Untis group: {group}")
        except Exception:
            pass


def _load_untis_school() -> str:
    for p in [CONFIG_FILE, APP_CONFIG_FILE]:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "untis_school" in data and data["untis_school"]:
                        return str(data["untis_school"]).strip()
                    if "untis_url" in data and data["untis_url"]:
                        u = data["untis_url"]
                        from urllib.parse import urlparse, parse_qs
                        parsed = urlparse(u)
                        qs = parse_qs(parsed.query)
                        sch = qs.get("school", [""])[0].strip()
                        if not sch and ".webuntis.com" in parsed.netloc:
                            sub = parsed.netloc.split(".")[0].lower()
                            if sub not in ["arche", "urania", "triton", "www", "webuntis", "api"]:
                                sch = sub
                        if sch:
                            return sch
            except Exception:
                pass
    env_sch = os.environ.get("UNTIS_SCHOOL", "").strip()
    if env_sch:
        return env_sch
    return "spengergasse"


def save_untis_school(school: str, auto_push: bool = True) -> None:
    sch = school.strip()
    if not sch:
        return
    for p in [CONFIG_FILE, APP_CONFIG_FILE]:
        data = {}
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data["untis_school"] = sch
        data["untis_url"] = f"https://{sch}.webuntis.com/WebUntis/?school={sch}"
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    if auto_push:
        try:
            from git_sync_service import is_git_configured, GitSyncService
            if is_git_configured():
                GitSyncService.async_push(f"Update Untis school: {sch}")
        except Exception:
            pass


MOODLE_BASE_URL = _load_moodle_base_url()
TEAMS_BASE_URL = "https://teams.cloud.microsoft"
UNTIS_URL = _load_untis_url()
UNTIS_GROUP = _load_untis_group()
UNTIS_SCHOOL = _load_untis_school()

CACHE_FILE = os.path.join(CONFIG_DIR, "tasks_cache.json")
DELETED_TASKS_FILE = os.path.join(DATA_DIR, "deleted_tasks.json")
APP_DELETED_TASKS_FILE = os.path.join(CONFIG_DIR, "tasks_deleted_tasks.json")
DELETED_MANUAL_TASKS_FILE = os.path.join(DATA_DIR, "deleted_manual_tasks.json")
APP_DELETED_MANUAL_TASKS_FILE = os.path.join(CONFIG_DIR, "tasks_deleted_manual_tasks.json")
HIDDEN_TASKS_FILE = os.path.join(DATA_DIR, "hidden_tasks.json")
APP_HIDDEN_TASKS_FILE = os.path.join(CONFIG_DIR, "tasks_hidden_tasks.json")
CUSTOM_TASKS_FILE = os.path.join(DATA_DIR, "custom_tasks.json")
APP_CUSTOM_TASKS_FILE = os.path.join(CONFIG_DIR, "tasks_custom_tasks.json")
CUSTOM_EXAMS_FILE = os.path.join(DATA_DIR, "custom_exams.json")
APP_CUSTOM_EXAMS_FILE = os.path.join(CONFIG_DIR, "tasks_custom_exams.json")
SCHOOLBOOKS_FILE = os.path.join(DATA_DIR, "schoolbooks.json")
APP_SCHOOLBOOKS_FILE = os.path.join(CONFIG_DIR, "tasks_schoolbooks.json")
DIRECTORIES_FILE = os.path.join(DATA_DIR, "directories.json")
APP_DIRECTORIES_FILE = os.path.join(CONFIG_DIR, "tasks_directories.json")
MOODLE_COOKIE_FILE = os.path.join(CONFIG_DIR, "moodle_session_cookies.json")
TEAMS_PROFILE_DIR = os.path.join(CONFIG_DIR, "teams_browser_profile")
os.makedirs(TEAMS_PROFILE_DIR, exist_ok=True)
UNTIS_PROFILE_DIR = os.path.join(CONFIG_DIR, "untis_browser_profile")
UNTIS_CACHE_FILE = os.path.join(CONFIG_DIR, "untis_absences_cache.json")
os.makedirs(UNTIS_PROFILE_DIR, exist_ok=True)

GIT_SYNC_CONFIG_FILE = os.path.join(CONFIG_DIR, "git_sync_config.json")
GIT_SYNC_WORK_DIR = os.path.join(CONFIG_DIR, "git_sync_repo")



# Cache-Optimierung & automatische Bereinigung
def _load_auto_clean_setting() -> bool:
    for p in [CONFIG_FILE, APP_CONFIG_FILE]:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "auto_clean_browser_cache" in data:
                        return bool(data["auto_clean_browser_cache"])
            except Exception:
                pass
    return True

AUTO_CLEAN_BROWSER_CACHE = _load_auto_clean_setting()

# Liste von rein temporären Unterordnern innerhalb eines Chromium-Profils,
# die gefahrlos geleert werden können, OHNE Logins / Cookies / Sessions zu verlieren.
SAFE_CACHE_SUBDIRS = [
    os.path.join("Default", "Cache"),
    os.path.join("Default", "Code Cache"),
    os.path.join("Default", "GPUCache"),
    os.path.join("Default", "DawnGraphiteCache"),
    os.path.join("Default", "DawnWebGPUCache"),
    "GrShaderCache",
    "ShaderCache",
    "Crashpad",
]

# Chromium-Startargumente zur Begrenzung des Festplatten-Caches auf 500 MB
CHROMIUM_CACHE_ARGS = [
    "--disk-cache-size=524288000",
    "--media-cache-size=524288000",
]

# Leistungsoptimierungen für Headless-Chromium (verhindert 100% CPU-Spitzen während Hintergrund-Syncs)
HEADLESS_CHROMIUM_ARGS = [
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--renderer-process-limit=2",
    "--no-first-run",
    "--no-default-browser-check",
    "--mute-audio",
    "--disable-background-networking",
]


_ACTIVE_BROWSER_CONTEXTS = set()
_CONTEXTS_LOCK = threading.Lock()
_IS_SHUTTING_DOWN = False


def set_shutting_down() -> None:
    """Signalisiert das globale Beenden der Anwendung für Hintergrundprozesse."""
    global _IS_SHUTTING_DOWN
    _IS_SHUTTING_DOWN = True


def is_shutting_down() -> bool:
    """Gibt zurück, ob die Anwendung aktuell beendet wird."""
    return _IS_SHUTTING_DOWN



def register_active_browser_context(ctx) -> None:
    """Registriert einen aktiven Browser-Kontext für sauberes Beenden."""
    if ctx is not None:
        with _CONTEXTS_LOCK:
            _ACTIVE_BROWSER_CONTEXTS.add(ctx)


def unregister_active_browser_context(ctx) -> None:
    """Entfernt einen geschlossenen Browser-Kontext aus der Registrierung."""
    if ctx is not None:
        with _CONTEXTS_LOCK:
            _ACTIVE_BROWSER_CONTEXTS.discard(ctx)


def close_all_active_browser_contexts() -> None:
    """Schließt alle noch geöffneten Browser-Kontexte sauber und verhindert EPIPE beim Exit."""
    set_shutting_down()
    with _CONTEXTS_LOCK:
        contexts = list(_ACTIVE_BROWSER_CONTEXTS)
        _ACTIVE_BROWSER_CONTEXTS.clear()
    for ctx in contexts:
        try:
            ctx.close()
        except Exception:
            pass


def launch_teams_browser_context(playwright_instance, user_data_dir: str = None, headless: bool = True, args: list = None, viewport=None):
    """
    Startet einen persistenten Browser-Kontext für Microsoft Teams.
    Nutzt unter Windows primär das isolierte Playwright-Chromium (channel=None),
    um automatisches Windows-SSO-Hijacking durch Edge (das zu falschen privaten MS-Konten führt)
    zu verhindern und Passkeys (WebAuthn / Windows Hello) sauber zu unterstützen.
    """
    target_dir = user_data_dir or TEAMS_PROFILE_DIR
    channels_to_try = [None, "chrome", "msedge"] if sys.platform == "win32" else [None]
    base_args = list(args or [])
    sso_disable_args = [
        "--disable-features=msSingleSignon,msSingleSignOnOSAccount,ImplicitSignIn",
        "--disable-sync",
    ]
    for ch in channels_to_try:
        try:
            extra_args = sso_disable_args if ch == "msedge" else []
            headless_opt = HEADLESS_CHROMIUM_ARGS if headless else []
            kwargs = {
                "user_data_dir": target_dir,
                "headless": headless,
                "args": base_args + extra_args + headless_opt,
            }
            if ch:
                kwargs["channel"] = ch
            if viewport is not None:
                kwargs["viewport"] = viewport
            else:
                kwargs["no_viewport"] = True
            ctx = playwright_instance.chromium.launch_persistent_context(**kwargs)
            if ctx:
                register_active_browser_context(ctx)
            return ctx
        except Exception:
            continue
    return None


@contextlib.contextmanager
def open_teams_context(playwright_instance, **kwargs):
    """Context Manager für sicheres Öffnen und garantiertes Schließen eines Teams-Browser-Kontexts."""
    ctx = launch_teams_browser_context(playwright_instance, **kwargs)
    try:
        yield ctx
    finally:
        if ctx:
            try:
                ctx.close()
            except Exception:
                pass
            unregister_active_browser_context(ctx)


def clean_browser_profile_caches(custom_profiles=None, threshold_mb: int = 600) -> int:
    """
    Bereinigt rein temporäre Browser-Cache-Verzeichnisse (Chromium HTTP-Cache,
    Code-Cache, GPU-Cache) für Teams und Untis, wenn das Profil größer als threshold_mb ist.
    WICHTIG: Cookies, LocalStorage, IndexedDB und Service-Worker-Daten bleiben unberührt,
    sodass der Login zu 100% erhalten bleibt und gecachte Web-Bundles schnelle Syncs ermöglichen.
    Gibt die Anzahl der freigegebenen Bytes zurück.
    """
    import shutil

    profiles_to_clean = custom_profiles if custom_profiles is not None else [TEAMS_PROFILE_DIR, UNTIS_PROFILE_DIR]
    total_freed_bytes = 0

    for profile_dir in profiles_to_clean:
        if not os.path.exists(profile_dir):
            continue

        # Prüfe Profilgröße, falls ein Schwellenwert gesetzt ist
        if threshold_mb > 0:
            profile_size = 0
            try:
                for root, _, files in os.walk(profile_dir):
                    for file in files:
                        try:
                            profile_size += os.path.getsize(os.path.join(root, file))
                        except Exception:
                            pass
            except Exception:
                pass

            # Liegt das Profil unter dem Schwellenwert (z.B. 200 MB), belassen wir den Cache,
            # damit Teams blitzschnell aus dem Cache lädt
            if profile_size < threshold_mb * 1024 * 1024:
                continue

        for sub_rel in SAFE_CACHE_SUBDIRS:
            target_path = os.path.join(profile_dir, sub_rel)
            if not os.path.exists(target_path):
                continue

            # Größe ermitteln
            dir_size = 0
            try:
                if os.path.isdir(target_path):
                    for root, _, files in os.walk(target_path):
                        for file in files:
                            try:
                                fp = os.path.join(root, file)
                                dir_size += os.path.getsize(fp)
                            except Exception:
                                pass
                elif os.path.isfile(target_path):
                    dir_size = os.path.getsize(target_path)
            except Exception:
                pass

            # Löschen (mit Fehlertoleranz für gesperrte / offene Dateien)
            try:
                if os.path.isdir(target_path):
                    shutil.rmtree(target_path, ignore_errors=True)
                elif os.path.isfile(target_path):
                    os.remove(target_path)
                total_freed_bytes += dir_size
            except Exception:
                pass

    return total_freed_bytes


# Vollständige Palette kuratierter und moderner Terminal-Themes (~20 Themes)
ALLOWED_THEMES = [
    # Beliebte Dark Themes
    "catppuccin-mocha",
    "dracula",
    "tokyo-night",
    "nord",
    "monokai",
    # Retro & Warm
    "gruvbox",
    # Rosé Pine Palette
    "rose-pine",
    "rose-pine-moon",
    "rose-pine-dawn",
    # Solarized Palette
    "solarized-dark",
    "solarized-light",
    # Catppuccin Varianten
    "catppuccin-macchiato",
    "catppuccin-frappe",
    "catppuccin-latte",
    # Atom One Palette
    "atom-one-dark",
    "atom-one-light",
    # Minimal & Earth Tones
    "flexoki",
    # True Black OLED with Flexoki Accents
    "oled",
    # Textual Standard Themes
    "textual-dark",
    "textual-light",
    # Klassische ANSI Terminal Themes
    "ansi-dark",
    "ansi-light",
]
DEFAULT_THEME = "catppuccin-mocha"

# Moodle Credentials Pfade (nur im lokalen Anwendungs-/Cache-Verzeichnis)
MOODLE_CREDS_POSSIBLE_PATHS = [
    os.path.join(CONFIG_DIR, "moodle_credentials.json"),
    os.path.join(WORKSPACE_DIR, "credentials.json"),
]

# WebUntis Credentials Pfade (nutzt Untis-Creds oder geteilte Schul-Zugangsdaten)
UNTIS_CREDS_POSSIBLE_PATHS = [
    os.path.join(CONFIG_DIR, "untis_credentials.json"),
    os.path.join(WORKSPACE_DIR, "untis_credentials.json"),
] + list(MOODLE_CREDS_POSSIBLE_PATHS)


# Windows 11 Downloads Ordner
DOWNLOADS_DIR = os.path.join(USERPROFILE, "Downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

TEAMS_STATUS_FILE = os.path.join(CONFIG_DIR, "teams_status.json")

# OneDrive Zielordner
ONEDRIVE_DIR = os.path.join(USERPROFILE, "OneDrive")
ONEDRIVE_TARGET_DIR = ONEDRIVE_DIR
for _candidate in ["Schule", "3. Klasse", "Klasse"]:
    _p = os.path.join(ONEDRIVE_DIR, _candidate)
    if os.path.exists(_p):
        ONEDRIVE_TARGET_DIR = _p
        break


# Bekannte Fächer Zuordnung (Matching von Kursnamen auf saubere Kürzel)
SUBJECT_MAPPINGS = {
    "SWP PM": ["swp pm", "swp_pm", "swp-pm", "projektmanagement", "bim_eij"],
    "SWP": ["swp", "softwareentwicklung"],
    "SESD": ["sesd", "security software development"],
    "SPL": ["spl", "systemprogrammierung"],
    "NW2": ["nw2", "chemie", "naturwissenschaften chemie"],
    "NW": ["nw", "physik", "naturwissenschaften physik", "nwes"],
    "BET": ["bet", "betriebstechnik"],
    "AMEC": ["amec", "angewandte mechatronik", "mechatronik", "mathe", "mathematik"],
    "SMEN": ["smen", "smeny"],
    "D": ["deutsch", "d "],
    "E": ["englisch", "english", "e "],
    "UFW": ["ufw", "unternehmensführung"],
    "POS": ["pos", "programmieren"],
    "MT": ["mt", "medientechnik"],
    "REL": ["religion", "rk", "evang"],
    "WST": ["werkstatt", "wst", "fertigungstechnik"],
}


def normalize_subject_name(raw_name: str) -> str:
    """Extrahiert ein sauberes Schulfach-Kürzel aus Kursnamen."""
    if not raw_name:
        return "Allgemein"

    raw_clean = raw_name.strip()
    raw_lower = raw_clean.lower()

    # 0. Unterscheidung zwischen SWP PM und reinem SWP
    if (
        "projektmanagement" in raw_lower
        or "swp pm" in raw_lower
        or "swp_pm" in raw_lower
        or "swp-pm" in raw_lower
        or re.search(r"(?:^|[_\s\-])(?:pm|bim_eij)(?:[_\s\-]|$)", raw_lower)
    ):
        return "SWP PM"
    if raw_lower.startswith("swp") or "softwareentwicklung" in raw_lower:
        return "SWP"

    # 1. Spezifische Fächer mit Sub-Index (z.B. "SPL_1", "SPL-1", "SPL 1", "SPL_3", "POS_2", "SPL_1_3AHWII")
    # Sub-Indices wie _1, _2, _3 sollen als Teil der Fach-Abkürzung erhalten bleiben
    m_sub = re.match(r"^([A-Za-z]+)[_\s\-]+(\d+)(?:[_\s\-]|$)", raw_clean)
    if m_sub:
        base_part = m_sub.group(1).upper()
        idx_part = m_sub.group(2)
        return f"{base_part}_{idx_part}"

    m_sub_direct = re.match(r"^([A-Za-z]+)(\d+)(?:[_\s\-]|$)", raw_clean)
    if m_sub_direct:
        base_part = m_sub_direct.group(1).upper()
        idx_part = m_sub_direct.group(2)
        if f"{base_part}{idx_part}" == "NW2":
            return "NW2"
        return f"{base_part}_{idx_part}"

    # 2. Bekannte Mappings prüfen
    for subject, keywords in SUBJECT_MAPPINGS.items():
        for kw in keywords:
            if kw == raw_lower or (len(kw) >= 3 and kw in raw_lower):
                return subject

    # 3. Prüfen auf führende Buchstabenkombinationen (z.B. "AMEC_3AHWII" -> "AMEC")
    m = re.match(r"^([A-Za-z0-9]+)[\s_-]", raw_clean)
    if m:
        sub = m.group(1).upper()
        if len(sub) <= 6:
            return sub

    return raw_clean[:15].strip()


# Lehrer-Kürzel Zuordnungen (können optional in config.json gepflegt werden)
def _load_teacher_mappings():
    subject_map = {}
    name_map = {}
    for p in [CONFIG_FILE, APP_CONFIG_FILE]:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    if isinstance(cfg, dict):
                        if "teacher_subject_mappings" in cfg and isinstance(cfg["teacher_subject_mappings"], dict):
                            subject_map.update(cfg["teacher_subject_mappings"])
                        if "teacher_name_mappings" in cfg and isinstance(cfg["teacher_name_mappings"], dict):
                            name_map.update(cfg["teacher_name_mappings"])
            except Exception:
                pass
    return subject_map, name_map


TEACHER_SUBJECT_MAPPINGS, TEACHER_NAME_MAPPINGS = _load_teacher_mappings()


def extract_teacher(course_full: str = "", subject: str = "", title: str = "", description: str = "") -> str:
    """Extrahiert das Lehrerkürzel aus dem Kursnamen, Fach oder Text."""
    combined = f"{course_full} {subject} {title} {description}".strip()
    comb_lower = combined.lower()

    # 1. Bekannte Nachnamen prüfen
    for name, code in TEACHER_NAME_MAPPINGS.items():
        if re.search(rf"\b{re.escape(name)}\b", comb_lower):
            return code

    # 2. Prüfen auf Kürzel am Ende des Kursnamens (z.B. "... - KRD", "... - BIM_EIJ", "... _WOF")
    m = re.search(r"[-_]\s*([A-Za-z]{3}(?:_[A-Za-z]{3})*)\s*$", (course_full or "").strip())
    if m:
        codes = m.group(1).upper().replace("_", "/")
        if not any(ign in codes for ign in ["262", "252", "242", "AHW", "HWII"]):
            return codes

    # 3. Standard-Lehrer für das jeweilige Schulfach (3AHWII)
    sub = (subject or normalize_subject_name(course_full)).upper()
    if sub in TEACHER_SUBJECT_MAPPINGS:
        return TEACHER_SUBJECT_MAPPINGS[sub]

    # 4. Fallback: Beliebiges 3-Buchstaben-Wort am Ende
    if course_full:
        m_end = re.search(r"\b([A-Z]{3})\b", course_full)
        if m_end and m_end.group(1) not in ["SJ2", "AHW", "HWI", "BET", "SWP", "UFW", "NW2", "SPL", "SES"]:
            return m_end.group(1)

    return "-"


def sanitize_filename(name: str) -> str:
    """Entfernt ungültige Dateisystemzeichen."""
    if not name:
        return "unbenannt"
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:100]


def resolve_subject_folder(subject: str) -> str:
    """Findet den passenden Fachordner in 3. Klasse, falls bereits vorhanden (z.B. 'SWP PM' für SWP, 'Chemie' für NW2)."""
    if os.path.exists(ONEDRIVE_TARGET_DIR):
        try:
            existing = [f for f in os.listdir(ONEDRIVE_TARGET_DIR) if os.path.isdir(os.path.join(ONEDRIVE_TARGET_DIR, f))]
            sub_lower = subject.lower().strip()
            # 1. Exakter Match
            for f in existing:
                if f.lower() == sub_lower:
                    return f
            # 2. Spezialfälle (z.B. NW2 -> Chemie, SWP PM, SWP)
            if subject.upper() == "SWP PM":
                for f in existing:
                    if "swp pm" in f.lower() or "swp_pm" in f.lower():
                        return f
            elif subject.upper() == "SWP":
                for f in existing:
                    if f.lower() == "swp":
                        return f
            if subject.upper() == "NW2":
                for f in existing:
                    if "chemie" in f.lower():
                        return f
            # 3. Teilstring-Match
            for f in existing:
                if sub_lower in f.lower() or f.lower() in sub_lower:
                    return f
        except Exception:
            pass
    return subject


def get_task_download_dir(subject: str, task_title: str) -> str:
    r"""
    Speichert direkt im Windows 11 Downloads-Ordner:
    C:\Users\<User>\Downloads\<Fach> - <Aufgabe>\
    """
    safe_subject = sanitize_filename(subject)
    safe_task = sanitize_filename(task_title)
    folder_name = f"{safe_subject} - {safe_task}" if safe_subject else safe_task
    target = os.path.join(DOWNLOADS_DIR, folder_name)
    os.makedirs(target, exist_ok=True)
    return target


def load_saved_theme() -> str:
    """Lädt das gespeicherte Theme aus der Konfigurationsdatei."""
    for path in [CONFIG_FILE, APP_CONFIG_FILE]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        theme = data.get("theme")
                        if isinstance(theme, str):
                            clean = theme.strip().lower().replace("_", "-")
                            if clean in ALLOWED_THEMES:
                                return clean
            except Exception:
                pass
    return DEFAULT_THEME


def save_saved_theme(theme_name: str) -> None:
    """Speichert das aktuell gewählte Theme dauerhaft atomar in config.json ab und pusht bei Änderung."""
    if not theme_name or not isinstance(theme_name, str):
        return
    clean_theme = theme_name.strip().lower().replace("_", "-")
    if clean_theme not in ALLOWED_THEMES:
        return

    # Veraltete theme.json-Dateien bereinigen, falls vorhanden
    for legacy_t in [os.path.join(DATA_DIR, "theme.json"), os.path.join(CONFIG_DIR, "theme.json")]:
        if os.path.exists(legacy_t):
            try:
                os.remove(legacy_t)
            except Exception:
                pass

    changed = False
    # In config.json ablegen
    for path in [CONFIG_FILE, APP_CONFIG_FILE]:
        try:
            data = {}
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            data = loaded
                except Exception:
                    data = {}
            if data.get("theme") != clean_theme:
                data["theme"] = clean_theme
                changed = True
                os.makedirs(os.path.dirname(path), exist_ok=True)
                tmp_path = f"{path}.tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, path)
        except Exception:
            pass

    # Automatisch zu Git pushen, wenn sich das Theme geändert hat
    if changed:
        try:
            try:
                from git_sync_service import is_git_configured, GitSyncService
            except ImportError:
                from services.git_sync_service import is_git_configured, GitSyncService
            if is_git_configured():
                GitSyncService.async_push(f"Update theme: {clean_theme}")
        except Exception:
            pass


def load_favorite_themes() -> List[str]:
    """Lädt die Liste favorisierter Theme-Namen aus config.json."""
    for path in [CONFIG_FILE, APP_CONFIG_FILE]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        favs = data.get("favorite_themes")
                        if isinstance(favs, list):
                            return [t for t in favs if isinstance(t, str) and t in ALLOWED_THEMES]
            except Exception:
                pass
    return []


def save_favorite_themes(favorites: List[str]) -> None:
    """Speichert favorisierte Themes persistent in config.json ab."""
    clean_favs = []
    seen = set()
    for t in favorites:
        if isinstance(t, str):
            c = t.strip().lower().replace("_", "-")
            if c in ALLOWED_THEMES and c not in seen:
                seen.add(c)
                clean_favs.append(c)

    changed = False
    for path in [CONFIG_FILE, APP_CONFIG_FILE]:
        try:
            data = {}
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            data = loaded
                except Exception:
                    data = {}
            if data.get("favorite_themes") != clean_favs:
                data["favorite_themes"] = clean_favs
                changed = True
                os.makedirs(os.path.dirname(path), exist_ok=True)
                tmp_path = f"{path}.tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, path)
        except Exception:
            pass

    if changed:
        try:
            try:
                from git_sync_service import is_git_configured, GitSyncService
            except ImportError:
                from services.git_sync_service import is_git_configured, GitSyncService
            if is_git_configured():
                GitSyncService.async_push("Update favorite themes")
        except Exception:
            pass


def toggle_favorite_theme(theme_name: str) -> bool:
    """Schaltet den Favoriten-Status eines Themes um. Gibt True zurück, wenn es nun favorisiert ist."""
    if not theme_name or not isinstance(theme_name, str):
        return False
    clean = theme_name.strip().lower().replace("_", "-")
    if clean not in ALLOWED_THEMES:
        return False
    favs = load_favorite_themes()
    if clean in favs:
        favs.remove(clean)
        is_fav = False
    else:
        favs.append(clean)
        is_fav = True
    save_favorite_themes(favs)
    return is_fav




DEFAULT_EXCUSE_PROFILE = {
    "student_name": "Max Mustermann",
    "student_class": "1AHIT",
    "teacher_name": "Prof. Erika Musterlehrer",
    "school_address": "Musterstraße 1",
    "school_district": "A-1010 Wien",
}


def load_excuse_profile() -> dict:
    """Lädt das Schüler- und Schulprofil für das Entschuldigungsschreiben."""
    profile = dict(DEFAULT_EXCUSE_PROFILE)
    for path in [CONFIG_FILE, APP_CONFIG_FILE]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "excuse_profile" in data and isinstance(data["excuse_profile"], dict):
                        for k, v in data["excuse_profile"].items():
                            if v is not None and str(v).strip():
                                profile[k] = str(v).strip()
                        return profile
            except Exception:
                pass
    return profile


def save_excuse_profile(profile_data: dict, auto_push: bool = True) -> None:
    """Speichert das Schüler- und Schulprofil dauerhaft und synchronisiert optional per Git."""
    if not isinstance(profile_data, dict):
        return
    for path in [CONFIG_FILE, APP_CONFIG_FILE]:
        try:
            data = {}
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            data = loaded
                except Exception:
                    data = {}
            cur = data.get("excuse_profile", {})
            if not isinstance(cur, dict):
                cur = {}
            for k in ["student_name", "student_class", "teacher_name", "school_address", "school_district"]:
                if k in profile_data:
                    cur[k] = str(profile_data[k]).strip()
            data["excuse_profile"] = cur
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp_path = f"{path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception:
            pass

    if auto_push:
        try:
            from git_sync_service import is_git_configured, GitSyncService
            if is_git_configured():
                GitSyncService.async_push("Update student profile")
        except Exception:
            pass


def load_full_school_config() -> dict:
    """Lädt die konsolidierte Schüler- und Schulkonfiguration (Profil, Klasse, Gruppe, Schule)."""
    prof = load_excuse_profile()
    grp = _load_untis_group() or "X"
    sch = _load_untis_school() or ""
    cfg = {
        "student_name": prof.get("student_name") or "Max Mustermann",
        "student_class": prof.get("student_class") or "1AHIT",
        "untis_group": grp,
        "untis_school": sch,
        "teacher_name": prof.get("teacher_name") or "Prof. Erika Musterlehrer",
        "school_address": prof.get("school_address") or "Musterstraße 1",
        "school_district": prof.get("school_district") or "A-1010 Wien",
    }
    for path in [CONFIG_FILE, APP_CONFIG_FILE]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        for k in ["student_name", "student_class", "teacher_name", "school_address", "school_district"]:
                            if k in data and data[k] is not None and str(data[k]).strip():
                                cfg[k] = str(data[k]).strip()
            except Exception:
                pass
    return cfg


def save_full_school_config(config_data: dict, auto_push: bool = True) -> None:
    """Speichert die vollständige Konfiguration dauerhaft und synchronisiert sie per Git."""
    if not isinstance(config_data, dict):
        return

    # 1. Excuse Profile speichern (ohne individuellen Push)
    save_excuse_profile({
        "student_name": config_data.get("student_name", ""),
        "student_class": config_data.get("student_class", ""),
        "teacher_name": config_data.get("teacher_name", ""),
        "school_address": config_data.get("school_address", ""),
        "school_district": config_data.get("school_district", ""),
    }, auto_push=False)

    # 2. Untis Gruppe speichern
    grp = config_data.get("untis_group", "")
    if grp:
        save_untis_group(grp, auto_push=False)

    # 3. Untis Schule speichern
    sch = config_data.get("untis_school", "")
    if sch:
        save_untis_school(sch, auto_push=False)

    if auto_push:
        try:
            from git_sync_service import is_git_configured, GitSyncService
            if is_git_configured():
                GitSyncService.async_push("Update student & school config")
        except Exception:
            pass


UNTIS_EXAM_NOTES_FILE = os.path.join(CONFIG_DIR, "untis_exam_notes.json")
APP_UNTIS_EXAM_NOTES_FILE = os.path.join(DATA_DIR, "exam_notes.json")


def load_exam_notes() -> dict:
    """Lädt selbst eingetragene Prüfungsstoffe und Notizen (exam_id -> topic)."""
    notes = {}
    legacy_notes = os.path.join(WORKSPACE_DIR, "exam_notes.json")
    for p in [legacy_notes, APP_UNTIS_EXAM_NOTES_FILE, UNTIS_EXAM_NOTES_FILE]:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        notes.update({str(k): str(v) for k, v in data.items()})
            except Exception:
                pass
    return notes


def save_exam_notes(notes: dict) -> None:
    """Speichert selbst eingetragene Prüfungsstoffe dauerhaft."""
    if not isinstance(notes, dict):
        return
    for p in [APP_UNTIS_EXAM_NOTES_FILE, UNTIS_EXAM_NOTES_FILE]:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp_path = f"{p}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(notes, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, p)
        except Exception:
            pass
    try:
        from git_sync_service import is_git_configured, GitSyncService
        if is_git_configured():
            GitSyncService.async_push("Update exam notes")
    except Exception:
        pass



def save_single_exam_note(exam_id: str, note: str) -> None:
    """Speichert die Notiz/den Stoff für eine spezifische Prüfung."""
    notes = load_exam_notes()
    notes[str(exam_id)] = note.strip()
    save_exam_notes(notes)


def load_all_course_links() -> list[dict]:
    """
    Lädt alle Moodle- und Teams-Kurse für die Schnellöffnung im Browser.
    Gibt eine Liste von Dictionaries mit folgenden Schlüsseln zurück:
    - platform: 'moodle' oder 'teams'
    - display_badge: '[Moodle]' oder '[Teams]'
    - subject: Fachkürzel (z.B. 'SMEN', 'UFW')
    - display_title: Lesbarer Kursname inkl. Klasse
    - url: Direkte Web-URL
    - is_current_class: bool (True für die konfigurierte Schulklasse)
    """
    courses = []
    seen_keys = set()
    full_cfg = load_full_school_config()
    current_class = (full_cfg.get("student_class") or "1AHIT").strip().upper()
    curr_kw = current_class.lower()
    m_grade = re.search(r"^(\d+)", current_class)
    target_grade = int(m_grade.group(1)) if m_grade else 0

    # 1. Moodle Kurse aus Cache laden (strikt nur für die eingestellte Klasse)
    moodle_cache_p = os.path.join(CONFIG_DIR, "moodle_courses_cache.json")
    if not os.path.exists(moodle_cache_p):
        fallback_p = os.path.join(ASSETS_DIR, "default_courses.json")
        if os.path.exists(fallback_p):
            moodle_cache_p = fallback_p
    if os.path.exists(moodle_cache_p):
        try:
            with open(moodle_cache_p, "r", encoding="utf-8") as f:
                m_courses = json.load(f)
                if isinstance(m_courses, list):
                    for mc in m_courses:
                        cid = str(mc.get("id", ""))
                        if not cid:
                            continue
                        url = mc.get("url") or f"{MOODLE_BASE_URL}/course/view.php?id={cid}"
                        fullname = mc.get("fullname", "") or f"Moodle Kurs #{cid}"
                        subj = mc.get("subject", "")
                        grade = mc.get("grade_level", 0)

                        fn_sn_lower = (fullname + " " + mc.get("shortname", "")).lower()
                        is_curr = curr_kw in fn_sn_lower or (target_grade > 0 and grade == target_grade)

                        # Strikt nur Kurse der eingestellten Klasse aufnehmen
                        if not is_curr:
                            continue

                        key = f"moodle_{cid}"
                        seen_keys.add(key)
                        courses.append({
                            "platform": "moodle",
                            "display_badge": "[Moodle]",
                            "subject": subj,
                            "display_title": fullname,
                            "url": url,
                            "is_current_class": True,
                        })
        except Exception:
            pass

    # 2. Teams Kurse:
    # A. Aus benutzerdefinierten Links in config.json
    custom_teams_links = {}
    for p in [CONFIG_FILE, APP_CONFIG_FILE]:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                    if isinstance(cfg_data, dict):
                        custom_links = cfg_data.get("teams_course_links") or cfg_data.get("custom_course_links") or {}
                        if isinstance(custom_links, dict):
                            custom_teams_links.update(custom_links)
            except Exception:
                pass

    # B. Aus synchronisierten Aufgaben (tasks_cache.json)
    cache_tasks_p = CACHE_FILE
    if os.path.exists(cache_tasks_p):
        try:
            with open(cache_tasks_p, "r", encoding="utf-8") as f:
                cdata = json.load(f)
                for t in cdata.get("tasks", []):
                    if t.get("platform") == "teams":
                        subj = t.get("course") or ""
                        full_name = t.get("course_full") or subj
                        if not subj:
                            continue
                        norm_sub = normalize_subject_name(subj)
                        k = f"teams_{norm_sub.lower()}"
                        if k not in seen_keys:
                            seen_keys.add(k)
                            t_url = custom_teams_links.get(subj) or custom_teams_links.get(full_name) or "https://teams.cloud.microsoft/"
                            courses.append({
                                "platform": "teams",
                                "display_badge": "[Teams]",
                                "subject": subj,
                                "display_title": f"{full_name} ({current_class})" if current_class.lower() not in full_name.lower() else full_name,
                                "url": t_url,
                                "is_current_class": True,
                            })
        except Exception:
            pass

    default_teams = [
        ("UFW", "UFW - Unternehmensführung und Wirtschaftsrecht"),
        ("Deutsch", "Deutsch"),
        ("Englisch", "Englisch"),
    ]
    if current_class:
        default_teams.append((current_class, f"{current_class} - Jahrgangsklasse"))
    for subj, full_desc in default_teams:
        norm_sub = normalize_subject_name(subj)
        k = f"teams_{norm_sub.lower()}"
        if k not in seen_keys:
            seen_keys.add(k)
            t_url = custom_teams_links.get(subj) or custom_teams_links.get(full_desc) or "https://teams.cloud.microsoft/"
            courses.append({
                "platform": "teams",
                "display_badge": "[Teams]",
                "subject": subj,
                "display_title": f"{full_desc} ({current_class})" if current_class not in full_desc else full_desc,
                "url": t_url,
                "is_current_class": True,
            })

    # Sortierung: Plattform (Teams zuerst), danach nach Fach und Titel
    def sort_key(c):
        return (
            0 if c["platform"] == "teams" else 1,
            c["subject"].lower(),
            c["display_title"].lower()
        )

    courses.sort(key=sort_key)
    return courses


def get_git_sync_config() -> dict:
    """Lädt die Git-Synchronisations-Konfiguration (Repo-URL, Token, Branch, etc.)."""
    if os.path.exists(GIT_SYNC_CONFIG_FILE):
        try:
            with open(GIT_SYNC_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {
        "repo_url": "",
        "token": "",
        "branch": "main",
        "enabled": False,
        "last_sync": None,
    }


def save_git_sync_config(
    repo_url: str,
    token: str = "",
    branch: str = "main",
    enabled: bool = True,
    last_sync: Optional[str] = None,
) -> None:
    """Speichert die Git-Synchronisations-Konfiguration persistent."""
    cfg = get_git_sync_config()
    cfg["repo_url"] = repo_url.strip()
    cfg["token"] = token.strip()
    cfg["branch"] = branch.strip() or "main"
    cfg["enabled"] = bool(enabled)
    if last_sync is not None:
        cfg["last_sync"] = last_sync

    os.makedirs(os.path.dirname(GIT_SYNC_CONFIG_FILE), exist_ok=True)
    try:
        with open(GIT_SYNC_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save Git sync configuration: {e}", file=sys.stderr)


def remove_git_sync_config() -> None:
    """Entfernt oder deaktiviert die Git-Synchronisations-Konfiguration."""
    if os.path.exists(GIT_SYNC_CONFIG_FILE):
        try:
            os.remove(GIT_SYNC_CONFIG_FILE)
        except Exception:
            pass


DEFAULT_ENABLED_PLATFORMS = {
    "teams": True,
    "moodle": True,
    "untis": True,
    "git": True,
}


def load_enabled_platforms() -> dict:
    """Lädt die aktivierten Plattformen aus config.json (Default: alle aktiv)."""
    for path in [CONFIG_FILE, APP_CONFIG_FILE]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "enabled_platforms" in data:
                        raw = data["enabled_platforms"]
                        if isinstance(raw, dict):
                            res = dict(DEFAULT_ENABLED_PLATFORMS)
                            for k in res:
                                if k in raw:
                                    res[k] = bool(raw[k])
                            return res
            except Exception:
                pass
    return dict(DEFAULT_ENABLED_PLATFORMS)


def save_enabled_platforms(enabled: dict) -> None:
    """Speichert den Aktiv-Status der Plattformen in config.json."""
    if not isinstance(enabled, dict):
        return
    clean_enabled = dict(DEFAULT_ENABLED_PLATFORMS)
    for k in clean_enabled:
        if k in enabled:
            clean_enabled[k] = bool(enabled[k])

    for path in [CONFIG_FILE, APP_CONFIG_FILE]:
        try:
            data = {}
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
            data["enabled_platforms"] = clean_enabled
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save enabled platforms to {path}: {e}", file=sys.stderr)


def is_platform_enabled(platform: str) -> bool:
    """Gibt zurück, ob eine Plattform aktiv geschaltet ist."""
    key = platform.strip().lower()
    return load_enabled_platforms().get(key, True)


# AI Explain Konfiguration & Presets
AI_EXPLAIN_PRESETS = {
    "gemini": {
        "name": "Google Gemini",
        "url_template": "https://gemini.google.com/app",
    },
    "chatgpt": {
        "name": "ChatGPT",
        "url_template": "https://chatgpt.com/?q={prompt}",
    },
    "perplexity": {
        "name": "Perplexity AI",
        "url_template": "https://www.perplexity.ai/search?q={prompt}",
    },
    "custom": {
        "name": "Custom URL",
        "url_template": "https://gemini.google.com/app",
    },
    "app": {
        "name": "Desktop App (.exe)",
        "url_template": "",
    },
}

DEFAULT_AI_CHAT_CONFIG = {
    "provider": "gemini",           # "gemini" | "openai_compatible"
    "api_key": "",
    "model": "gemini-2.0-flash",    # e.g. "gemini-2.0-flash", "gpt-4o-mini"
    "base_url": "https://api.openai.com/v1",
    "language": "de",               # "de" | "en"
}


def load_ai_chat_config() -> dict:
    """Lädt die Konfiguration für das AI-Chat Feature aus config.json."""
    for path in [CONFIG_FILE, APP_CONFIG_FILE]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "ai_chat_config" in data:
                        raw = data["ai_chat_config"]
                        if isinstance(raw, dict):
                            res = dict(DEFAULT_AI_CHAT_CONFIG)
                            if "provider" in raw and str(raw["provider"]).lower() in ["gemini", "openai_compatible"]:
                                res["provider"] = str(raw["provider"]).lower()
                            if "api_key" in raw and isinstance(raw["api_key"], str):
                                res["api_key"] = raw["api_key"].strip()
                            if "model" in raw and isinstance(raw["model"], str) and raw["model"].strip():
                                res["model"] = raw["model"].strip()
                            if "base_url" in raw and isinstance(raw["base_url"], str) and raw["base_url"].strip():
                                res["base_url"] = raw["base_url"].strip()
                            if "language" in raw and str(raw["language"]).lower() in ["de", "en"]:
                                res["language"] = str(raw["language"]).lower()
                            return res
            except Exception:
                pass
    return dict(DEFAULT_AI_CHAT_CONFIG)


def save_ai_chat_config(cfg: dict, auto_push: bool = True) -> None:
    """Speichert die AI-Chat-Einstellungen persistent."""
    if not isinstance(cfg, dict):
        return
    current = load_ai_chat_config()
    if "provider" in cfg and str(cfg["provider"]).lower() in ["gemini", "openai_compatible"]:
        current["provider"] = str(cfg["provider"]).lower()
    if "api_key" in cfg and isinstance(cfg["api_key"], str):
        current["api_key"] = cfg["api_key"].strip()
    if "model" in cfg and isinstance(cfg["model"], str) and cfg["model"].strip():
        current["model"] = cfg["model"].strip()
    if "base_url" in cfg and isinstance(cfg["base_url"], str) and cfg["base_url"].strip():
        current["base_url"] = cfg["base_url"].strip()
    if "language" in cfg and str(cfg["language"]).lower() in ["de", "en"]:
        current["language"] = str(cfg["language"]).lower()

    for path in [CONFIG_FILE, APP_CONFIG_FILE]:
        try:
            data = {}
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
            data["ai_chat_config"] = current
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Could not save ai_chat_config to {path}: {e}", file=sys.stderr)


DEFAULT_AI_EXPLAIN_CONFIG = {
    "provider": "gemini",
    "url_template": "https://gemini.google.com/app",
    "app_path": None,
    "language": "de",
}


def load_ai_explain_config() -> dict:
    """Lädt die Konfiguration für das AI-Explain Feature aus config.json."""
    for path in [CONFIG_FILE, APP_CONFIG_FILE]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "ai_explain_config" in data:
                        raw = data["ai_explain_config"]
                        if isinstance(raw, dict):
                            res = dict(DEFAULT_AI_EXPLAIN_CONFIG)
                            if "provider" in raw and str(raw["provider"]).lower() in AI_EXPLAIN_PRESETS:
                                res["provider"] = str(raw["provider"]).lower()
                            if "url_template" in raw and isinstance(raw["url_template"], str) and raw["url_template"].strip():
                                res["url_template"] = raw["url_template"].strip()
                            if "app_path" in raw:
                                res["app_path"] = str(raw["app_path"]).strip() if raw["app_path"] else None
                            if "language" in raw and str(raw["language"]).lower() in ["de", "en"]:
                                res["language"] = str(raw["language"]).lower()
                            return res
            except Exception:
                pass
    return dict(DEFAULT_AI_EXPLAIN_CONFIG)


def save_ai_explain_config(cfg: dict, auto_push: bool = True) -> None:
    """Speichert die AI-Explain-Einstellungen persistent."""
    if not isinstance(cfg, dict):
        return
    current = load_ai_explain_config()
    if "provider" in cfg and str(cfg["provider"]).lower() in AI_EXPLAIN_PRESETS:
        current["provider"] = str(cfg["provider"]).lower()
    if "url_template" in cfg and isinstance(cfg["url_template"], str) and cfg["url_template"].strip():
        current["url_template"] = cfg["url_template"].strip()
    if "app_path" in cfg:
        val = cfg["app_path"]
        current["app_path"] = val.strip() if isinstance(val, str) and val.strip() else None
    if "language" in cfg and str(cfg["language"]).lower() in ["de", "en"]:
        current["language"] = str(cfg["language"]).lower()

    for path in [CONFIG_FILE, APP_CONFIG_FILE]:
        try:
            data = {}
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
            data["ai_explain_config"] = current
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Could not save ai_explain_config to {path}: {e}", file=sys.stderr)
