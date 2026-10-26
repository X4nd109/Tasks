"""
auth.py - Sichere, persistente Authentifizierung für Moodle und Microsoft Teams.
Zero-Knowledge: Keine Anmeldedaten werden im Klartext geloggt oder übertragen.
"""

import getpass
import json
import os
import shutil
import sys
import time
import urllib.parse
import re
import requests
from typing import Optional, Tuple, Dict

try:
    import msvcrt
except ImportError:
    msvcrt = None

from config import (
    CONFIG_DIR,
    MOODLE_BASE_URL,
    MOODLE_COOKIE_FILE,
    MOODLE_CREDS_POSSIBLE_PATHS,
    UNTIS_CREDS_POSSIBLE_PATHS,
    UNTIS_CACHE_FILE,
    UNTIS_PROFILE_DIR,
    TEAMS_BASE_URL,
    TEAMS_PROFILE_DIR,
    TEAMS_STATUS_FILE,
    CHROMIUM_CACHE_ARGS,
    launch_teams_browser_context,
    is_platform_enabled,
)

TEAMS_OAUTH_AUTHORIZE_URL = (
    "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    "?client_id=5e3ce6c0-2b1f-4285-8d4b-75ee78787346"
    "&scope=openId%20profile%20openid%20offline_access"
    "&redirect_uri=https%3A%2F%2Fteams.cloud.microsoft%2Fv2%2Fauthv2"
    "&response_mode=fragment"
    "&response_type=code"
)


class AuthResult(tuple):
    """
    Rückgabewert für Login-Operationen (success: bool, message: str).
    Abwärtskompatibel mit bool-Prüfungen (if res:) und Tuple-Unpacking (ok, msg = res).
    """
    def __new__(cls, success: bool, message: str = ""):
        return super().__new__(cls, (bool(success), str(message)))

    @property
    def success(self) -> bool:
        return self[0]

    @property
    def message(self) -> str:
        return self[1]

    def __bool__(self) -> bool:
        return self[0]


def clean_school_username(username: str) -> str:
    """Bereinigt Schulkennungen: entfernt versehentlich eingegebene @spengergasse.at E-Mail-Suffixe."""
    if not username:
        return ""
    u = username.strip()
    if "@" in u:
        u = u.split("@")[0].strip()
    return u


def get_saved_moodle_cookies() -> Optional[list]:
    """Lädt gespeicherte Moodle-Cookies, falls vorhanden."""
    if os.path.exists(MOODLE_COOKIE_FILE):
        try:
            with open(MOODLE_COOKIE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def save_moodle_cookies(cookies: list):
    """Speichert Moodle-Cookies für persistente Sitzungen."""
    try:
        with open(MOODLE_COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f)
    except Exception as e:
        print(f"Warning: Could not save Moodle cookies: {e}", file=sys.stderr)


def get_existing_moodle_credentials() -> Tuple[Optional[str], Optional[dict]]:
    """Prüft, ob bereits gespeicherte Moodle-Zugangsdaten auf dem System liegen."""
    for path in MOODLE_CREDS_POSSIBLE_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("logged_out"):
                        return None, None
                    u = data.get("username", "").strip()
                    p = data.get("password", "").strip()
                    if u and p:
                        return path, data
            except Exception:
                continue
    return None, None


def get_existing_untis_credentials() -> Tuple[Optional[str], Optional[dict]]:
    """Prüft, ob gespeicherte WebUntis- oder Schul-Zugangsdaten vorliegen."""
    for path in UNTIS_CREDS_POSSIBLE_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("logged_out"):
                        return None, None
                    u = data.get("username", "").strip()
                    p = data.get("password", "").strip()
                    if u and p:
                        return path, data
            except Exception:
                continue
    return None, None


def save_untis_credentials(username: str, password: str, target_path: Optional[str] = None) -> bool:
    """Speichert WebUntis-Zugangsdaten sicher in einer lokalen JSON-Datei."""
    if not target_path:
        target_path = os.path.join(CONFIG_DIR, "untis_credentials.json")
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump({"username": username.strip(), "password": password.strip()}, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving Untis credentials: {e}", file=sys.stderr)
        return False


def is_moodle_logged_in() -> bool:
    """Checks whether valid Moodle cookies or saved credentials exist."""
    if get_saved_moodle_cookies():
        return True
    path, creds = get_existing_moodle_credentials()
    if creds and creds.get("username") and creds.get("password"):
        return True
    return False


def is_teams_logged_in() -> bool:
    """Checks whether Microsoft Teams is configured or has a valid browser profile."""
    if os.path.exists(TEAMS_STATUS_FILE):
        try:
            with open(TEAMS_STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("configured", False):
                    return True
        except Exception:
            pass
    if os.path.isdir(TEAMS_PROFILE_DIR):
        def_dir = os.path.join(TEAMS_PROFILE_DIR, "Default")
        if os.path.isdir(def_dir) and len(os.listdir(def_dir)) > 3:
            return True
    return False


def is_untis_logged_in() -> bool:
    """Checks whether WebUntis credentials exist."""
    path, creds = get_existing_untis_credentials()
    if creds and creds.get("username") and creds.get("password"):
        return True
    return False


def get_platform_login_status() -> Dict[str, bool]:
    """Returns a dictionary mapping platform keys ('moodle', 'teams', 'untis') to boolean login states."""
    return {
        "moodle": is_moodle_logged_in(),
        "teams": is_teams_logged_in(),
        "untis": is_untis_logged_in(),
    }


def is_git_logged_in() -> bool:
    """Checks whether Git Cloud-Sync is configured."""
    try:
        from git_sync_service import is_git_configured
        return is_git_configured()
    except Exception:
        return False


def logout_moodle(task_mgr=None) -> Tuple[bool, str]:
    """Logs out from Moodle, deletes credentials, cookies, and cached tasks."""
    try:
        if os.path.exists(MOODLE_COOKIE_FILE):
            try:
                os.remove(MOODLE_COOKIE_FILE)
            except Exception:
                pass
        for path in MOODLE_CREDS_POSSIBLE_PATHS:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        if task_mgr and hasattr(task_mgr, "clear_platform_tasks"):
            task_mgr.clear_platform_tasks("moodle")
        return True, "Moodle logged out and cache cleared."
    except Exception as e:
        return False, f"Failed to log out of Moodle: {e}"


def logout_teams(task_mgr=None) -> Tuple[bool, str]:
    """Logs out from Microsoft Teams, deletes browser profile, status file, and cached tasks."""
    try:
        if os.path.exists(TEAMS_STATUS_FILE):
            try:
                os.remove(TEAMS_STATUS_FILE)
            except Exception:
                pass
        if os.path.exists(TEAMS_PROFILE_DIR):
            try:
                shutil.rmtree(TEAMS_PROFILE_DIR, ignore_errors=True)
            except Exception:
                pass
        if task_mgr and hasattr(task_mgr, "clear_platform_tasks"):
            task_mgr.clear_platform_tasks("teams")
        return True, "Microsoft Teams logged out and cache cleared."
    except Exception as e:
        return False, f"Failed to log out of Teams: {e}"


def logout_untis() -> Tuple[bool, str]:
    """Logs out from WebUntis, clears credentials and cache."""
    try:
        for path in UNTIS_CREDS_POSSIBLE_PATHS:
            if os.path.exists(path) and "untis_credentials.json" in os.path.basename(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        untis_path = os.path.join(CONFIG_DIR, "untis_credentials.json")
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(untis_path, "w", encoding="utf-8") as f:
                json.dump({"logged_out": True}, f, indent=2)
        except Exception:
            pass

        if os.path.exists(UNTIS_CACHE_FILE):
            try:
                os.remove(UNTIS_CACHE_FILE)
            except Exception:
                pass
        if os.path.exists(UNTIS_PROFILE_DIR):
            try:
                shutil.rmtree(UNTIS_PROFILE_DIR, ignore_errors=True)
            except Exception:
                pass
        return True, "WebUntis logged out and cache cleared."
    except Exception as e:
        return False, f"Failed to log out of WebUntis: {e}"


def logout_git() -> Tuple[bool, str]:
    """Disconnects Git Cloud-Sync and clears local git cache."""
    try:
        from git_sync_service import GitSyncService
        return GitSyncService.disconnect()
    except Exception as e:
        return False, f"Failed to disconnect Git: {e}"


def has_missing_logins() -> bool:
    """Returns True if any enabled platform (Moodle, Teams, WebUntis) is not logged in."""
    status = get_platform_login_status()
    return any(not ok for platform, ok in status.items() if is_platform_enabled(platform))



def check_moodle_session(page, context) -> bool:
    """Prüft, ob die aktuelle Moodle-Sitzung gültig ist."""
    try:
        page.goto(f"{MOODLE_BASE_URL}/my/", wait_until="domcontentloaded", timeout=12000)
        page.wait_for_timeout(1500)
        if "/login/index.php" in page.url or page.query_selector("form#login, #loginbtn"):
            return False
        return True
    except Exception:
        return False


def login_moodle_with_creds(page, context, username: str, password: str, moodle_url: Optional[str] = None) -> bool:
    """Führt Moodle-Login durch und speichert Cookies."""
    base_url = (moodle_url or MOODLE_BASE_URL).rstrip("/")
    u = clean_school_username(username)
    p = password.strip()
    try:
        page.goto(f"{base_url}/login/index.php", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_selector("#username", timeout=10000)
        page.fill("#username", u)
        page.fill("#password", p)
        page.click("#loginbtn")
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        page.wait_for_timeout(2500)

        # Prüfe auf Fehler
        error_el = page.query_selector("#loginerrormessage, .loginerrors, .alert-danger")
        if error_el and error_el.inner_text().strip():
            return False

        if "/login/index.php" in page.url:
            return False

        # Cookies sichern
        cookies = context.cookies()
        save_moodle_cookies(cookies)
        return True
    except Exception:
        return False


def _humanize_request_error(e: Exception, service_name: str = "Moodle") -> str:
    """Translates raw urllib3 / requests network exceptions into user-friendly diagnostic messages."""
    if isinstance(e, requests.exceptions.Timeout):
        return f"Connection timeout: {service_name} server is not responding."

    if isinstance(e, requests.exceptions.ConnectionError):
        err_str = str(e).lower()
        if "10061" in err_str or "refused" in err_str:
            return f"Connection refused: {service_name} server is offline or requires school VPN."
        if "getaddrinfo" in err_str or "nameresolution" in err_str or "not known" in err_str:
            return f"{service_name} server not found: Check URL or internet connection."
        if "ssl" in err_str or "certificate" in err_str:
            return f"SSL certificate verification failed for {service_name} server."
        return f"Could not connect to {service_name} server: Network or host unreachable."

    if isinstance(e, requests.exceptions.HTTPError):
        status = e.response.status_code if getattr(e, "response", None) is not None else "unknown"
        return f"{service_name} server returned HTTP error: {status}"

    err_str = str(e).lower()
    if "10061" in err_str or "refused" in err_str:
        return f"Connection refused: {service_name} server is offline or requires school VPN."
    if "timeout" in err_str:
        return f"Connection timeout: {service_name} server is not responding."

    return f"Network error connecting to {service_name}: {type(e).__name__}"


def _is_network_connectivity_error(message: str) -> bool:
    """Checks whether an error message indicates an unreachable/offline host or network failure."""
    msg = message.lower()
    keywords = ["refused", "timeout", "not found", "unreachable", "dns", "ssl", "offline", "verbindung fehlgeschlagen"]
    return any(kw in msg for kw in keywords)


def login_moodle_http(username: str, password: str, moodle_url: Optional[str] = None) -> AuthResult:
    """
    Führt Moodle-Login blitzschnell rein über HTTP-Requests durch (~0.3s).
    Funktioniert auf jedem System ohne vorinstalliertes Playwright-Chromium.
    Liest den dynamischen 'logintoken' aus der Moodle-Login-Seite und sendet den POST.
    """
    base_url = (moodle_url or MOODLE_BASE_URL).rstrip("/")
    u = clean_school_username(username)
    p = password.strip()
    if not u or not p:
        return AuthResult(False, "Benutzername und Passwort dürfen nicht leer sein.")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    try:
        login_url = f"{base_url}/login/index.php"
        r_get = session.get(login_url, timeout=12)
        if r_get.status_code != 200:
            return AuthResult(False, f"Moodle-Server antwortet mit HTTP {r_get.status_code}.")

        token_match = re.search(r'name=["\']logintoken["\']\s+value=["\']([^"\']+)["\']', r_get.text)
        logintoken = token_match.group(1) if token_match else ""

        payload = {
            "anchor": "",
            "logintoken": logintoken,
            "username": u,
            "password": p,
        }

        r_post = session.post(login_url, data=payload, timeout=15, allow_redirects=True)

        # Prüfe auf Fehlermeldung auf der Seite
        if "/login/index.php" in r_post.url or "loginerrormessage" in r_post.text or "loginerrors" in r_post.text:
            err_m = re.search(r'class=["\'][^"\']*(?:loginerrors|alert-danger)[^"\']*["\'][^>]*>(.*?)</div>', r_post.text, re.DOTALL | re.IGNORECASE)
            if not err_m:
                err_m = re.search(r'id=["\']loginerrormessage["\'][^>]*>(.*?)</div>', r_post.text, re.DOTALL | re.IGNORECASE)
            err_text = re.sub(r'<[^>]+>', '', err_m.group(1)).strip() if err_m else "Ungültige Anmeldedaten."
            return AuthResult(False, err_text)

        # Prüfe ob Cookies vorhanden sind
        cookie_list = []
        moodle_netloc = urllib.parse.urlparse(base_url).netloc
        for c in session.cookies:
            cookie_list.append({
                "name": c.name,
                "value": c.value,
                "domain": c.domain or moodle_netloc,
                "path": c.path or "/",
                "secure": c.secure,
                "httpOnly": True,
            })

        has_session = any(c.get("name") == "MoodleSession" for c in cookie_list)
        if not has_session and "/login/index.php" in r_post.url:
            return AuthResult(False, "Moodle-Login fehlgeschlagen. Bitte Zugangsdaten prüfen.")

        save_moodle_cookies(cookie_list)
        return AuthResult(True, "OK")
    except requests.exceptions.RequestException as e:
        return AuthResult(False, _humanize_request_error(e, "Moodle"))
    except Exception as e:
        return AuthResult(False, f"Fehler bei Moodle-Authentifizierung: {e}")


def login_moodle_direct(username: str, password: str, moodle_url: Optional[str] = None) -> AuthResult:
    """
    Führt Moodle-Login mit Benutzername und Passwort durch und speichert Credentials lokal.
    Versucht primär blitzschnelles HTTP (funktioniert ohne Playwright-Chromium).
    Fällt bei Bedarf auf Playwright zurück (versucht Edge/Chrome/Chromium).
    """
    if moodle_url:
        from config import save_moodle_base_url
        save_moodle_base_url(moodle_url)

    u = clean_school_username(username)
    p = password.strip()
    if not u or not p:
        return AuthResult(False, "Benutzername und Passwort dürfen nicht leer sein.")

    # 1. Primärer HTTP-Login (blitzschnell, kein Playwright nötig)
    http_res = login_moodle_http(u, p, moodle_url=moodle_url)
    if http_res.success:
        target_creds_file = MOODLE_CREDS_POSSIBLE_PATHS[0]
        os.makedirs(os.path.dirname(target_creds_file), exist_ok=True)
        try:
            with open(target_creds_file, "w", encoding="utf-8") as f:
                json.dump({"username": u, "password": p}, f)
        except Exception:
            pass
        return http_res

    # Falls der Fehler spezifisch "Ungültige Anmeldedaten" war, hat Moodle den Login abgewiesen
    if any(kw in http_res.message.lower() for kw in ["ungültig", "invalid", "kennwort", "password"]):
        return http_res

    # Bei echten Netzwerk- und Verbindungsproblemen (Server offline, Refused, Timeout)
    # macht ein träger Browser-Fallback keinen Sinn und würde nur 15-20s Wartezeit verursachen.
    if _is_network_connectivity_error(http_res.message):
        return http_res

    # 2. Browser-Fallback (falls Moodle JavaScript oder spezielles SSO verlangt)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = None
            for ch in [None, "chrome", "msedge"]:
                try:
                    kwargs = {"headless": True}
                    if ch:
                        kwargs["channel"] = ch
                    browser = pw.chromium.launch(**kwargs)
                    if browser:
                        break
                except Exception:
                    continue

            if browser:
                context = browser.new_context()
                page = context.new_page()
                success = login_moodle_with_creds(page, context, u, p, moodle_url=moodle_url)
                browser.close()
                if success:
                    target_creds_file = MOODLE_CREDS_POSSIBLE_PATHS[0]
                    os.makedirs(os.path.dirname(target_creds_file), exist_ok=True)
                    try:
                        with open(target_creds_file, "w", encoding="utf-8") as f:
                            json.dump({"username": u, "password": p}, f)
                    except Exception:
                        pass
                    return AuthResult(True, "OK")
    except Exception:
        pass

    return http_res


def setup_moodle_interactive(console=None) -> bool:
    """Interactive login for Moodle in the terminal with masked password input."""
    if console:
        console.print("\n[bold orange3]── Moodle Login ──[/bold orange3]")
        console.print("[dim]Your credentials are stored locally on your PC only.[/dim]")
    else:
        print("\n── Moodle Login ──")

    try:
        current_url = MOODLE_BASE_URL
        if console:
            console.print(f"[dim]Current server URL: [cyan]{current_url}[/cyan] (Press ENTER to keep)[/dim]")
        url_input = input(f"Moodle URL [{current_url}]: ").strip()
        moodle_url = url_input if url_input else current_url
        if moodle_url != current_url:
            from config import save_moodle_base_url
            save_moodle_base_url(moodle_url)

        raw_username = input("Moodle username (or email): ").strip()
        username = clean_school_username(raw_username)
        if not username:
            print("Cancelled: No username entered.")
            return False
        if "@" in raw_username:
            print(f"Notice: Cleaned username to '{username}' (school email domain removed).")

        password = getpass.getpass("Moodle password: ").strip()
        if not password:
            print("Cancelled: No password entered.")
            return False

        print("Checking Moodle login...")
        res = login_moodle_direct(username, password, moodle_url=moodle_url)
        if res.success:
            if console:
                console.print("[bold green]✓ Moodle login successful and saved permanently![/bold green]")
            else:
                print("✓ Moodle login successful and saved permanently!")
            return True
        else:
            err = res.message or "Moodle login failed. Please check your username and password."
            if console:
                console.print(f"[bold red]✗ {err}[/bold red]")
            else:
                print(f"✗ {err}")
            return False
    except KeyboardInterrupt:
        print("\nCancelled.")
        return False


def check_teams_session() -> bool:
    """Prüft blitzschnell (0.001s, ohne Browser-Start!), ob Teams verknüpft ist."""
    if os.path.exists(TEAMS_STATUS_FILE):
        try:
            with open(TEAMS_STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return bool(data.get("configured", False))
        except Exception:
            pass
    return False


def test_teams_session_live() -> bool:
    """Prüft im Headless-Modus (ohne sichtbares Fenster), ob die Teams-Sitzung gültig ist."""
    from playwright.sync_api import sync_playwright

    if not os.path.exists(TEAMS_PROFILE_DIR):
        return False
    try:
        with sync_playwright() as p:
            ctx = launch_teams_browser_context(
                p,
                user_data_dir=TEAMS_PROFILE_DIR,
                headless=True,
                args=["--disable-blink-features=AutomationControlled"] + CHROMIUM_CACHE_ARGS
            )
            if not ctx:
                return False
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(TEAMS_BASE_URL, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass

            logged_in_selectors = (
                '[data-tid="user-avatar"], '
                'button[id*="personDropdown"], '
                'div[data-tid*="app-bar"], '
                'button[data-tid="66aeee93-507d-479a-a3ef-8f494af43945"], '
                '[role="navigation"], '
                'div[data-tid*="team-card"], '
                'button[aria-label*="Zuweisungen" i], '
                'button[aria-label*="Aufgaben" i], '
                'button[aria-label*="Assignment" i], '
                'button[aria-label*="Teams" i], '
                'button[aria-label*="Chat" i], '
                'button[aria-label*="Aktivität" i], '
                'button[aria-label*="Activity" i], '
                'button[aria-label*="Kalender" i], '
                'button[aria-label*="Calendar" i], '
                'div[data-tid*="left-rail"], '
                'div[data-tid*="powerbar"], '
                'div[role="main"], '
                'div[data-tid*="chat-list"]'
            )

            session_valid = False
            start_check = time.time()
            while time.time() - start_check < 25.0:
                url = page.url.lower()
                title = page.title().lower()

                # 1. Haben wir Teams UI-Elemente in Page oder Frames?
                has_ind = False
                try:
                    if page.locator(logged_in_selectors).count() > 0:
                        has_ind = True
                except Exception:
                    pass
                if not has_ind:
                    for fr in page.frames:
                        try:
                            if fr.locator(logged_in_selectors).count() > 0:
                                has_ind = True
                                break
                        except Exception:
                            pass

                # Teams URL oder typische App-Titel
                if has_ind or (("teams.live.com" in url or "teams.cloud.microsoft" in url or "teams.microsoft.com" in url) and any(kw in title for kw in ["chat", "teams", "aktivität", "activity", "besprechung", "zuweisungen"])):
                    session_valid = True
                    break

                # 2. Erst nach mind. 6 Sekunden ein definitives Login-Formular als abgelaufen werten
                if time.time() - start_check > 6.0:
                    try:
                        login_inputs = page.locator('input[type="email"]:visible, input[type="password"]:visible, input#i0116:visible, input#i0118:visible')
                        if login_inputs.count() > 0 and ("login.microsoftonline.com" in url or "login.live.com" in url):
                            session_valid = False
                            break
                    except Exception:
                        pass

                page.wait_for_timeout(800)

            if session_valid:
                try:
                    with open(TEAMS_STATUS_FILE, "w", encoding="utf-8") as f:
                        json.dump({"configured": True, "last_login": time.time()}, f)
                except Exception:
                    pass

            ctx.close()
            return session_valid
    except Exception:
        return False


def setup_teams_interactive(console=None, fresh: bool = False, email: Optional[str] = None) -> bool:
    """
    Interactive setup for Microsoft Teams.
    - If fresh=False: detects existing sessions and offers direct reuse or fresh login.
    - If fresh=True: directly clears old profile and opens fresh Microsoft login page.
    - Supports Passkeys (Windows Hello, FIDO2, Security Keys) directly in the opened browser.
    - Automatically detects login, confirms dialogs across all frames, and saves the session.
    """
    from playwright.sync_api import sync_playwright

    session_exists = check_teams_session() or (
        os.path.exists(TEAMS_PROFILE_DIR) and len(os.listdir(TEAMS_PROFILE_DIR)) > 5
    )

    if session_exists and not fresh:
        if console:
            console.print("\n[bold dodger_blue1]── Microsoft Teams Connection ──[/bold dodger_blue1]")
            console.print("[green]✓ Saved Teams session profile found.[/green]\n")
            console.print("  [bold cyan][1][/bold cyan] Check & use existing session [dim](Recommended)[/dim]")
            console.print("  [bold cyan][2][/bold cyan] Fresh new login [dim](Clears old cache & opens fresh Microsoft login page)[/dim]")
            console.print("  [bold cyan][3][/bold cyan] Cancel\n")
            try:
                from rich.prompt import Prompt
                choice = Prompt.ask("Choice [1-3]", default="1").strip()
            except Exception:
                choice = input("Choice [1-3] (Default: 1): ").strip() or "1"
        else:
            print("\n── Microsoft Teams Connection ──")
            print("✓ Saved Teams session profile found.\n")
            print("  [1] Check & use existing session (Recommended)")
            print("  [2] Fresh new login (Clears old cache & opens fresh Microsoft login page)")
            print("  [3] Cancel\n")
            try:
                choice = input("Choice [1-3] (Default: 1): ").strip() or "1"
            except Exception:
                choice = "1"

        if choice in ["3", "q", "exit", "cancel", "back", "zurueck", "abbrechen"]:
            if console:
                console.print("[dim]Cancelled.[/dim]\n")
            else:
                print("Cancelled.\n")
            return False

        if choice == "1":
            if console:
                console.print("[cyan]Checking existing Teams session in background...[/cyan]")
            else:
                print("Checking existing Teams session in background...")
            if test_teams_session_live():
                try:
                    with open(TEAMS_STATUS_FILE, "w", encoding="utf-8") as f:
                        json.dump({"configured": True, "last_login": time.time()}, f)
                except Exception:
                    pass
                if console:
                    console.print("[bold green]✓ Existing Teams session is active and ready to use![/bold green]\n")
                else:
                    print("✓ Existing Teams session is active and ready to use!\n")
                return True
            else:
                if console:
                    console.print("[yellow]! Previous session has expired. Starting fresh login...[/yellow]\n")
                else:
                    print("! Previous session has expired. Starting fresh login...\n")

    # Frisch neu anmelden: Alten Cache & Profil vollständig löschen
    if os.path.exists(TEAMS_PROFILE_DIR):
        try:
            shutil.rmtree(TEAMS_PROFILE_DIR, ignore_errors=True)
        except Exception:
            pass
    os.makedirs(TEAMS_PROFILE_DIR, exist_ok=True)

    try:
        with open(TEAMS_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump({"configured": False}, f)
    except Exception:
        pass

    if console:
        console.print("\n[bold dodger_blue1]── Microsoft Teams Setup (Browser / Passkey Login) ──[/bold dodger_blue1]")
        console.print("[white]Opening browser with clean Microsoft login page...[/white]")
        console.print("[yellow]1. Sign in with your school email and Passkey (Windows Hello) or password.[/yellow]")
        console.print("[yellow]2. Confirm two-factor authentication if requested.[/yellow]")
        console.print("[yellow]3. IMPORTANT: Check 'Stay signed in: Yes'![/yellow]")
        console.print("[cyan]4. As soon as you see your classes or assignments, window will close automatically (or press ENTER).[/cyan]\n")
    else:
        print("\n── Microsoft Teams Setup (Browser / Passkey Login) ──")
        print("Opening browser with clean Microsoft login page...")
        print("1. Sign in with your school email and Passkey (Windows Hello) or password.")
        print("2. Confirm two-factor authentication if requested.")
        print("3. IMPORTANT: Check 'Stay signed in: Yes'!")
        print("4. As soon as you see your classes or assignments, window will close automatically (or press ENTER).\n")

    launch_args = [
        "--start-maximized",
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check"
    ] + CHROMIUM_CACHE_ARGS

    is_ok = False
    with sync_playwright() as p:
        ctx = launch_teams_browser_context(
            p,
            user_data_dir=TEAMS_PROFILE_DIR,
            headless=False,
            args=launch_args,
        )

        if not ctx:
            if console:
                console.print("[bold red]Error: Could not open browser window.[/bold red]")
            else:
                print("Error: Could not open browser window.", flush=True)
            return False

        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.bring_to_front()

        # Guard against popup storms: keep at most 2 tabs open
        def _on_extra_page(p_new):
            try:
                if len(ctx.pages) > 2:
                    p_new.close()
            except Exception:
                pass

        ctx.on("page", _on_extra_page)

        login_email = email.strip() if email and email.strip() else ""
        target_login_url = f"{TEAMS_BASE_URL}/?loginHint={urllib.parse.quote(login_email)}" if login_email else TEAMS_BASE_URL

        print("Loading Microsoft Teams...", flush=True)
        try:
            page.goto(target_login_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass

        print("\n" + "=" * 65, flush=True)
        print(" BROWSER IS OPEN!", flush=True)
        print(" 1. Sign in with your school email and Passkey (Windows Hello) or password.", flush=True)
        print(" 2. IMPORTANT: Confirm 'Stay signed in: Yes' if prompted.", flush=True)
        print(" 3. As soon as you see your classes or assignments:", flush=True)
        print("    Window will complete automatically, or press [ENTER] here!", flush=True)
        print("=" * 65 + "\n", flush=True)

        start_t = time.time()
        login_seen_time = None

        logged_in_selectors = (
            '[data-tid="user-avatar"], '
            'button[id*="personDropdown"], '
            'div[data-tid*="app-bar"], '
            'button[data-tid="66aeee93-507d-479a-a3ef-8f494af43945"], '
            '[role="navigation"], '
            'div[data-tid*="team-card"], '
            'button[aria-label*="Zuweisungen" i], '
            'button[aria-label*="Aufgaben" i], '
            'button[aria-label*="Assignment" i], '
            'button[aria-label*="Teams" i], '
            'button[aria-label*="Chat" i], '
            'button[aria-label*="Aktivität" i], '
            'button[aria-label*="Activity" i], '
            'button[aria-label*="Kalender" i], '
            'button[aria-label*="Calendar" i], '
            'div[data-tid*="left-rail"], '
            'div[data-tid*="powerbar"]'
        )

        while time.time() - start_t < 360:  # 6 Minuten Zeitfenster
            # Tastenabfrage (ENTER) im Terminal falls interaktiv
            if console and msvcrt and msvcrt.kbhit():
                try:
                    key = msvcrt.getch()
                    if key in [b"\r", b"\n"]:
                        print("\n✓ Manual confirmation received in terminal.", flush=True)
                        try:
                            curr_url = page.url.lower()
                            if "login.microsoftonline.com" not in curr_url and "login.live.com" not in curr_url:
                                is_ok = True
                        except Exception:
                            is_ok = True
                        break
                except Exception:
                    pass

            open_pages = [p for p in ctx.pages if not p.is_closed()]
            if not open_pages:
                break

            for p_active in open_pages:
                try:
                    curr_url = p_active.url.lower()

                    # Fallback für hängendes authv2: Leite zur Teams-Startseite weiter
                    if "/v2/authv2" in curr_url:
                        p_active.wait_for_timeout(2000)
                        if "/v2/authv2" in p_active.url.lower():
                            try:
                                p_active.goto(TEAMS_BASE_URL, wait_until="domcontentloaded", timeout=15000)
                            except Exception:
                                pass

                    # KMSI ("Angemeldet bleiben?") automatisch bestätigen
                    try:
                        kmsi_btn = p_active.locator('#idSIButton9, input[value="Yes"], input[value="Ja"], button:has-text("Yes"), button:has-text("Ja")').first
                        if kmsi_btn.count() > 0 and kmsi_btn.is_visible():
                            try:
                                chk = p_active.locator('#KmsiCheckboxField').first
                                if chk.count() > 0 and chk.is_visible():
                                    chk.check()
                            except Exception:
                                pass
                            kmsi_btn.click()
                    except Exception:
                        pass

                    # "Web-App stattdessen verwenden" automatisch bestätigen
                    try:
                        for wb_sel in ['button:has-text("Web-App stattdessen")', 'a:has-text("Web-App stattdessen")', 'button:has-text("Use the web app instead")', 'a:has-text("Use the web app instead")']:
                            wb = p_active.locator(wb_sel).first
                            if wb.count() > 0 and wb.is_visible():
                                wb.click()
                                break
                    except Exception:
                        pass

                    # Nutzer hat Microsoft-Login verlassen und ist auf Teams
                    if "login.microsoftonline.com" not in curr_url and "login.live.com" not in curr_url and ("teams.cloud.microsoft" in curr_url or "teams.microsoft.com" in curr_url):
                        has_indicator = False
                        try:
                            if p_active.locator(logged_in_selectors).count() > 0:
                                has_indicator = True
                        except Exception:
                            pass

                        if not has_indicator:
                            for fr in p_active.frames:
                                try:
                                    if fr.locator(logged_in_selectors).count() > 0:
                                        has_indicator = True
                                        break
                                except Exception:
                                    pass

                        if has_indicator:
                            if login_seen_time is None:
                                login_seen_time = time.time()
                                print("\n✓ Teams loaded successfully! Securing session profile...", flush=True)

                            # Gib dem Browser 3 Sekunden Zeit, damit alle Tokens (IndexedDB & Cookies)
                            # stabil gespeichert werden, bevor das Fenster geschlossen wird
                            if (time.time() - login_seen_time) >= 3.0:
                                print("✓ Teams session verified and saved permanently!", flush=True)
                                is_ok = True
                                break
                except Exception:
                    pass

            if is_ok:
                break

            time.sleep(0.8)

        # Fallback Check falls Fenster manuell geschlossen wurde
        if not is_ok:
            try:
                curr_url = page.url.lower()
                if "login.microsoftonline.com" not in curr_url and ("teams.cloud.microsoft" in curr_url or "teams.microsoft.com" in curr_url):
                    is_ok = True
            except Exception:
                pass

        print("Saving Teams session profile...")
        try:
            ctx.close()
        except Exception:
            pass

    # Falls is_ok noch False ist (z.B. weil das Fenster direkt geschlossen wurde),
    # finaler Verifizierungstest der gespeicherten Sitzung:
    if not is_ok:
        if test_teams_session_live():
            is_ok = True

    if is_ok:
        try:
            with open(TEAMS_STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump({"configured": True, "last_login": time.time()}, f)
        except Exception:
            pass

        if console:
            console.print("[bold green]✓ Microsoft Teams connected successfully! Session saved permanently.[/bold green]\n")
        else:
            print("✓ Microsoft Teams connected successfully! Session saved permanently.\n")
        return True
    else:
        if console:
            console.print("[bold yellow]! Teams login was not completed.[/bold yellow]\n")
        else:
            print("! Teams login was not completed.\n")
        return False


def login_teams_direct(
    email: str,
    password: str,
    on_status: Optional[callable] = None,
    on_mfa_number: Optional[callable] = None,
    on_mfa_code_request: Optional[callable] = None,
    headless: bool = True,
    timeout_sec: int = 180,
) -> Tuple[bool, str]:
    """
    Führt einen automatisierten Teams-Login mit E-Mail und Passwort aus.
    Unterstützt 2FA (Authenticator Number Matching oder SMS-Code) über Callbacks.
    Speichert bei Erfolg die Sitzung dauerhaft im Profil ab.
    """
    from playwright.sync_api import sync_playwright

    email = email.strip()
    password = password.strip()
    if not email or not password:
        return False, "E-Mail oder Passwort fehlt."

    def _notify(msg: str):
        if on_status:
            try:
                on_status(msg)
            except Exception:
                pass

    _notify("Starte sichere Browser-Sitzung...")

    # Frisches Profil anlegen für saubere Authentifizierung
    if os.path.exists(TEAMS_PROFILE_DIR):
        try:
            shutil.rmtree(TEAMS_PROFILE_DIR, ignore_errors=True)
        except Exception:
            pass
    os.makedirs(TEAMS_PROFILE_DIR, exist_ok=True)

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
    ] + CHROMIUM_CACHE_ARGS

    try:
        with sync_playwright() as p:
            ctx = launch_teams_browser_context(
                p,
                user_data_dir=TEAMS_PROFILE_DIR,
                headless=headless,
                args=launch_args,
            )
            if not ctx:
                return False, "Browser konnte nicht gestartet werden."

            # Guard against popup storms
            def _on_extra(p_new):
                try:
                    if len(ctx.pages) > 2:
                        p_new.close()
                except Exception:
                    pass
            ctx.on("page", _on_extra)

            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            _notify("Öffne Microsoft-Anmeldeseite...")

            target_url = (
                f"{TEAMS_BASE_URL}/?loginHint={urllib.parse.quote(email)}"
                if email
                else TEAMS_BASE_URL
            )

            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass

            start_t = time.time()
            email_submitted = False
            password_submitted = False
            kmsi_clicked = False
            last_mfa_num = None
            fido_attempts = 0

            while time.time() - start_t < timeout_sec:
                if page.is_closed():
                    return False, "Browser-Sitzung wurde unerwartet geschlossen."

                curr_url = page.url.lower()

                # Fallback für hängendes authv2
                if "/v2/authv2" in curr_url:
                    page.wait_for_timeout(2000)
                    if "/v2/authv2" in page.url.lower():
                        try:
                            page.goto(TEAMS_BASE_URL, wait_until="domcontentloaded", timeout=15000)
                        except Exception:
                            pass

                # 1. Erfolgreich in Teams angekommen?
                if "login.microsoftonline.com" not in curr_url and "login.live.com" not in curr_url and ("teams.cloud.microsoft" in curr_url or "teams.microsoft.com" in curr_url):
                    logged_in_selectors = (
                        '[data-tid="user-avatar"], '
                        'button[id*="personDropdown"], '
                        'div[data-tid*="app-bar"], '
                        'button[data-tid="66aeee93-507d-479a-a3ef-8f494af43945"], '
                        '[role="navigation"], '
                        'div[data-tid*="team-card"], '
                        'button[aria-label*="Zuweisungen" i], '
                        'button[aria-label*="Aufgaben" i], '
                        'button[aria-label*="Assignment" i], '
                        'button[aria-label*="Teams" i], '
                        'button[aria-label*="Chat" i], '
                        'button[aria-label*="Aktivität" i], '
                        'button[aria-label*="Activity" i], '
                        'button[aria-label*="Kalender" i], '
                        'button[aria-label*="Calendar" i], '
                        'div[data-tid*="left-rail"], '
                        'div[data-tid*="powerbar"]'
                    )
                    has_ind = False
                    try:
                        if page.locator(logged_in_selectors).count() > 0:
                            has_ind = True
                    except Exception:
                        pass
                    if not has_ind:
                        for fr in page.frames:
                            try:
                                if fr.locator(logged_in_selectors).count() > 0:
                                    has_ind = True
                                    break
                            except Exception:
                                pass

                    if has_ind:
                        _notify("Teams geladen! Sichere Sitzungsdaten...")
                        time.sleep(4.0)
                        try:
                            with open(TEAMS_STATUS_FILE, "w", encoding="utf-8") as f:
                                json.dump({"configured": True, "last_login": time.time()}, f)
                        except Exception:
                            pass
                        try:
                            ctx.close()
                        except Exception:
                            pass
                        return True, "Erfolgreich angemeldet!"

                # 2. Fehlermeldungen prüfen
                try:
                    for err_sel in ["#usernameError", "#passwordError", ".alert-error", "div[role='alert']"]:
                        err_el = page.locator(err_sel).first
                        if err_el.count() > 0 and err_el.is_visible():
                            txt = err_el.inner_text().strip()
                            if txt:
                                try:
                                    ctx.close()
                                except Exception:
                                    pass
                                return False, f"Microsoft-Fehler: {txt}"
                except Exception:
                    pass

                # 3. E-Mail-Eingabe (oder durch login_hint bereits übersprungen)
                if not email_submitted:
                    try:
                        # Falls Microsoft durch login_hint direkt beim Passwort/FIDO gelandet ist:
                        if "bridge/fido" in curr_url or page.locator('input[type="password"], input[name="passwd"], input#i0118').count() > 0:
                            email_submitted = True
                        else:
                            inp_email = page.locator('input[type="email"], input[name="loginfmt"], input#i0116').first
                            if inp_email.count() > 0 and inp_email.is_visible():
                                _notify("E-Mail wird übermittelt...")
                                inp_email.fill(email)
                                page.wait_for_timeout(300)
                                btn_next = page.locator('input[type="submit"], button[type="submit"], input#idSIButton9').first
                                if btn_next.count() > 0:
                                    btn_next.click()
                                    email_submitted = True
                                    _notify("E-Mail übermittelt, warte auf Passwort-Feld...")
                                    page.wait_for_timeout(1000)
                                    continue
                    except Exception:
                        pass

                # 3b. Passkey / FIDO Bridge abfangen und zu Passwort wechseln
                if email_submitted and not password_submitted:
                    try:
                        # A) FIDO-Bridge-Seite (Face, fingerprint, PIN or security key)
                        if "bridge/fido" in curr_url or "face, fingerprint" in (page.title() or "").lower():
                            fido_attempts += 1
                            if fido_attempts > 4:
                                try:
                                    ctx.close()
                                except Exception:
                                    pass
                                return False, "Passkey erforderlich. Bitte nutze die Option '🔑 Mit Passkey / Browser anmelden'."
                            _notify("Passkey-Abfrage erkannt: Wechsle zu Kennwort...")
                            btn_back = page.locator('#idBtn_Back, button:has-text("Back"), button:has-text("Zurück"), button:has-text("Cancel"), button:has-text("Abbrechen")').first
                            if btn_back.count() > 0 and btn_back.is_visible():
                                btn_back.click()
                                page.wait_for_timeout(1500)
                                continue

                        # B) Anmeldeoptionen / 'Use my password' / 'Mein Kennwort'
                        pwd_choice = page.locator(
                            'text=/Use my password|Mein Kennwort|Kennwort verwenden|Use password/i, '
                            '#idA_PWD_SwitchToPassword, '
                            '[data-testid="switchToPassword"], '
                            '#signInAnotherWay'
                        ).first
                        if pwd_choice.count() > 0 and pwd_choice.is_visible():
                            _notify("Wähle Kennwort-Anmeldung...")
                            pwd_choice.click()
                            page.wait_for_timeout(1500)
                            continue
                    except Exception:
                        pass

                # 4. Passwort-Eingabe
                if email_submitted and not password_submitted:
                    try:
                        inp_pwd = page.locator('input[type="password"], input[name="passwd"], input#i0118').first
                        if inp_pwd.count() > 0 and inp_pwd.is_visible():
                            _notify("Passwort wird eingegeben...")
                            inp_pwd.fill(password)
                            page.wait_for_timeout(300)
                            btn_submit = page.locator('input[type="submit"], button[type="submit"], input#idSIButton9').first
                            if btn_submit.count() > 0:
                                btn_submit.click()
                                password_submitted = True
                                _notify("Passwort übermittelt, prüfe 2-Faktor-Authentifizierung...")
                                page.wait_for_timeout(1500)
                                continue
                    except Exception:
                        pass

                # 5. Zwei-Faktor-Authentifizierung (2FA / MFA)
                if password_submitted:
                    # a) Microsoft Authenticator Number Matching
                    try:
                        mfa_sign_el = page.locator('#idRichContext_DisplaySign, div.displaySign, [data-testid="displaySign"], div.text-block-large_display-sign').first
                        if mfa_sign_el.count() > 0 and mfa_sign_el.is_visible():
                            num_txt = mfa_sign_el.inner_text().strip()
                            if num_txt and num_txt != last_mfa_num:
                                last_mfa_num = num_txt
                                if on_mfa_number:
                                    try:
                                        on_mfa_number(num_txt)
                                    except Exception:
                                        pass
                                _notify(f"Bestätige Zahl [{num_txt}] in deiner Authenticator App!")
                    except Exception:
                        pass

                    # b) SMS / TOTP Code Eingabe
                    try:
                        otc_input = page.locator('input[name="otc"], input#idTxtBx_SAOTCC_OTC, input[type="tel"]').first
                        if otc_input.count() > 0 and otc_input.is_visible():
                            if on_mfa_code_request:
                                _notify("SMS- / Verifizierungscode erforderlich...")
                                code = on_mfa_code_request()
                                if code:
                                    _notify("Übermittle Verifizierungscode...")
                                    otc_input.fill(str(code).strip())
                                    page.wait_for_timeout(300)
                                    btn_otc = page.locator('input[type="submit"], button[type="submit"], input#idSubmit_SAOTCC_Continue').first
                                    if btn_otc.count() > 0:
                                        btn_otc.click()
                                        page.wait_for_timeout(1000)
                                        continue
                    except Exception:
                        pass

                    # c) KMSI ("Angemeldet bleiben? / Stay signed in?")
                    try:
                        kmsi_btn = page.locator('#idSIButton9, input[value="Yes"], input[value="Ja"], button:has-text("Yes"), button:has-text("Ja")').first
                        if kmsi_btn.count() > 0 and kmsi_btn.is_visible() and not kmsi_clicked:
                            try:
                                chk = page.locator('#KmsiCheckboxField').first
                                if chk.count() > 0 and chk.is_visible():
                                    chk.check()
                            except Exception:
                                pass
                            _notify("Bestätige 'Angemeldet bleiben: Ja'...")
                            kmsi_btn.click()
                            kmsi_clicked = True
                            page.wait_for_timeout(1500)
                            continue
                    except Exception:
                        pass

                page.wait_for_timeout(800)

            try:
                ctx.close()
            except Exception:
                pass
            return False, "Timeout during Microsoft Teams login."
    except Exception as e:
        return False, f"Error during Microsoft Teams login: {e}"
