"""
teams_service.py - Service zum Abrufen von Microsoft Teams Aufgaben, Details und Dateidownloads.
Nutzt das persistente Playwright-Browserprofil für dauerhaftes Single-Sign-On.
"""

import json
import os
import re
import sys
import time
from typing import List, Optional
from playwright.sync_api import sync_playwright

from config import (
    TEAMS_BASE_URL,
    TEAMS_PROFILE_DIR,
    TEAMS_STATUS_FILE,
    get_task_download_dir,
    normalize_subject_name,
    sanitize_filename,
    extract_teacher,
    CHROMIUM_CACHE_ARGS,
    launch_teams_browser_context,
    open_teams_context,
    is_shutting_down,
)
from auth import check_teams_session
from models import Task, TaskAttachment

TEAMS_ASSIGNMENTS_APP_ID = "66aeee93-507d-479a-a3ef-8f494af43945"
TEAMS_ASSIGNMENTS_URL = "https://teams.cloud.microsoft/"


def parse_teams_due_date(iso_str: str) -> str:
    """Wandelt ein ISO-Datum in lesbares deutsches Format um."""
    if not iso_str:
        return "Keine Frist"
    try:
        clean_str = iso_str.replace("Z", "+00:00")
        import datetime
        dt = datetime.datetime.fromisoformat(clean_str)
        local_dt = dt.astimezone()
        now = datetime.datetime.now(local_dt.tzinfo)
        diff = (local_dt.date() - now.date()).days

        time_str = local_dt.strftime("%H:%M")
        if diff == 0:
            return f"Heute, {time_str} Uhr"
        elif diff == 1:
            return f"Morgen, {time_str} Uhr"
        elif diff == -1:
            return f"Gestern, {time_str} Uhr"
        elif diff < -1:
            return f"Vor {-diff} Tagen"
        else:
            months = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sept.", "Okt.", "Nov.", "Dez."]
            m_name = months[local_dt.month - 1]
            return f"{local_dt.day}. {m_name}, {time_str} Uhr"
    except Exception:
        return iso_str[:16].replace("T", " ")


def format_teams_description(instructions) -> str:
    """Wandelt Teams Anweisungen (HTML/String/Dict) in sauberen Markdown/Klartext um."""
    if not instructions:
        return ""
    description_text = ""
    if isinstance(instructions, dict):
        description_text = instructions.get("content", "")
    elif isinstance(instructions, str):
        description_text = instructions

    if not description_text or not isinstance(description_text, str):
        return ""

    import html
    description_text = html.unescape(description_text).replace("\xa0", " ")

    description_text = re.sub(r"!\[.*?\]\(.*?\)", "[Bild]", description_text)
    description_text = re.sub(r"<img[^>]*>", "[Bild]", description_text, flags=re.IGNORECASE)
    description_text = re.sub(r"\[\s*\[Bild\]\s*\]\(.*?\)", "[Bild]", description_text)
    description_text = re.sub(r"\[Bild\]\(.*?\)", "[Bild]", description_text)

    if "<" in description_text and ">" in description_text:
        description_text = re.sub(r"<style[^>]*>.*?</style>", "", description_text, flags=re.DOTALL | re.IGNORECASE)
        description_text = re.sub(r"<script[^>]*>.*?</script>", "", description_text, flags=re.DOTALL | re.IGNORECASE)
        description_text = re.sub(r"<h[1-6][^>]*>", "\n\n### ", description_text, flags=re.IGNORECASE)
        description_text = re.sub(r"</h[1-6]>", "\n\n", description_text, flags=re.IGNORECASE)
        description_text = re.sub(r"<li[^>]*>", "\n* ", description_text, flags=re.IGNORECASE)
        description_text = re.sub(r"</li>", "\n", description_text, flags=re.IGNORECASE)
        description_text = re.sub(r"<br\s*/?>", "\n", description_text, flags=re.IGNORECASE)
        description_text = re.sub(r"</p>", "\n\n", description_text, flags=re.IGNORECASE)
        description_text = re.sub(r"</div>", "\n", description_text, flags=re.IGNORECASE)
        description_text = re.sub(r"<[^>]+>", "", description_text)
        description_text = re.sub(r"\n{3,}", "\n\n", description_text).strip()

    return description_text


def extract_teams_attachments(resources, default_url: str = "") -> List[TaskAttachment]:
    """Extrahiert TaskAttachment-Objekte aus Teams API-Ressourcen."""
    attachments: List[TaskAttachment] = []
    if isinstance(resources, list):
        for r in resources:
            res_obj = r.get("resource", {}) if isinstance(r, dict) else {}
            fname = res_obj.get("displayName") or r.get("displayName") or "Anhang"
            furl = res_obj.get("downloadUrl") or res_obj.get("webUrl") or default_url
            attachments.append(TaskAttachment(name=fname, url=furl))
    return attachments


def fetch_teams_tasks() -> List[Task]:
    """
    Ruft alle Microsoft Teams Aufgaben über das persistente Browser-Profil ab.
    Fängt API-Payloads von assignments.edu.cloud.microsoft ab und extrahiert
    Aufgabendaten, Klassen-Namen, Fristen und Abgabelinks.
    """
    if not check_teams_session():
        return []

    tasks: List[Task] = []
    seen_ids = set()
    intercepted_items = []
    last_intercept_time = [0.0]

    try:
        with sync_playwright() as p, open_teams_context(
            p,
            user_data_dir=TEAMS_PROFILE_DIR,
            headless=True,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"] + CHROMIUM_CACHE_ARGS
        ) as ctx:
            if not ctx:
                return []
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            # 1. Netzwerk-Überwachung für JSON-Aufgabendaten
            def handle_response(response):
                try:
                    url = response.url.lower()
                    if ("assignments.edu" in url or "edu/me/work" in url or "work" in url or "assignment" in url) and "json" in (response.headers.get("content-type") or ""):
                        data = response.json()
                        items = []
                        if isinstance(data, dict):
                            if "value" in data and isinstance(data["value"], list):
                                items = data["value"]
                            elif "assignments" in data and isinstance(data["assignments"], list):
                                items = data["assignments"]
                        elif isinstance(data, list):
                            items = data

                        for item in items:
                            if isinstance(item, dict) and ("displayName" in item or "title" in item):
                                intercepted_items.append(item)
                                last_intercept_time[0] = time.time()
                except Exception:
                    pass

            page.on("response", handle_response)

            # 2. Navigiere zu Teams
            try:
                page.goto(TEAMS_BASE_URL, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass

            # Prüfe, ob wir dauerhaft auf einer echten Login-Seite gelandet sind
            # (kurze SSO-Token-Redirects über login.microsoftonline.com abwarten)
            if "login.microsoftonline.com" in page.url or "bridge/fido" in page.url:
                is_real_login = False
                wait_sso = time.time()
                while time.time() - wait_sso < 8.0:
                    if is_shutting_down():
                        break
                    curr_url = page.url.lower()
                    if "login.microsoftonline.com" not in curr_url and "bridge/fido" not in curr_url and ("teams.cloud.microsoft" in curr_url or "teams.microsoft.com" in curr_url or "teams.live.com" in curr_url):
                        is_real_login = False
                        break
                    try:
                        login_inputs = page.locator('input[type="email"]:visible, input[type="password"]:visible, input#i0116:visible, input#i0118:visible')
                        if login_inputs.count() > 0 and ("login.microsoftonline.com" in curr_url or "login.live.com" in curr_url):
                            is_real_login = True
                            break
                    except Exception:
                        pass
                    page.wait_for_timeout(500)

                if is_real_login:
                    try:
                        with open(TEAMS_STATUS_FILE, "w", encoding="utf-8") as f:
                            json.dump({"configured": False}, f)
                    except Exception:
                        pass
                    ctx.close()
                    return []

            page.wait_for_timeout(3500)

            # 3. Klicke auf die Aufgaben-App (Assignments / Zuweisungen)
            assign_selectors = (
                'button[data-tid="66aeee93-507d-479a-a3ef-8f494af43945"], '
                'button[aria-label*="Zuweisungen" i], '
                'button[aria-label*="Assignment" i], '
                'button[aria-label*="Aufgaben" i], '
                '[data-tid*="app-bar-item-66aeee93"]'
            )
            clicked_assign = False
            try:
                assign_btn = page.locator(assign_selectors).first
                if assign_btn.count() > 0:
                    assign_btn.click()
                    clicked_assign = True
                else:
                    # Prüfe, ob Aufgaben unter "Weitere Apps" / "..." versteckt ist
                    more_btn = page.locator('button[aria-label*="Weitere Apps" i], button[aria-label*="More added apps" i], button[data-tid="more-apps-button"], button[aria-label*="Apps" i]').first
                    if more_btn.count() > 0:
                        more_btn.click()
                        page.wait_for_timeout(500)
                        sub_assign = page.locator(assign_selectors).first
                        if sub_assign.count() > 0:
                            sub_assign.click()
                            clicked_assign = True
            except Exception:
                pass

            if not clicked_assign:
                # Fallback: Direktnavigation zur Assignments-App im Schul-Tenant
                try:
                    if "teams.live.com" not in page.url.lower():
                        page.goto(f"{TEAMS_BASE_URL}/_#/apps/66aeee93-507d-479a-a3ef-8f494af43945/sections/classroom", wait_until="domcontentloaded", timeout=10000)
                except Exception:
                    pass

            def check_and_confirm_dialogs():
                for c in [page] + page.frames:
                    try:
                        for sel in [
                            'button:has-text("Fortfahren")',
                            'button:has-text("Continue")',
                            'button:has-text("Weiter")',
                            'button:has-text("Zulassen")',
                            'button:has-text("Use the web app instead")',
                            'a:has-text("Use the web app instead")',
                        ]:
                            b = c.locator(sel).first
                            if b.count() > 0 and b.is_visible():
                                b.click(force=True, timeout=1000)
                                return True
                    except Exception:
                        pass
                return False

            # Dynamische Überprüfung von Berechtigungs-Dialogen ("Fortfahren", "Continue") und Laden der Tabs
            for _ in range(15):  # Bis zu 3.0 Sekunden dynamisch warten
                if is_shutting_down():
                    break
                page.wait_for_timeout(200)
                check_and_confirm_dialogs()
                # Prüfen, ob die Tabs bereits bereitstehen
                if any(f.locator('button[role="tab"]').count() > 0 for f in page.frames):
                    break

            # 4. Klicke auf den Tab "Past due" / "Überfällig", um auch überfällige Aufgaben zu laden
            for c in [page] + page.frames:
                try:
                    pd_tab = c.locator('button[role="tab"]:has-text("Past due"), button[role="tab"]:has-text("Überfällig"), button[role="tab"]:has-text("Vergangen")').first
                    if pd_tab.count() > 0:
                        pd_tab.click(force=True, timeout=2000)
                        page.wait_for_timeout(800)
                        break
                except Exception:
                    pass

            # 5. Klicke auf den Tab "Erledigt" / "Completed" / "Abgeschlossen", um auch erledigte Aufgaben abzurufen
            comp_selector = (
                'button:has-text("Erledigt"), button:has-text("Completed"), button:has-text("Abgeschlossen"), '
                '[role="tab"]:has-text("Erledigt"), [role="tab"]:has-text("Completed"), [role="tab"]:has-text("Abgeschlossen"), '
                '[data-tid*="completed" i], [data-tid*="completed-tab" i], a:has-text("Erledigt"), a:has-text("Completed")'
            )
            for c in [page] + page.frames:
                try:
                    comp_btn = c.locator(comp_selector).first
                    if comp_btn.count() > 0:
                        comp_btn.click(force=True, timeout=2000)
                        page.wait_for_timeout(800)
                        break
                except Exception:
                    pass

            # Reaktiv warten auf abgefangene API-Antworten (mit Beruhigungszeit für Nachzügler-Batches)
            start_wait = time.time()
            retry_clicked = False
            while time.time() - start_wait < 3.5:
                if is_shutting_down():
                    break
                if intercepted_items and (time.time() - last_intercept_time[0] >= 0.8):
                    break

                # Dialoge (z.B. Fortfahren) oder Retry-Button anklicken falls vorhanden
                if time.time() - start_wait > 1.2:
                    check_and_confirm_dialogs()

                if not retry_clicked and (time.time() - start_wait > 2.0):
                    for c in [page] + page.frames:
                        try:
                            rb = c.locator('button:has-text("Retry"), button:has-text("Wiederholen"), #error-action').first
                            if rb.count() > 0:
                                rb.click(timeout=1000, force=True)
                                retry_clicked = True
                                break
                        except Exception:
                            pass

                page.wait_for_timeout(150)

            # 6. Klassen-Namen aus den aktuell gerenderten Aufgabenkarten auflösen
            class_id_map = {}
            all_containers = [page]
            for f in page.frames:
                all_containers.append(f)

            def scan_cards_for_classes():
                for container in all_containers:
                    try:
                        cards = container.query_selector_all('div[class*="assignmentListCard"], div[class*="fui-Card"], [role="listitem"], [data-tid*="card"], div[class*="card"]')
                        for c in cards:
                            try:
                                lines = [l.strip() for l in c.inner_text().split("\n") if l.strip()]
                                for item in intercepted_items:
                                    t_name = item.get("displayName") or item.get("title")
                                    if t_name and t_name in lines:
                                        cid = item.get("classId")
                                        if cid and cid not in class_id_map:
                                            found_class = None
                                            for l in lines:
                                                if any(kw in l.lower() for kw in ["ufw", "swp", "sew", "nw", "syb", "amec", "mathe", "deutsch", "englisch", "bet", "jg", "3ahwii"]):
                                                    found_class = l
                                                    break
                                                elif not found_class and l != t_name and not any(kw in l.lower() for kw in ["fällig", "due", "uhr", "punkte", "points", "vergangen", "past", "view", "zugewiesen", "abgegeben", "übermittelt", "today", "heute"]):
                                                    found_class = l
                                            if found_class:
                                                class_id_map[cid] = found_class
                            except Exception:
                                pass
                    except Exception:
                        pass

            scan_cards_for_classes()

            # 6. Aufgaben aus abgefangenen API-Daten deduplizieren und generieren
            items_by_id = {}
            for item in intercepted_items:
                raw_id = item.get("id") or str(abs(hash(item.get("displayName", ""))))
                # Erledigte Versionen überschreiben ggf. offene Vorgänger
                if raw_id not in items_by_id or item.get("isCompleted") or item.get("allTurnedIn"):
                    items_by_id[raw_id] = item

            for item in items_by_id.values():
                raw_id = item.get("id") or str(abs(hash(item.get("displayName", ""))))
                tid = f"teams_{raw_id}"
                if tid in seen_ids:
                    continue
                seen_ids.add(tid)

                title = item.get("displayName") or item.get("title") or "Teams Aufgabe"
                due_iso = item.get("dueDateTime") or item.get("dueDateTimeUtc") or ""
                due_str = parse_teams_due_date(due_iso) if due_iso else "Keine Frist"
                due_ts = None
                is_past = False
                if due_iso:
                    try:
                        import datetime
                        dt_due = datetime.datetime.fromisoformat(due_iso.replace("Z", "+00:00"))
                        due_ts = dt_due.timestamp()
                        is_past = dt_due.astimezone() < datetime.datetime.now().astimezone()
                    except Exception:
                        pass

                cid = item.get("classId")
                class_name = class_id_map.get(cid) or item.get("classDisplayName") or item.get("className")
                if not class_name:
                    lower_title = title.lower()
                    if any(k in lower_title for k in ["ufw", "unternehmensführung"]):
                        class_name = "UFW"
                    elif any(k in lower_title for k in ["deutsch", "erörterung", "aufsatz", "sa ", "schularbeit"]):
                        class_name = "Deutsch"
                    elif any(k in lower_title for k in ["englisch", "english", "branding", "homework"]):
                        class_name = "Englisch"
                    elif any(k in lower_title for k in ["mathe", "mathematik", "vektoren", "integral"]):
                        class_name = "AMEC"
                    else:
                        class_name = "UFW"
                subject = normalize_subject_name(class_name)

                status_raw = item.get("status", "").lower()
                subs = item.get("submissions") or []
                sub_status = subs[0].get("status", "").lower() if subs else ""
                is_comp = bool(item.get("isCompleted")) or bool(item.get("allTurnedIn")) or ("submitted" in sub_status) or ("turned" in sub_status) or ("returned" in sub_status) or ("completed" in status_raw)

                if is_comp:
                    if "returned" in sub_status or item.get("statusreason") == "returned":
                        status = "bewertet"
                        status_display = "Zurückgegeben"
                    else:
                        status = "abgegeben"
                        status_display = "Abgegeben"
                elif is_past or "gestern" in due_str.lower() or "vor " in due_str.lower() or "überfällig" in due_str.lower():
                    status = "ueberfaellig"
                    status_display = "Überfällig"
                else:
                    status = "offen"
                    status_display = "Zugewiesen"

                web_url = item.get("webUrl") or f"{TEAMS_ASSIGNMENTS_URL}?context=%7B%22subEntityId%22%3A%22assignment_{raw_id}%22%7D"

                # Prüfen, ob API-Payload bereits Anweisungen oder Anhänge enthält
                task_description = ""
                task_attachments = []
                details_loaded = False

                if item.get("instructions"):
                    task_description = format_teams_description(item.get("instructions"))
                    if task_description.strip():
                        details_loaded = True

                if item.get("resources"):
                    task_attachments = extract_teams_attachments(item.get("resources"), default_url=web_url)
                    if task_attachments:
                        details_loaded = True

                tasks.append(
                    Task(
                        id=tid,
                        platform="teams",
                        course=subject,
                        course_full=class_name,
                        title=title,
                        due_date_str=due_str,
                        due_timestamp=due_ts,
                        status=status,
                        status_display=status_display,
                        url=web_url,
                        class_id=cid,
                        description=task_description,
                        attachments=task_attachments,
                        details_loaded=details_loaded,
                        teacher=extract_teacher(course_full=class_name, subject=subject, title=title, description=task_description),
                    )
                )

            # 6. Fallback: DOM-Scraping falls keine REST-Payloads direkt abgefangen wurden
            if not tasks:
                for container in all_containers:
                    try:
                        cards = container.query_selector_all('div[class*="assignmentListCard"], div[class*="fui-Card"], [role="listitem"], [data-tid*="card"], div[class*="card"]')
                        for card in cards:
                            try:
                                card_text = card.inner_text().strip()
                                if not card_text or len(card_text) < 5:
                                    continue

                                lines = [l.strip() for l in card_text.split("\n") if l.strip()]
                                if len(lines) >= 2:
                                    raw_title = lines[0]
                                    raw_meta = " ".join(lines[1:])

                                    due_match = re.search(r'(?:fällig|due)\s*(?:am)?\s*([^\n\r,]+(?:\d{1,2}:\d{2})?)', raw_meta, re.IGNORECASE)
                                    due_str = due_match.group(0).strip() if due_match else "Keine Frist"

                                    subject = normalize_subject_name(raw_meta)
                                    tid = f"teams_{abs(hash(raw_title + raw_meta))}"

                                    if tid not in seen_ids:
                                        seen_ids.add(tid)
                                        tasks.append(
                                            Task(
                                                id=tid,
                                                platform="teams",
                                                course=subject,
                                                course_full=raw_meta[:40],
                                                title=raw_title,
                                                due_date_str=due_str,
                                                status="offen",
                                                status_display="Zugewiesen",
                                                url=TEAMS_ASSIGNMENTS_URL,
                                                details_loaded=False,
                                                teacher=extract_teacher(course_full=raw_meta[:40], subject=subject, title=raw_title),
                                            )
                                        )
                            except Exception:
                                pass
                    except Exception:
                        pass
    except Exception as e:
        err_msg = str(e).lower()
        if not is_shutting_down() and "target page, context or browser has been closed" not in err_msg and "targetclosederror" not in type(e).__name__.lower():
            print(f"Error fetching Teams assignments: {e}", file=sys.stderr)

    return tasks


def fetch_teams_task_details(task: Task) -> Task:
    """
    Lädt die Detailbeschreibung (Angabe), Status und Anhänge einer Teams-Aufgabe.
    """
    if task.details_loaded:
        return task

    if not os.path.exists(TEAMS_PROFILE_DIR):
        return task

    try:
        with sync_playwright() as p, open_teams_context(
            p,
            user_data_dir=TEAMS_PROFILE_DIR,
            headless=True,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"] + CHROMIUM_CACHE_ARGS
        ) as ctx:
            if not ctx:
                return task
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            details_api_data = {}

            def handle_details_response(response):
                try:
                    u = response.url.lower()
                    if ("assignments" in u or "work" in u) and "json" in (response.headers.get("content-type") or ""):
                        data = response.json()
                        items = []
                        if isinstance(data, dict):
                            if "instructions" in data or "resources" in data:
                                items = [data]
                            elif "value" in data and isinstance(data["value"], list):
                                items = data["value"]
                            elif "assignments" in data and isinstance(data["assignments"], list):
                                items = data["assignments"]
                        elif isinstance(data, list):
                            items = data

                        for it in items:
                            if not isinstance(it, dict):
                                continue
                            it_id = str(it.get("id", ""))
                            it_title = it.get("displayName") or it.get("title") or ""
                            if it_id and (it_id in task.id or (it_title and it_title.lower() == task.title.lower())):
                                details_api_data.update(it)
                                break
                            elif not details_api_data and ("instructions" in it or "resources" in it):
                                details_api_data.update(it)
                except Exception:
                    pass

            page.on("response", handle_details_response)

            # Navigiere zur Aufgabenansicht
            target_url = task.url if task.url and "http" in task.url else TEAMS_ASSIGNMENTS_URL
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
            except Exception:
                pass

            # Falls auf Teams Hauptseite: Assignments anklicken
            try:
                assign_btn = page.locator('button[data-tid="66aeee93-507d-479a-a3ef-8f494af43945"], button[aria-label*="Zuweisungen" i], button[aria-label*="Assignment" i], button[aria-label*="Aufgaben" i]').first
                assign_btn.wait_for(state="visible", timeout=8000)
                assign_btn.click(timeout=2500, force=True)
            except Exception:
                pass

            # Klicke auf Web-App falls Launcher erscheint (reaktiv)
            start_launcher = time.time()
            while time.time() - start_launcher < 3.0:
                if details_api_data.get("instructions") or any("assignments.edu.cloud.microsoft" in f.url for f in page.frames):
                    break
                btn = page.query_selector(
                    'a:has-text("web app"), button:has-text("web app"), a:has-text("Web-App"), button:has-text("Web-App"), [data-tid*="use-web-app"]'
                )
                if btn:
                    try:
                        btn.click(timeout=1500, force=True)
                    except Exception:
                        pass
                    break
                page.wait_for_timeout(200)

            # Reaktiv warten auf das Laden des Aufgaben-Frames oder API-Antworten (statt statischem wait_for_timeout(7000))
            found_frame = None
            start_frame_wait = time.time()
            while time.time() - start_frame_wait < 7.0:
                if details_api_data.get("instructions"):
                    break
                for f in page.frames:
                    if "assignments.edu.cloud.microsoft" in f.url:
                        found_frame = f
                        break
                if found_frame:
                    if found_frame.query_selector(
                        'button:has-text("Turn in"), button:has-text("Abgeben"), [data-tid*="submission"], [role="listitem"], [data-tid*="card"], div[class*="card"], div[class*="assignment-details"]'
                    ):
                        break
                    page.wait_for_timeout(250)

            # Im Assignments-Frame nach der Karte suchen und anklicken falls noch nicht in Detailansicht
            if found_frame and not details_api_data.get("instructions"):
                if not found_frame.query_selector('button:has-text("Turn in"), button:has-text("Abgeben"), [data-tid*="submission"]'):
                    cards = found_frame.query_selector_all('[role="listitem"], [data-tid*="card"], div[class*="card"]')
                    card_found = False
                    for c in cards:
                        if task.title.lower() in c.inner_text().lower():
                            c.click(timeout=2000, force=True)
                            card_found = True
                            # Reaktiv warten statt statischem wait_for_timeout(4000)
                            click_t = time.time()
                            while time.time() - click_t < 4.0:
                                if details_api_data.get("instructions"):
                                    break
                                if found_frame.query_selector(
                                    'button:has-text("Turn in"), button:has-text("Abgeben"), [data-tid*="submission"], div[class*="assignment-details-description"], [data-tid*="instruction"]'
                                ):
                                    break
                                page.wait_for_timeout(200)
                            break

                    # Falls nicht in der aktiven Liste gefunden, 'Vergangen' / 'Past due' aufklappen
                    if not card_found:
                        past_btn = found_frame.query_selector(
                            'button:has-text("past due"), button:has-text("Vergangen"), button:has-text("Past due"), [data-tid*="past-due"]'
                        )
                        if past_btn:
                            try:
                                past_btn.click(timeout=1500, force=True)
                                past_t = time.time()
                                while time.time() - past_t < 2.5:
                                    cards = found_frame.query_selector_all('[role="listitem"], [data-tid*="card"], div[class*="card"]')
                                    if any(task.title.lower() in c.inner_text().lower() for c in cards):
                                        break
                                    page.wait_for_timeout(200)

                                for c in found_frame.query_selector_all('[role="listitem"], [data-tid*="card"], div[class*="card"]'):
                                    if task.title.lower() in c.inner_text().lower():
                                        c.click(timeout=2000, force=True)
                                        click_t = time.time()
                                        while time.time() - click_t < 4.0:
                                            if details_api_data.get("instructions"):
                                                break
                                            if found_frame.query_selector(
                                                'button:has-text("Turn in"), button:has-text("Abgeben"), [data-tid*="submission"], div[class*="assignment-details-description"], [data-tid*="instruction"]'
                                            ):
                                                break
                                            page.wait_for_timeout(200)
                                        break
                            except Exception:
                                pass

            # 1. Anweisungen / Beschreibung ermitteln
            description_text = ""
            if details_api_data.get("instructions"):
                description_text = format_teams_description(details_api_data["instructions"])

            if not description_text and found_frame:
                try:
                    desc_el = found_frame.query_selector(
                        'div[class*="assignment-details-description"], div[data-tid*="instruction"], .assignment-instruction, [aria-label*="Anweisungen"], [aria-label*="Instructions"], div[class*="instructions"]'
                    )
                    if desc_el:
                        raw_html_or_text = desc_el.evaluate('''el => {
                            const clone = el.cloneNode(true);
                            const imgs = clone.querySelectorAll("img");
                            imgs.forEach(img => {
                                const span = document.createElement("span");
                                span.textContent = "\\n[Bild]\\n";
                                img.parentNode.replaceChild(span, img);
                            });
                            return clone.innerText.trim();
                        }''')
                        description_text = format_teams_description(raw_html_or_text)
                except Exception:
                    pass

            # Fallback falls in der Detailansicht ein Bild eingebettet ist, aber kein Text vorhanden war
            if not description_text and found_frame:
                try:
                    imgs = found_frame.query_selector_all(
                        'div[class*="assignment-details-description"] img, div[class*="assignment-details-left-pane"] img, div[class*="assignment-details-container"] img'
                    )
                    if imgs:
                        description_text = "[Bild]"
                except Exception:
                    pass

            if not description_text:
                description_text = "Keine gesonderte Beschreibung in Teams hinterlegt.\nAbgabe und Details können direkt über den Abgabelink in Microsoft Teams geöffnet werden."

            task.description = description_text

            # 2. Anhänge / Referenzmaterialien ermitteln
            attachments: List[TaskAttachment] = []
            if details_api_data.get("resources"):
                attachments = extract_teams_attachments(details_api_data["resources"], default_url=task.url)

            if not attachments and found_frame:
                try:
                    file_elements = found_frame.query_selector_all(
                        'div[data-tid*="reference-material"], button[aria-label*="Anhang"], a[download], [data-tid*="resource"]'
                    )
                    for fel in file_elements:
                        fname = fel.inner_text().strip()
                        if fname and len(fname) > 2 and "\n" not in fname:
                            attachments.append(TaskAttachment(name=fname, url=task.url))
                except Exception:
                    pass

            task.attachments = attachments
            task.details_loaded = True
    except Exception as e:
        err_msg = str(e).lower()
        if not is_shutting_down() and "target page, context or browser has been closed" not in err_msg and "targetclosederror" not in type(e).__name__.lower():
            print(f"Error loading Teams task details: {e}", file=sys.stderr)

    return task


def download_teams_attachments(task: Task, dest_dir: Optional[str] = None) -> List[str]:
    """
    Speichert die Aufgabenangabe als angabe.md und lädt Referenzdateien aus Teams herunter.
    """
    if not dest_dir:
        dest_dir = get_task_download_dir(task.course, task.title)

    os.makedirs(dest_dir, exist_ok=True)
    task.download_dir = dest_dir
    downloaded_files: List[str] = []

    # 1. Angabe als Markdown-Datei speichern
    angabe_file = os.path.join(dest_dir, "angabe.md")
    try:
        with open(angabe_file, "w", encoding="utf-8") as f:
            f.write(f"# {task.title}\n\n")
            f.write(f"**Subject:** {task.course} ({task.course_full})\n")
            f.write(f"**Platform:** Microsoft Teams\n")
            f.write(f"**Due Date:** {task.due_date_str}\n")
            f.write(f"**Status:** {task.status_display}\n")
            f.write(f"**Submission Link:** [{task.url}]({task.url})\n\n")
            f.write("---\n\n")
            f.write("## Assignment Description\n\n")
            f.write(task.description or "No description provided.\n")
            if task.attachments:
                f.write("\n\n---\n## Attachments\n\n")
                for att in task.attachments:
                    f.write(f"- {att.name}\n")
        downloaded_files.append(angabe_file)
    except Exception as e:
        print(f"Error writing angabe.md: {e}", file=sys.stderr)

    return downloaded_files
