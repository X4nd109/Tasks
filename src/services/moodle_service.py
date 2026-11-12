"""
moodle_service.py - Service zum Abrufen von Moodle-Aufgaben, Details und Dateidownloads.
"""

import html
import json
import os
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
import requests
from playwright.sync_api import sync_playwright


from config import (
    CONFIG_DIR,
    MOODLE_BASE_URL,
    DOWNLOADS_DIR,
    get_task_download_dir,
    normalize_subject_name,
    sanitize_filename,
    extract_teacher,
    load_full_school_config,
)
from auth import (
    get_saved_moodle_cookies,
    save_moodle_cookies,
    get_existing_moodle_credentials,
    login_moodle_with_creds,
    login_moodle_direct,
)
from models import Task, TaskAttachment


class HTMLToMarkdown(HTMLParser):
    """Robuster HTML zu Markdown Konverter ohne externe Abhängigkeiten."""
    def __init__(self):
        super().__init__()
        self.result = []
        self.href = None
        self.in_list_item = False
        self.inside_image = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attr_dict = dict(attrs)
        if tag in ["h1", "h2", "h3", "h4"]:
            self.result.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "p":
            self.result.append("\n\n")
        elif tag == "br":
            self.result.append("\n")
        elif tag == "li":
            self.result.append("\n* ")
            self.in_list_item = True
        elif tag in ["strong", "b"]:
            self.result.append("**")
        elif tag in ["em", "i"]:
            self.result.append("*")
        elif tag == "code":
            self.result.append("`")
        elif tag == "pre":
            self.result.append("\n```\n")
        elif tag == "a":
            self.href = attr_dict.get("href")
            self.inside_image = False
            self.result.append("[")
        elif tag == "img":
            # Falls innerhalb eines Links <a>, entfernen wir das öffnende '['
            if self.href and self.result and self.result[-1] == "[":
                self.result.pop()
            self.result.append("[Bild]")
            self.inside_image = True

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ["h1", "h2", "h3", "h4"]:
            self.result.append("\n")
        elif tag == "p":
            self.result.append("\n")
        elif tag == "li":
            self.in_list_item = False
        elif tag in ["strong", "b"]:
            self.result.append("**")
        elif tag in ["em", "i"]:
            self.result.append("*")
        elif tag == "code":
            self.result.append("`")
        elif tag == "pre":
            self.result.append("\n```\n")
        elif tag == "a":
            if not self.inside_image:
                if self.href:
                    self.result.append(f"]({self.href})")
                else:
                    self.result.append("]")
            self.href = None
            self.inside_image = False

    def handle_data(self, data):
        self.result.append(data)

    def get_markdown(self) -> str:
        raw = "".join(self.result)
        # Ersetze markdown-Bilder ![...](...) oder [Bild](...) durch einfach [Bild]
        raw = re.sub(r"!\[.*?\]\(.*?\)", "[Bild]", raw)
        raw = re.sub(r"\[\s*\[Bild\]\s*\]\(.*?\)", "[Bild]", raw)
        raw = re.sub(r"\[Bild\]\(.*?\)", "[Bild]", raw)
        lines = [line.rstrip() for line in raw.split("\n")]
        text = "\n".join(lines)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text


def html_to_markdown(html_content: str) -> str:
    if not html_content:
        return ""
    parser = HTMLToMarkdown()
    parser.feed(html_content)
    return parser.get_markdown()


def check_moodle_task_status_http(session: requests.Session, url: str) -> Tuple[str, str]:
    """
    Prüft blitzschnell über HTTP den tatsächlichen Abgabestatus einer Moodle-Aufgabe.
    Gibt (status, status_display) zurück:
      - ("abgegeben", "Zur Bewertung abgegeben")
      - ("offen", "Keine Abgabe")
    """
    clean_url = re.sub(r"&action=\w+", "", url)
    try:
        resp = session.get(clean_url, timeout=8)
        txt = resp.text

        # 1. Moodle CSS-Klasse für erfolgreiche Abgabe
        if re.search(r'class="[^"]*submissionstatussubmitted[^"]*"', txt, re.IGNORECASE):
            m = re.search(r'class="[^"]*submissionstatussubmitted[^"]*"[^>]*>(.*?)</td>', txt, re.IGNORECASE | re.DOTALL)
            status_text = re.sub(r'<[^>]+>', '', m.group(1)).strip() if m else "Zur Bewertung abgegeben"
            return "abgegeben", status_text

        # 2. Prüfe Moodle Tabelle auf Abgabestatus
        m_table = re.search(r'<table class="generaltable[^"]*">(.*?)</table>', txt, re.DOTALL)
        if m_table:
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', m_table.group(1), re.DOTALL)
            for r in rows:
                th_m = re.search(r'<th[^>]*>(.*?)</th>', r, re.DOTALL)
                td_m = re.search(r'<td[^>]*>(.*?)</td>', r, re.DOTALL)
                if th_m and td_m:
                    th_txt = re.sub(r'<[^>]+>', '', th_m.group(1)).strip().lower()
                    td_txt = re.sub(r'<[^>]+>', '', td_m.group(1)).strip()
                    if "abgabestatus" in th_txt or "submission status" in th_txt:
                        td_lower = td_txt.lower()
                        if any(neg in td_lower for neg in ["keine", "kein", "nichts", "nicht", "not"]):
                            disp = "noch offen" if ("nichts abgegeben" in td_lower or "für diese aufgabe" in td_lower) else td_txt
                            return "offen", disp
                        elif any(kw in td_lower for kw in ["abgegeben", "submitted"]):
                            return "abgegeben", td_txt
                        else:
                            return "offen", td_txt

        # 3. Textbaustein-Fallback
        if "Zur Bewertung abgegeben" in txt or "Abgegeben zur Bewertung" in txt:
            return "abgegeben", "Zur Bewertung abgegeben"
        if any(neg in txt for neg in ["Bisher wurden keine Aufgaben abgegeben", "nichts abgegeben", "Keine Abgabe"]):
            return "offen", "Keine Abgabe"
    except Exception:
        pass

    return "offen", "Offen"


def ensure_moodle_session(context, page) -> bool:
    """Stellt sicher, dass der Browser in Moodle angemeldet ist."""
    cookies = get_saved_moodle_cookies()
    if cookies:
        try:
            context.add_cookies(cookies)
            page.goto(f"{MOODLE_BASE_URL}/my/", wait_until="domcontentloaded", timeout=12000)
            page.wait_for_timeout(1000)
            if "/login/index.php" not in page.url and not page.query_selector("form#login, #loginbtn"):
                return True
        except Exception:
            pass

    # Automatisch mit hinterlegten Zugangsdaten anmelden, falls vorhanden
    _, creds = get_existing_moodle_credentials()
    if creds and creds.get("username") and creds.get("password"):
        return login_moodle_with_creds(page, context, creds["username"], creds["password"])

    return False


def parse_moodle_calendar_events(html_text: str, base_url: str = MOODLE_BASE_URL) -> List[dict]:
    """
    Parst anstehende Abgaben aus dem HTML der Moodle-Kalenderansicht (/calendar/view.php?view=upcoming).
    Gibt eine Liste von Dicts mit {url, id, title, date_str, course_full} zurück.
    """
    if not html_text:
        return []

    chunks = re.split(r'<div[^>]*data-type="event"', html_text)[1:]
    if not chunks:
        chunks = re.split(r'<div[^>]*class="[^"]*\bevent\b[^"]*"', html_text)[1:]

    events = []
    seen_urls = set()

    for ev_html in chunks:
        # 1. Abgabelink ermitteln (/mod/assign/view.php?id=...)
        m_link = re.search(r'href="([^"]*/mod/assign/view\.php\?id=\d+[^"]*)"', ev_html)
        if not m_link:
            m_link = re.search(r'<a[^>]*class="[^"]*card-link[^"]*"[^>]*href="([^"]+)"', ev_html)
            if not m_link or "/mod/assign/view.php" not in m_link.group(1):
                continue

        raw_link = m_link.group(1)
        clean_link = html.unescape(raw_link)
        clean_link = urllib.parse.urljoin(base_url, clean_link)
        clean_link = re.sub(r"[?&]action=\w+", "", clean_link)

        if clean_link in seen_urls:
            continue
        seen_urls.add(clean_link)

        # 2. Titel ermitteln (.name oder data-event-title)
        m_title = re.search(r'class="name[^"]*">(.*?)</h3>', ev_html, re.DOTALL)
        if m_title:
            title = html.unescape(re.sub(r'<[^>]+>', '', m_title.group(1))).strip()
        else:
            m_t2 = re.search(r'data-event-title="([^"]+)"', ev_html)
            title = html.unescape(m_t2.group(1)) if m_t2 else ""

        title = re.sub(r"\s+ist fällig\.?", "", title, flags=re.IGNORECASE).strip()
        title = re.sub(r"\s+is due\.?", "", title, flags=re.IGNORECASE).strip()

        # 3. Fälligkeitsdatum ermitteln (.date)
        m_date = re.search(r'class="date[^"]*"[^>]*>(.*?)</span>', ev_html, re.DOTALL)
        if not m_date:
            m_date = re.search(r'class="date[^"]*"[^>]*>(.*?)</div>', ev_html, re.DOTALL)

        if m_date:
            date_str = html.unescape(re.sub(r'<[^>]+>', '', m_date.group(1))).strip()
            date_str = " ".join(date_str.split())
        else:
            date_str = "Keine Frist"

        # 4. Kursname ermitteln (Link zu /course/view.php)
        m_course = re.search(r'<a[^>]*href="[^"]*/course/view\.php\?id=\d+"[^>]*>(.*?)</a>', ev_html, re.DOTALL)
        course_full = html.unescape(re.sub(r'<[^>]+>', '', m_course.group(1))).strip() if m_course else ""

        # 5. ID ermitteln
        m_id = re.search(r"id=(\d+)", clean_link)
        task_id = f"moodle_{m_id.group(1)}" if m_id else f"moodle_{abs(hash(clean_link))}"

        events.append({
            "id": task_id,
            "url": clean_link,
            "title": title,
            "date_str": date_str or "Keine Frist",
            "course_full": course_full,
        })

    return events


def parse_moodle_assign_index(html_text: str, course_name: str = "", base_url: str = MOODLE_BASE_URL) -> List[dict]:
    """
    Parst die Aufgabenübersicht eines Moodle-Kurses (/mod/assign/index.php?id=...).
    Gibt eine Liste von Dicts mit {url, id, title, due_date, status_display, status, course_full} zurück.
    """
    if not html_text:
        return []

    assigns = []
    seen_urls = set()

    # Dynamische Ermittlung der Spaltenindizes aus thead
    thead_match = re.search(r'<thead[^>]*>(.*?)</thead>', html_text, re.DOTALL)
    due_col_idx = None
    status_col_idx = None
    if thead_match:
        th_cells = re.findall(r'<th[^>]*>(.*?)</th>', thead_match.group(1), re.DOTALL)
        headers = [html.unescape(re.sub(r'<[^>]+>', '', h)).strip().lower() for h in th_cells]
        for idx, h in enumerate(headers):
            if any(kw in h for kw in ["fällig", "due"]):
                due_col_idx = idx
            elif any(kw in h for kw in ["abgabe", "submission", "einreichung"]):
                status_col_idx = idx
            elif "status" in h and status_col_idx is None:
                status_col_idx = idx

    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html_text, re.DOTALL)
    for row in rows:
        m_a = re.search(r'<a[^>]*href="([^"]*/mod/assign/view\.php\?id=\d+[^"]*)"[^>]*>(.*?)</a>', row, re.DOTALL)
        if not m_a:
            continue

        raw_href = m_a.group(1)
        clean_href = html.unescape(raw_href)
        clean_href = urllib.parse.urljoin(base_url, clean_href)
        clean_href = re.sub(r"[?&]action=\w+", "", clean_href)

        if clean_href in seen_urls:
            continue
        seen_urls.add(clean_href)

        title = html.unescape(re.sub(r'<[^>]+>', '', m_a.group(2))).strip()
        title = title.split("\n")[0].strip()

        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
        clean_cells = [html.unescape(re.sub(r'<[^>]+>', '', c)).strip() for c in cells]

        # Fälligkeit ermitteln
        if due_col_idx is not None and due_col_idx < len(clean_cells):
            due_date = clean_cells[due_col_idx]
        elif len(clean_cells) > 2 and any(kw in clean_cells[1].lower() for kw in ["jan", "feb", "mär", "apr", "mai", "jun", "jul", "aug", "sep", "okt", "nov", "dez", "montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"]):
            due_date = clean_cells[1]
        else:
            due_date = "Keine Frist"

        # Falls Spaltenverschiebung "Keine Abgabe" oder Bewertung in die Frist gesteckt hätte
        if any(kw in due_date.lower() for kw in ["abgabe", "submitted", "bewertung", "punkte", "einreichung", "not submitted", "grading"]):
            due_date = "Keine Frist"

        # Abgabestatus ermitteln
        if status_col_idx is not None and status_col_idx < len(clean_cells):
            sub_status = clean_cells[status_col_idx]
        else:
            sub_status = clean_cells[3] if len(clean_cells) > 3 else (clean_cells[2] if len(clean_cells) > 2 else "Unbekannt")

        if sub_status in ["-", "", "Unbekannt"]:
            for c in clean_cells:
                if any(kw in c.lower() for kw in ["abgegeben", "submitted"]):
                    sub_status = c
                    break

        m_id = re.search(r"id=(\d+)", clean_href)
        task_id = f"moodle_{m_id.group(1)}" if m_id else f"moodle_{abs(hash(clean_href))}"

        stat = "abgegeben" if any(kw in sub_status.lower() for kw in ["abgegeben", "submitted"]) else "offen"

        assigns.append({
            "id": task_id,
            "url": clean_href,
            "title": title,
            "due_date": due_date or "Keine Frist",
            "status_display": sub_status,
            "status": stat,
            "course_full": course_name,
        })

    return assigns


def fetch_moodle_tasks_http(deep_scan: bool = False) -> List[Task]:
    """
    Ruft alle Moodle-Aufgaben blitzschnell über HTTP ab (~1.5s).
    1. Schneller Scan über den Kalender (/calendar/view.php?view=upcoming).
    2. Falls deep_scan=True oder keine Kalendertermine gefunden wurden:
       Paralleler Abruf der Aufgabenindexseiten aller Kurse über HTTP.
    3. Parallele HTTP-Statusprüfung aller gefundenen Aufgaben.
    Wirft RuntimeError bei ungültigen Cookies oder Netzwerkfehlern (für Fallback).
    """
    cookies = get_saved_moodle_cookies()
    if not cookies:
        raise RuntimeError("Keine gespeicherten Moodle-Cookies vorhanden.")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    moodle_netloc = urllib.parse.urlparse(MOODLE_BASE_URL).netloc
    for c in cookies:
        session.cookies.set(c["name"], c["value"], domain=c.get("domain", moodle_netloc))

    tasks: List[Task] = []
    seen_urls = set()

    # 1. Kalender-Scan über HTTP
    cal_url = f"{MOODLE_BASE_URL}/calendar/view.php?view=upcoming"
    resp = session.get(cal_url, timeout=12)

    # Prüfen, ob Session abgelaufen oder Login-Weiterleitung stattfand
    if resp.status_code != 200 or "/login/index.php" in resp.url or "<form id=\"login\"" in resp.text or "id=\"loginbtn\"" in resp.text:
        raise RuntimeError("Moodle-Sitzung abgelaufen oder ungültig.")

    if resp.encoding is None:
        resp.encoding = resp.apparent_encoding or "utf-8"

    cal_events = parse_moodle_calendar_events(resp.text, base_url=MOODLE_BASE_URL)
    for ev in cal_events:
        link = ev["url"]
        if link in seen_urls:
            continue
        seen_urls.add(link)

        c_full = ev["course_full"]
        title = ev["title"]
        subject = normalize_subject_name(c_full or title)

        tasks.append(
            Task(
                id=ev["id"],
                platform="moodle",
                course=subject,
                course_full=c_full,
                title=title,
                due_date_str=ev["date_str"],
                status="offen",
                status_display="Offen",
                url=link,
                details_loaded=False,
                teacher=extract_teacher(course_full=c_full, subject=subject, title=title),
            )
        )

    # 2. Aufgaben aus allen Kursen der aktuellen Klasse parallel abrufen (~1.5s)
    try:
        cids: List[Tuple[str, str]] = []
        seen_cids = set()

        # Direkt aus Kurslinks / Cache für die aktuelle Klasse laden
        try:
            from config import load_all_course_links
            for c in load_all_course_links():
                if c.get("platform") == "moodle":
                    m_cid = re.search(r"id=(\d+)", c.get("url", ""))
                    if m_cid and m_cid.group(1) not in seen_cids:
                        cids.append((m_cid.group(1), c.get("display_title") or c.get("subject", "")))
                        seen_cids.add(m_cid.group(1))
        except Exception:
            pass

        # Fallback auf /my/ scraping, falls noch keine Kurse im Cache waren
        if not cids:
            for overview_url in [f"{MOODLE_BASE_URL}/my/", f"{MOODLE_BASE_URL}/my/courses.php"]:
                try:
                    r_overview = session.get(overview_url, timeout=10)
                    if r_overview.status_code == 200:
                        matches = re.findall(r'<a[^>]*href="[^"]*course/view\.php\?id=(\d+)"[^>]*>(.*?)</a>', r_overview.text, re.DOTALL)
                        for cid, ctext in matches:
                            c_clean = html.unescape(re.sub(r'<[^>]+>', '', ctext)).strip()
                            if not c_clean or cid in seen_cids:
                                continue
                            full_cfg = load_full_school_config()
                            curr_cls = (full_cfg.get("student_class") or "").strip().lower()
                            filter_keywords = [curr_cls] if curr_cls else []
                            filter_keywords += ["sj2627", "2627", "sj2526", "2526"]
                            if not curr_cls or any(kw in c_clean.lower() for kw in filter_keywords):
                                cids.append((cid, c_clean))
                                seen_cids.add(cid)
                except Exception:
                    pass

        def fetch_course_assigns(c_info: Tuple[str, str]) -> List[dict]:
            cid, cname = c_info
            try:
                idx_url = f"{MOODLE_BASE_URL}/mod/assign/index.php?id={cid}"
                r_idx = session.get(idx_url, timeout=10)
                if r_idx.status_code == 200:
                    return parse_moodle_assign_index(r_idx.text, course_name=cname, base_url=MOODLE_BASE_URL)
            except Exception:
                pass
            return []

        if cids:
            with ThreadPoolExecutor(max_workers=min(len(cids), 8)) as ex:
                assign_lists = list(ex.map(fetch_course_assigns, cids[:8]))

            for a_list in assign_lists:
                for a in a_list:
                    link = a["url"]
                    if link in seen_urls:
                        for existing_t in tasks:
                            if existing_t.url == link:
                                if existing_t.status_display in ["Offen", "Unbekannt", ""]:
                                    existing_t.status_display = a["status_display"]
                                    existing_t.status = a["status"]
                        continue
                    seen_urls.add(link)

                    c_full = a["course_full"]
                    title = a["title"]
                    subject = normalize_subject_name(c_full or title)

                    tasks.append(
                        Task(
                            id=a["id"],
                            platform="moodle",
                            course=subject,
                            course_full=c_full,
                            title=title,
                            due_date_str=a["due_date"],
                            status=a["status"],
                            status_display=a["status_display"],
                            url=link,
                            details_loaded=False,
                            teacher=extract_teacher(course_full=c_full, subject=subject, title=title),
                        )
                    )
    except Exception as e:
        print(f"Hinweis: Moodle HTTP-Kurs-Scan Fehler: {e}", file=sys.stderr)

    # 3. Parallele HTTP-Statusprüfung aller verbliebenen offenen Aufgaben
    tasks_to_check = [
        t for t in tasks
        if t.status_display in ["Offen", "Unbekannt", ""] or t.status not in ["abgegeben", "offen"]
    ]
    if tasks_to_check:
        try:
            def update_status(t: Task):
                st, disp = check_moodle_task_status_http(session, t.url)
                t.status = st
                t.status_display = disp

            max_w = min(len(tasks_to_check), 8)
            with ThreadPoolExecutor(max_workers=max_w) as executor:
                list(executor.map(update_status, tasks_to_check))
        except Exception as e:
            print(f"Hinweis: Moodle HTTP-Statusprüfung fehlgeschlagen: {e}", file=sys.stderr)

    return tasks


def fetch_moodle_tasks(deep_scan: bool = False) -> List[Task]:
    """
    Ruft alle Moodle-Aufgaben ab.
    Versucht zuerst einen blitzschnellen HTTP-Scan (~2s).
    Fällt bei ungültigen Cookies oder Fehlern automatisch auf Playwright zurück.
    """
    # 1. Blitzschneller HTTP-Scan mit vorhandenen Cookies
    try:
        tasks = fetch_moodle_tasks_http(deep_scan=deep_scan)
        if tasks is not None and len(tasks) > 0:
            return tasks
    except Exception as e:
        print(f"Hinweis: Moodle HTTP-Scan nicht möglich ({e}), starte Playwright-Fallback...", file=sys.stderr)

    # 2. Browser-Fallback mit Playwright (Session wiederherstellen)
    tasks: List[Task] = []
    session_ok = False
    try:
        with sync_playwright() as p:
            browser = None
            for ch in [None, "chrome", "msedge"]:
                try:
                    kwargs = {"headless": True}
                    if ch:
                        kwargs["channel"] = ch
                    browser = p.chromium.launch(**kwargs)
                    if browser:
                        break
                except Exception:
                    continue

            if browser:
                try:
                    context = browser.new_context()
                    page = context.new_page()
                    session_ok = ensure_moodle_session(context, page)
                finally:
                    try:
                        browser.close()
                    except Exception:
                        pass
    except Exception:
        pass

    if session_ok:
        try:
            tasks = fetch_moodle_tasks_http(deep_scan=deep_scan)
            if tasks is not None:
                return tasks
        except Exception as e2:
            print(f"Fehler bei Moodle-HTTP nach Refresh: {e2}", file=sys.stderr)

    return tasks


class MoodlePageParser(HTMLParser):
    """Extrahiert Titel, Angabe (#intro), Abgabestatustabelle, Fälligkeitsdatum (.activity-dates) und Anhänge aus Moodle-Aufgabenseiten."""
    def __init__(self, base_url: str = MOODLE_BASE_URL):
        super().__init__()
        self.base_url = base_url
        self.in_intro = False
        self.has_intro = False
        self.intro_tag = None
        self.intro_depth = 0
        self.intro_html_parts = []

        self.in_table = False
        self.in_th = False
        self.in_td = False
        self.current_th = []
        self.current_td = []
        self.status_map = {}

        self.in_activity_dates = False
        self.in_date_item = False
        self.current_date_text = []
        self.due_date = ""

        self.in_a = False
        self.current_a_href = None
        self.current_a_text = []
        self.attachments: List[TaskAttachment] = []
        self.seen_att_urls = set()

        self.in_title = False
        self.current_title_parts = []
        self.title = ""

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        tag_lower = tag.lower()

        # Titel aus h1 oder h2
        if tag_lower in ["h1", "h2"] and not self.title:
            self.in_title = True
            self.current_title_parts = []

        # Intro container
        if not self.in_intro and not self.has_intro:
            classes = attr_dict.get("class", "").split()
            tag_id = attr_dict.get("id", "")
            data_region = attr_dict.get("data-region", "")
            if tag_id == "intro" or "activity-description" in classes or data_region == "activity-description" or ("box" in classes and "generalbox" in classes and not self.intro_html_parts):
                self.in_intro = True
                self.intro_tag = tag_lower
                self.intro_depth = 1
                return
        elif self.in_intro:
            if tag_lower == self.intro_tag:
                self.intro_depth += 1
            attr_str = "".join(f' {k}="{v}"' if v is not None else f' {k}' for k, v in attrs)
            self.intro_html_parts.append(f"<{tag}{attr_str}>")

        # Activity dates container (Moodle 4.x)
        classes_str = attr_dict.get("class", "")
        data_region = attr_dict.get("data-region", "")
        if "activity-dates" in classes_str or data_region == "activity-dates":
            self.in_activity_dates = True

        if self.in_activity_dates and "date-item" in classes_str.split():
            self.in_date_item = True
            self.current_date_text = []

        # Status-Tabelle
        if "submissionstatustable" in classes_str or "generaltable" in classes_str:
            self.in_table = True

        if self.in_table:
            if tag_lower == "th":
                self.in_th = True
                self.current_th = []
            elif tag_lower == "td":
                self.in_td = True
                self.current_td.append([])

        # Anhänge (Dateilinks über /pluginfile.php/)
        if tag_lower == "a":
            href = attr_dict.get("href", "")
            if "/pluginfile.php/" in href and not any(x in href for x in ["logo", "/theme/", "/icon", "mod_icon"]):
                self.in_a = True
                self.current_a_href = urllib.parse.urljoin(self.base_url, href)
                self.current_a_text = []

    def handle_endtag(self, tag):
        tag_lower = tag.lower()

        if self.in_title and tag_lower in ["h1", "h2"]:
            self.in_title = False
            if not self.title:
                self.title = "".join(self.current_title_parts).strip()

        if self.in_intro:
            if tag_lower == self.intro_tag:
                self.intro_depth -= 1
                if self.intro_depth == 0:
                    self.in_intro = False
                    self.has_intro = True
                    return
            self.intro_html_parts.append(f"</{tag}>")

        if self.in_date_item and tag_lower == "div":
            self.in_date_item = False
            item_txt = " ".join("".join(self.current_date_text).split())
            if any(kw in item_txt.lower() for kw in ["fällig:", "faellig:", "due:"]):
                m = re.search(r'(?:f[äa]llig|due):\s*([^\n\r]+)', item_txt, re.IGNORECASE)
                if m and not self.due_date:
                    self.due_date = m.group(1).strip()
            self.current_date_text = []

        if self.in_table:
            if tag_lower == "th":
                self.in_th = False
            elif tag_lower == "td":
                self.in_td = False
            elif tag_lower == "tr":
                k = "".join(self.current_th).strip().lower()
                if not k and len(self.current_td) >= 2:
                    k = "".join(self.current_td[0]).strip().lower()
                    v = " ".join("".join(self.current_td[1]).split())
                elif self.current_td:
                    v = " ".join("".join(self.current_td[-1]).split())
                else:
                    v = ""
                if k and v:
                    self.status_map[k] = v
                self.current_th = []
                self.current_td = []
            elif tag_lower == "table":
                self.in_table = False

        if self.in_a and tag_lower == "a":
            self.in_a = False
            href = self.current_a_href
            if href and href not in self.seen_att_urls:
                self.seen_att_urls.add(href)
                raw_name = "".join(self.current_a_text).strip()
                name = raw_name.split("\n")[0].strip() if raw_name else ""
                if not name or len(name) < 2:
                    parsed_path = urllib.parse.unquote(urllib.parse.urlparse(href).path)
                    name = os.path.basename(parsed_path.rstrip("/"))
                self.attachments.append(TaskAttachment(name=name, url=href))
            self.current_a_href = None
            self.current_a_text = []

    def handle_data(self, data):
        if self.in_title:
            self.current_title_parts.append(data)
        if self.in_intro:
            self.intro_html_parts.append(data)
        if self.in_date_item:
            self.current_date_text.append(data)
        if self.in_th:
            self.current_th.append(data)
        if self.in_td and self.current_td:
            self.current_td[-1].append(data)
        if self.in_a:
            self.current_a_text.append(data)

    def handle_startendtag(self, tag, attrs):
        if self.in_intro:
            attr_str = "".join(f' {k}="{v}"' if v is not None else f' {k}' for k, v in attrs)
            self.intro_html_parts.append(f"<{tag}{attr_str} />")


def fetch_moodle_task_details_http(task: Task) -> bool:
    """
    Lädt die Detailbeschreibung, Status und Anhänge einer Moodle-Aufgabe blitzschnell über HTTP.
    Gibt True bei Erfolg zurück, sonst False (für Playwright-Fallback).
    """
    cookies = get_saved_moodle_cookies()
    if not cookies:
        return False

    clean_target_url = re.sub(r"&action=\w+", "", task.url)
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    moodle_netloc = urllib.parse.urlparse(MOODLE_BASE_URL).netloc
    for c in cookies:
        session.cookies.set(c["name"], c["value"], domain=c.get("domain", moodle_netloc))

    try:
        resp = session.get(clean_target_url, timeout=10, allow_redirects=True)
        if resp.status_code != 200 or "/login/index.php" in resp.url:
            return False

        if resp.encoding is None:
            resp.encoding = resp.apparent_encoding or "utf-8"
        txt = resp.text
        if "<form id=\"login\"" in txt or "id=\"loginbtn\"" in txt:
            return False

        parser = MoodlePageParser(base_url=clean_target_url)
        parser.feed(txt)

        # Falls keine verwertbaren Inhalte gefunden wurden, nicht erfolgreich
        if not parser.status_map and not parser.intro_html_parts and "submissionstatus" not in txt.lower() and not parser.due_date:
            return False

        # 1. Titel
        if not task.title and parser.title.strip():
            task.title = parser.title.strip()

        # 2. Angabe / Beschreibung
        intro_html = "".join(parser.intro_html_parts).strip()
        if intro_html:
            task.description = html_to_markdown(intro_html)
        elif not task.description:
            task.description = "Keine gesonderte Aufgabenbeschreibung vorhanden."

        # 3. Status-Tabelle
        status_map = parser.status_map
        def get_map_value(*keys):
            for k in keys:
                for mk, mv in status_map.items():
                    if k in mk:
                        return mv
            return None

        status_disp = get_map_value("abgabestatus", "submission status")
        if status_disp:
            if "nichts abgegeben" in status_disp.lower() or "für diese aufgabe" in status_disp.lower():
                status_disp = "noch offen"
            task.status_display = status_disp
            s_lower = status_disp.lower()
            if any(neg in s_lower for neg in ["keine", "kein", "nichts", "nicht", "not"]):
                task.status = "offen"
            elif any(kw in s_lower for kw in ["abgegeben", "submitted"]):
                task.status = "abgegeben"
            else:
                task.status = "offen"

        if "submissionstatussubmitted" in txt.lower():
            task.status = "abgegeben"

        # Fälligkeitsdatum aus Tabelle, .activity-dates oder Regex
        due_val = get_map_value("fälligkeitsdatum", "faelligkeitsdatum", "due date")
        if not due_val and parser.due_date:
            due_val = parser.due_date
        if not due_val:
            m_due = re.search(r'(?:f[äa]llig|due):\s*</span>\s*([^<\r\n]+)', txt, re.IGNORECASE)
            if m_due:
                due_val = m_due.group(1).strip()
        if due_val:
            task.due_date_str = due_val

        rem_val = get_map_value("verbleibende zeit", "time remaining")
        if rem_val and any(kw in rem_val.lower() for kw in ["überfällig", "ueberfaellig", "overdue"]):
            if not task.is_completed:
                task.status = "ueberfaellig"

        # 4. Anhänge
        task.attachments = parser.attachments
        task.details_loaded = True
        return True

    except Exception:
        return False


def fetch_moodle_task_details(task: Task) -> Task:
    """
    Lädt die Detailbeschreibung (Angabe), Status und Anhänge einer Moodle-Aufgabe.
    Versucht zuerst einen blitzschnellen HTTP-Direktabruf (ca. 200ms).
    Fällt bei fehlenden Cookies oder Fehlern automatisch auf Playwright zurück.
    """
    if task.details_loaded:
        return task

    # 1. Blitzschneller HTTP-Direktabruf
    try:
        if fetch_moodle_task_details_http(task):
            return task
    except Exception as e:
        print(f"Hinweis: HTTP-Details-Abruf fehlgeschlagen: {e}", file=sys.stderr)

    # 2. Browser-Fallback mit Playwright
    with sync_playwright() as p:
        browser = None
        for ch in [None, "chrome", "msedge"]:
            try:
                kwargs = {"headless": True}
                if ch:
                    kwargs["channel"] = ch
                browser = p.chromium.launch(**kwargs)
                if browser:
                    break
            except Exception:
                continue
        if not browser:
            return task
        context = browser.new_context()
        page = context.new_page()

        try:
            if not ensure_moodle_session(context, page):
                return task
            clean_target_url = re.sub(r"&action=\w+", "", task.url)
            page.goto(clean_target_url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)

            # Titel
            title_el = page.query_selector(".page-header-headings h1, h1, h2")
            if title_el and not task.title:
                task.title = title_el.inner_text().strip()

            # Angabe / Beschreibung
            intro_html = ""
            intro_el = page.query_selector("#intro, .activity-description, [data-region='activity-description'], .box.generalbox")
            if intro_el:
                intro_html = intro_el.inner_html()
            task.description = html_to_markdown(intro_html) if intro_html else "Keine gesonderte Aufgabenbeschreibung vorhanden."

            # Status-Tabelle
            status_rows = page.query_selector_all(".submissionstatustable tr, table.generaltable tr")
            status_map = {}
            for row in status_rows:
                th = row.query_selector("th")
                td = row.query_selector("td")
                if th and td:
                    k = th.inner_text().strip().lower()
                    v = td.inner_text().strip().replace("\n", " ")
                    status_map[k] = v

            if "abgabestatus" in status_map:
                disp = status_map["abgabestatus"]
                if "nichts abgegeben" in disp.lower() or "für diese aufgabe" in disp.lower():
                    disp = "noch offen"
                task.status_display = disp
                disp_lower = disp.lower()
                if any(neg in disp_lower for neg in ["keine", "kein", "nichts", "nicht", "not"]):
                    task.status = "offen"
                elif any(kw in disp_lower for kw in ["abgegeben", "submitted"]):
                    task.status = "abgegeben"
                else:
                    task.status = "offen"

            if "fälligkeitsdatum" in status_map:
                task.due_date_str = status_map["fälligkeitsdatum"]
            else:
                due_el = page.query_selector('.activity-dates .date-item:has-text("Fällig"), .activity-dates .date-item:has-text("Due"), [data-region="activity-dates"]')
                if due_el:
                    d_txt = due_el.inner_text().strip()
                    m_d = re.search(r'(?:f[äa]llig|due):\s*([^\n\r]+)', d_txt, re.IGNORECASE)
                    if m_d:
                        task.due_date_str = m_d.group(1).strip()

            if "verbleibende zeit" in status_map and "überfällig" in status_map["verbleibende zeit"].lower():
                if not task.is_completed:
                    task.status = "ueberfaellig"

            # Anhänge ermitteln
            file_links = page.query_selector_all('a[href*="/pluginfile.php/"]')
            attachments: List[TaskAttachment] = []
            seen_att = set()

            for fl in file_links:
                href = fl.get_attribute("href") or ""
                if any(x in href for x in ["logo", "/theme/", "/icon", "mod_icon"]):
                    continue
                href = urllib.parse.urljoin(task.url, href)
                seen_att.add(href)

                raw_name = fl.inner_text().strip()
                name = raw_name.split("\n")[0].strip() if raw_name else ""
                if not name or len(name) < 2:
                    parsed_path = urllib.parse.unquote(urllib.parse.urlparse(href).path)
                    name = os.path.basename(parsed_path.rstrip("/"))

                attachments.append(TaskAttachment(name=name, url=href))

            task.attachments = attachments
            task.details_loaded = True

        except Exception as e:
            print(f"Error loading Moodle details: {e}", file=sys.stderr)
        finally:
            try:
                browser.close()
            except Exception:
                pass

    return task


def download_moodle_attachments(task: Task, dest_dir: Optional[str] = None) -> List[str]:
    """
    Lädt alle angehängten Dateien einer Aufgabe herunter und speichert die Angabe als angabe.md.
    Speichert standardmäßig im konfigurierten Download-Ordner.
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
            f.write(f"**Platform:** Moodle\n")
            f.write(f"**Due Date:** {task.due_date_str}\n")
            f.write(f"**Status:** {task.status_display}\n")
            f.write(f"**Submission Link:** [{task.url}]({task.url})\n\n")
            f.write("---\n\n")
            f.write("## Assignment Description\n\n")
            f.write(task.description or "No description provided.\n")
            f.write("\n\n---\n")
            if task.attachments:
                f.write("## Attached Files\n\n")
                for att in task.attachments:
                    f.write(f"- [{att.name}]({att.url})\n")
        downloaded_files.append(angabe_file)
    except Exception as e:
        print(f"Error writing angabe.md: {e}", file=sys.stderr)

    # 2. Anhänge via HTTP-Session mit Moodle-Cookies herunterladen
    cookies = get_saved_moodle_cookies() or []
    req_session = requests.Session()
    req_session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    moodle_netloc = urllib.parse.urlparse(MOODLE_BASE_URL).netloc
    for c in cookies:
        req_session.cookies.set(c["name"], c["value"], domain=c.get("domain", moodle_netloc))

    for att in task.attachments:
        target_path = os.path.join(dest_dir, sanitize_filename(att.name))
        try:
            resp = req_session.get(att.url, stream=True, timeout=30)
            if resp.status_code == 200:
                with open(target_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=32768):
                        if chunk:
                            f.write(chunk)
                att.local_path = target_path
                downloaded_files.append(target_path)
            else:
                print(f"Download fehlgeschlagen für {att.name}: HTTP {resp.status_code}", file=sys.stderr)
        except Exception as e:
            print(f"Download-Fehler für {att.name}: {e}", file=sys.stderr)

    return downloaded_files


# =============================================================================
# Moodle Course Files & Materials Explorer Functions
# =============================================================================

def get_moodle_http_session(cookies: Optional[list] = None) -> requests.Session:
    """Erzeugt eine mit gespeicherten Moodle-Cookies vorkonfigurierte HTTP-Session."""
    if cookies is None:
        cookies = get_saved_moodle_cookies() or []
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    moodle_netloc = urllib.parse.urlparse(MOODLE_BASE_URL).netloc
    for c in cookies:
        s.cookies.set(c["name"], c["value"], domain=c.get("domain", moodle_netloc))
    return s


def reload_moodle_courses_cache() -> int:
    """Lädt alle eingeschriebenen Moodle-Kurse über die Moodle-AJAX-API neu und speichert sie im Cache."""
    session = get_moodle_http_session()
    r = session.get(f"{MOODLE_BASE_URL}/my/", timeout=12)
    m = re.search(r'"sesskey":"([^"]+)"', r.text)

    # Falls sesskey nicht gefunden oder session abgelaufen, versuchen wir ensure_moodle_session()
    if not m:
        try:
            ensure_moodle_session()
            session = get_moodle_http_session()
            r = session.get(f"{MOODLE_BASE_URL}/my/", timeout=12)
            m = re.search(r'"sesskey":"([^"]+)"', r.text)
        except Exception:
            pass

    if not m:
        return 0

    sesskey = m.group(1)
    ajax_url = f"{MOODLE_BASE_URL}/lib/ajax/service.php?sesskey={sesskey}&info=core_course_get_enrolled_courses_by_timeline_classification"
    payload = [{
        "index": 0,
        "methodname": "core_course_get_enrolled_courses_by_timeline_classification",
        "args": {"offset": 0, "limit": 0, "classification": "all", "sort": "fullname"}
    }]

    res = session.post(ajax_url, json=payload, timeout=15)
    if res.status_code != 200:
        return 0

    data = res.json()
    if not data or not isinstance(data, list) or not data[0].get("data"):
        return 0

    raw_courses = data[0]["data"].get("courses", [])
    courses_to_save = []

    for rc in raw_courses:
        cid = str(rc.get("id", ""))
        if not cid:
            continue
        fn = rc.get("fullname", "")
        sn = rc.get("shortname", "")
        url = f"{MOODLE_BASE_URL}/course/view.php?id={cid}"

        # Grade level ermitteln (z.B. aus "1AHIT" -> 1, "3AHWII" -> 3)
        text = (fn + " " + sn).lower()
        grade = 0
        m_gr = re.search(r'\b([1-5])[a-z]{2,}', text)
        if m_gr:
            grade = int(m_gr.group(1))

        # Schulfach Kürzel ermitteln
        m_subj = re.match(r'^([A-Za-z0-9_]+(?:\s+[A-Za-z0-9_]+)?)\s*[-–]', fn)
        subj = m_subj.group(1).strip() if m_subj else normalize_subject_name(fn)

        courses_to_save.append({
            "id": cid,
            "fullname": fn,
            "shortname": sn,
            "subject": subj,
            "grade_level": grade,
            "url": url,
        })

    if courses_to_save:
        cache_path = os.path.join(CONFIG_DIR, "moodle_courses_cache.json")
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(courses_to_save, f, indent=2, ensure_ascii=False)

    return len(courses_to_save)

