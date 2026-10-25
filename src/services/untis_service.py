"""
untis_service.py - WebUntis Abwesenheiten- & Stundenplan-Synchronisation.
Liest Fehlzeiten aus WebUntis über die offizielle WebUntis API aus, gleicht sie
stundengenau mit dem Stundenplan des jeweiligen Datums ab und berechnet die
gefehlten Unterrichtsstunden pro Fach in Sekundenbruchteilen (ohne träges Browser-Scraping).
"""

import os
import sys
import json
import time
import re
import datetime
from typing import List, Dict, Tuple, Optional, Set
from urllib.parse import urlparse, parse_qs

import requests

from config import (
    UNTIS_URL,
    UNTIS_GROUP,
    UNTIS_SCHOOL,
    UNTIS_PROFILE_DIR,
    UNTIS_CACHE_FILE,
    _load_untis_group,
    _load_untis_school,
    save_untis_school,
    load_exam_notes,
    save_single_exam_note,
)
from auth import (
    get_existing_untis_credentials,
    save_untis_credentials,
    AuthResult,
    clean_school_username,
)
from models import (
    UntisLesson,
    UntisAbsenceInterval,
    MissedLesson,
    SubjectAbsenceSummary,
    DailyAbsenceSummary,
    UntisExam,
)


# Standard-Stundenzeiten als Fallback (HTL-Raster)
DEFAULT_PERIOD_TIMES: Dict[int, Tuple[str, str]] = {
    1: ("08:00", "08:50"),
    2: ("08:50", "09:40"),
    3: ("09:55", "10:45"),
    4: ("10:45", "11:35"),
    5: ("11:45", "12:35"),
    6: ("12:35", "13:25"),
    7: ("13:25", "14:15"),
    8: ("14:25", "15:15"),
    9: ("15:15", "16:05"),
    10: ("16:15", "17:05"),
    11: ("17:10", "17:55"),
    12: ("17:55", "18:40"),
    13: ("18:50", "19:35"),
    14: ("19:35", "20:20"),
    15: ("20:20", "21:05"),
}


def time_to_minutes(t_str: str) -> int:
    """Konvertiert 'HH:MM' in Minuten seit Mitternacht."""
    try:
        parts = t_str.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return 0


def minutes_to_time(m: int) -> str:
    """Konvertiert Minuten seit Mitternacht in 'HH:MM'."""
    h = (m // 60) % 24
    mins = m % 60
    return f"{h:02d}:{mins:02d}"


def intervals_overlap(start1: str, end1: str, start2: str, end2: str) -> bool:
    """Prüft, ob zwei Zeitintervalle [start1, end1] und [start2, end2] überlappen."""
    m_s1 = time_to_minutes(start1)
    m_e1 = time_to_minutes(end1)
    m_s2 = time_to_minutes(start2)
    m_e2 = time_to_minutes(end2)
    return max(m_s1, m_s2) < min(m_e1, m_e2)


def normalize_subject_name(raw: str) -> str:
    """Normalisiert Fachnamen (z.B. SWP -> SWP, SWP PM -> SWP PM, SWP1x -> SWP, Dx -> D, AMx -> AM)."""
    s = raw.strip()
    # Entferne Gruppenanhänge wie _1x, 1x, x, y, _1y, 1y für die Fächer-Kategorisierung
    base = re.sub(r'[_]?(?:[1-9]?[xy]|[1-9][a-z])$', '', s, flags=re.IGNORECASE).strip()
    if not base:
        base = s
    if base.upper() in ["SWP PM", "SWP_PM", "SWP-PM"]:
        return "SWP PM"
    if base.upper() == "SWP":
        return "SWP"
    return base.upper() if len(base) <= 5 else base


def format_untis_time(raw_val) -> str:
    """Wandelt Untis-Zeiten wie 850 (8:50) oder '08:50' sauber in 'HH:MM' um."""
    if isinstance(raw_val, int):
        s = f"{raw_val:04d}"
        return f"{s[:2]}:{s[2:]}"
    elif isinstance(raw_val, str):
        raw = raw_val.strip()
        if ":" in raw:
            parts = raw.split(":")
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        elif len(raw) <= 4 and raw.isdigit():
            s = f"{int(raw):04d}"
            return f"{s[:2]}:{s[2:]}"
    return "08:00"


def extract_subgroup(group_str: str, subj_str: str) -> str:
    """Extrahiert Untergruppen wie 'X' oder 'Y' aus Gruppen- oder Fachstrings."""
    s = f"{group_str} {subj_str}"
    m = re.search(r'(?:^|[_\s])([1-9]?([a-z]))(?:[_\s]|$)', s, re.IGNORECASE) or re.search(r'([1-9]?([a-z]))$', subj_str, re.IGNORECASE)
    if m:
        letter = m.group(2) if m.group(2) else m.group(1)[-1]
        if letter.upper() in ["X", "Y"]:
            return letter.upper()
    return ""


def extract_exam_subgroup(raw_subj: str = "", name: str = "", text: str = "") -> str:
    """Extrahiert Untergruppe X oder Y aus Fach, Name oder Text einer Prüfung."""
    combined = f"{raw_subj} {name} {text}"
    m = re.search(r'\b(?:gruppe\s*([xy])|([xy])\s*[-_]?\s*gruppe)\b', combined, re.IGNORECASE)
    if m:
        return (m.group(1) or m.group(2)).upper()
    m = re.search(r'(?:^|[_\s\(\[])(?:[1-9]?([xy])|([a-z0-9]+[1-9]?([xy])))(?:[_\s\)\-\]\.,;]|$)', combined, re.IGNORECASE)
    if m:
        letter = m.group(1) or m.group(3)
        if letter and letter.upper() in ["X", "Y"]:
            return letter.upper()
    return ""


def clean_school_identifier(raw: str) -> str:
    """
    Bereinigt eine Schulkennung oder Schul-URL zu einer sauberen WebUntis-Kennung.
    Beispiele:
      'https://spengergasse.webuntis.com/WebUntis/?school=spengergasse' -> 'spengergasse'
      'spengergasse.webuntis.com' -> 'spengergasse'
      '  spengergasse  ' -> 'spengergasse'
    """
    if not raw:
        return ""
    s = raw.strip()
    # Falls URL übergeben wurde
    if "://" in s or "/" in s:
        try:
            if not s.startswith("http://") and not s.startswith("https://"):
                s = "https://" + s
            parsed = urlparse(s)
            qs = parse_qs(parsed.query)
            if "school" in qs and qs["school"]:
                return qs["school"][0].strip()
            if parsed.netloc and ".webuntis.com" in parsed.netloc:
                sub = parsed.netloc.split(".")[0].lower()
                if sub not in ["arche", "urania", "triton", "www", "webuntis", "api"]:
                    return sub
        except Exception:
            pass

    # Domain ohne Protokoll (z.B. spengergasse.webuntis.com)
    if ".webuntis.com" in s.lower():
        sub = s.lower().split(".webuntis.com")[0].split("/")[-1].split(":")[-1]
        if sub and sub not in ["arche", "urania", "triton", "www", "webuntis", "api"]:
            return sub

    return s


def search_webuntis_school(search_term: str) -> Optional[dict]:
    """
    Sucht über die offizielle WebUntis School Search API nach einer Schule.
    Liefert Dict mit {loginName, serverUrl, server, displayName} oder None.
    """
    term = search_term.strip()
    if not term:
        return None
    url = "https://mobile.webuntis.com/ms/schoolquery2"
    payload = {
        "id": "search_1",
        "method": "searchSchool",
        "params": [{"search": term}],
        "jsonrpc": "2.0"
    }
    try:
        r = requests.post(url, json=payload, timeout=6)
        if r.status_code == 200:
            data = r.json()
            schools = data.get("result", {}).get("schools", [])
            if schools:
                return schools[0]
    except Exception:
        pass
    return None


def resolve_webuntis_server(untis_url: Optional[str] = None, school: Optional[str] = None) -> Tuple[str, str]:
    """
    Ermittelt den echten Server-Endpunkt und den Schulnamen aus einer WebUntis-URL oder dem Schulnamen.
    Unterstützt Redirects, Schul-Subdomains (z.B. meine-schule.webuntis.com) und schoolquery2 API.
    """
    raw_sch = (school or "").strip()
    raw_url = (untis_url or "").strip()

    # Falls der Benutzer eine vollständige URL als 'school' übergeben hat
    if raw_sch and ("http://" in raw_sch.lower() or "https://" in raw_sch.lower() or ".webuntis.com" in raw_sch.lower()):
        raw_url = raw_sch
        raw_sch = ""

    sch = clean_school_identifier(raw_sch)
    if not sch and raw_url:
        sch = clean_school_identifier(raw_url)

    if not sch:
        sch = _load_untis_school() or UNTIS_SCHOOL or "spengergasse"

    # Falls Leerzeichen im Schulnamen (z.B. 'HTL Spengergasse'), nutze WebUntis API zur Suche
    if " " in sch or len(sch) > 20:
        found = search_webuntis_school(sch)
        if found:
            login_name = found.get("loginName") or sch
            server_url = found.get("serverUrl") or ""
            if server_url:
                parsed = urlparse(server_url)
                base = f"{parsed.scheme}://{parsed.netloc}/WebUntis"
                return base, login_name

    clean_host_sch = re.sub(r'[^a-zA-Z0-9_\-]', '', sch)

    candidates: List[str] = []
    if raw_url and "://" in raw_url:
        p = urlparse(raw_url)
        if p.netloc:
            candidates.append(f"{p.scheme}://{p.netloc}/WebUntis")

    if clean_host_sch:
        candidates.append(f"https://{clean_host_sch}.webuntis.com/WebUntis")

    candidates.extend([
        "https://arche.webuntis.com/WebUntis",
        "https://urania.webuntis.com/WebUntis",
        "https://triton.webuntis.com/WebUntis",
    ])

    # Prüfe Kandidaten kurz auf Erreichbarkeit
    for cand in candidates:
        test_url = f"{cand}/jsonrpc.do?school={sch}" if sch else f"{cand}/jsonrpc.do"
        try:
            r = requests.post(test_url, json={"id": "probe", "method": "getSchoolYears", "jsonrpc": "2.0"}, timeout=3)
            if r.status_code == 200:
                return cand, sch
        except Exception:
            continue

    default_base = f"https://{clean_host_sch}.webuntis.com/WebUntis" if clean_host_sch else "https://spengergasse.webuntis.com/WebUntis"
    return default_base, sch


def authenticate_untis_api(session: requests.Session, base_url: str, school: str, user: str, passw: str) -> Tuple[bool, Optional[str], Optional[int], str]:
    """
    Authentifiziert die Session bei der WebUntis JSON-RPC API.
    Gibt (success, sessionId, personId, message) zurück.
    """
    endpoint = f"{base_url}/jsonrpc.do?school={school}" if school else f"{base_url}/jsonrpc.do"
    payload = {
        "id": "auth_1",
        "method": "authenticate",
        "params": {
            "user": user,
            "password": passw,
            "client": "Tasks"
        },
        "jsonrpc": "2.0"
    }
    try:
        resp = session.post(endpoint, json=payload, timeout=12)
        if resp.status_code != 200:
            return False, None, None, f"HTTP error {resp.status_code} from WebUntis server."

        data = resp.json()
        if "error" in data:
            err = data["error"]
            msg = err.get("message", "Login failed.")
            return False, None, None, f"WebUntis API: {msg}"

        res = data.get("result", {})
        session_id = res.get("sessionId")
        person_id = res.get("personId")
        if not session_id or not person_id:
            return False, None, None, "No valid session ID received."

        return True, session_id, person_id, "OK"
    except Exception as e:
        return False, None, None, f"Connection error to WebUntis: {e}"


def login_untis_direct(username: str, password: str, school: Optional[str] = None, untis_url: Optional[str] = None) -> AuthResult:
    """
    Prüft Anmeldedaten direkt bei der WebUntis API und speichert sie bei Erfolg lokal.
    Gibt AuthResult(success, message) zurück (abwärtskompatibel mit bool).
    """
    u = clean_school_username(username)
    p = password.strip()
    if not u or not p:
        return AuthResult(False, "Benutzername und Passwort dürfen nicht leer sein.")

    base_url, resolved_school = resolve_webuntis_server(untis_url=untis_url, school=school)
    session = requests.Session()
    ok, session_id, person_id, msg = authenticate_untis_api(session, base_url, resolved_school, u, p)
    if ok:
        save_untis_credentials(u, p)
        save_untis_school(resolved_school)
        # Sofortiger schneller Hintergrundabgleich der Fehlstunden
        try:
            sync_untis_data()
        except Exception:
            pass
        return AuthResult(True, "OK")
    return AuthResult(False, msg)


def is_untis_session_valid() -> bool:
    """Prüft, ob funktionierende WebUntis-Zugangsdaten oder ein Cache vorliegen."""
    path, creds = get_existing_untis_credentials()
    if not creds:
        return os.path.exists(UNTIS_CACHE_FILE)
    return True


def setup_untis_interactive(console=None) -> bool:
    """Interaktiver Login für WebUntis (überprüft vorhandene Zugangsdaten oder fragt ab)."""
    path, creds = get_existing_untis_credentials()
    if creds:
        u = creds.get("username", "")
        p = creds.get("password", "")
        if login_untis_direct(u, p):
            if console:
                console.print(f"[bold green]✓ WebUntis erfolgreich authentifiziert (Benutzer: {u})![/bold green]")
            return True

    if console:
        console.print("[yellow]Bitte verwende das Login-Menü im Terminal für WebUntis.[/yellow]")
    return False


def open_untis_login_window(console=None) -> bool:
    """Kompatibilitäts-Funktion für WebUntis Login-Dialog."""
    return setup_untis_interactive(console)



def fetch_untis_absences_api(
    session: requests.Session,
    base_url: str,
    person_id: int,
    start_date: int = 20260901,
    end_date: int = 20270705,
) -> List[UntisAbsenceInterval]:
    """
    Ruft alle erfassten Fehlzeiten des Schülers direkt über den offiziellen WebUntis REST-Endpunkt ab.
    """
    endpoint = f"{base_url}/api/classreg/absences/students?startDate={start_date}&endDate={end_date}&studentId={person_id}&excuseStatusId=-1"
    res = session.get(endpoint, timeout=12)
    if res.status_code != 200:
        return []

    data = res.json()
    items = data.get("data", {}).get("absences", [])
    out_list: List[UntisAbsenceInterval] = []

    for a in items:
        s_date = str(a.get("startDate", ""))
        if len(s_date) == 8 and s_date.isdigit():
            d_str = f"{s_date[:4]}-{s_date[4:6]}-{s_date[6:]}"
        else:
            d_str = s_date

        start_time = format_untis_time(a.get("startTime", 800))
        end_time = format_untis_time(a.get("endTime", 1700))
        reason = a.get("reason") or a.get("text") or "Absence"
        status = "Excused" if a.get("isExcused") else "Open"

        out_list.append(
            UntisAbsenceInterval(
                id=str(a.get("id", f"abs_{len(out_list)}")),
                date=d_str,
                start_time=start_time,
                end_time=end_time,
                reason=reason,
                status=status,
                text=a.get("studentName", ""),
            )
        )
    return out_list


def fetch_untis_exams_api(
    session: requests.Session,
    base_url: str,
    person_id: Optional[int] = None,
    start_date: int = 20260901,
    end_date: int = 20270715,
) -> List[UntisExam]:
    """
    Ruft alle eingetragenen Prüfungen, Tests und Schularbeiten des aktuellen Schuljahres
    über die WebUntis API ab und verknüpft sie mit lokal gespeicherten Notizen/Stoff.
    """
    endpoint = f"{base_url}/api/exams?startDate={start_date}&endDate={end_date}"
    try:
        res = session.get(endpoint, timeout=12)
        if res.status_code != 200:
            return []
        data = res.json().get("data", {})
        raw_exams = data.get("exams", [])
    except Exception as e:
        print(f"Error fetching WebUntis exams: {e}", file=sys.stderr)
        return []

    custom_notes = load_exam_notes()
    today = datetime.date.today()
    out_exams: List[UntisExam] = []

    type_display_map = {
        "SA": "School Exam",
        "TE": "Test",
        "PR": "Oral Exam",
    }

    for it in raw_exams:
        if not isinstance(it, dict):
            continue

        # Schülerzuordnung prüfen, falls person_id übergeben wurde
        assigned = it.get("assignedStudents", [])
        if person_id and assigned:
            if not any(s.get("id") == person_id for s in assigned if isinstance(s, dict)):
                continue

        raw_date = str(it.get("examDate", ""))
        if len(raw_date) == 8 and raw_date.isdigit():
            d_str = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
            d_display = f"{raw_date[6:]}.{raw_date[4:6]}.{raw_date[:4]}"
            try:
                ex_date = datetime.date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:]))
                days_diff = (ex_date - today).days
                is_past = days_diff < 0
            except Exception:
                is_past = False
                days_diff = 0
        else:
            d_str = raw_date
            d_display = raw_date
            is_past = False
            days_diff = 0

        raw_type = str(it.get("examType", "TE")).strip().upper()
        type_display = type_display_map.get(raw_type, raw_type)
        raw_subj = it.get("subject", "")
        clean_subj = normalize_subject_name(raw_subj)
        exam_name = it.get("name", "") or it.get("text", "")
        exam_text = it.get("text", "")
        exam_grp = extract_exam_subgroup(raw_subj, exam_name, exam_text)

        s_time = format_untis_time(it.get("startTime", 800))
        e_time = format_untis_time(it.get("endTime", 850))

        # Eindeutiger Identifikator für Notizen und Zuordnung
        ex_id = str(it.get("id", 0))
        if ex_id == "0" or not ex_id:
            ex_id = f"{d_str}_{s_time.replace(':', '')}_{clean_subj}"

        custom_topic = custom_notes.get(ex_id, "")

        teachers = it.get("teachers", [])
        rooms = it.get("rooms", [])

        out_exams.append(
            UntisExam(
                id=ex_id,
                exam_type=raw_type,
                exam_type_display=type_display,
                subject=clean_subj,
                name=exam_name,
                text=exam_text,
                date=d_str,
                date_display=d_display,
                start_time=s_time,
                end_time=e_time,
                teachers=teachers if isinstance(teachers, list) else [str(teachers)],
                rooms=rooms if isinstance(rooms, list) else [str(rooms)],
                custom_topics=custom_topic,
                is_past=is_past,
                days_until=days_diff,
                group=exam_grp,
            )
        )

    out_exams.sort(key=lambda x: (x.date, x.start_time))
    return out_exams


def fetch_untis_timetable_for_dates_api(
    session: requests.Session,
    base_url: str,
    school: str,
    person_id: int,
    dates: Set[str],
) -> List[UntisLesson]:
    """
    Lädt gezielt und stundengenau den Stundenplan für die Tage herunter, an denen Abwesenheiten vorliegen.
    Nutzt den offiziellen WebUntis-Kalenderendpunkt zur vollständigen Auflösung von
    Lehrerkürzeln (z.B. PUA, WWE, BIM), Fach- und Raumnamen.
    """
    out_lessons: List[UntisLesson] = []
    seen_weeks: Set[str] = set()

    for d_str in sorted(dates):
        try:
            dt = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
            monday = dt - datetime.timedelta(days=dt.weekday())
            week_key = monday.isoformat()
        except Exception:
            week_key = d_str

        if week_key in seen_weeks:
            continue
        seen_weeks.add(week_key)

        weekly_url = f"{base_url}/api/public/timetable/weekly/data?elementType=5&elementId={person_id}&date={d_str}"
        try:
            resp = session.get(weekly_url, timeout=12)
            if resp.status_code == 200:
                res_data = resp.json().get("data", {}).get("result", {}).get("data", {})
                elements = res_data.get("elements", [])

                teachers_map = {el["id"]: el.get("name") or el.get("displayname", "") for el in elements if el.get("type") == 2}
                subjects_map = {el["id"]: el.get("name") or el.get("displayname", "") for el in elements if el.get("type") == 3}
                rooms_map = {el["id"]: el.get("name") or el.get("displayname", "") for el in elements if el.get("type") == 4}

                periods = res_data.get("elementPeriods", {}).get(str(person_id), [])
                for p in periods:
                    s_date = str(p.get("date", ""))
                    if len(s_date) == 8 and s_date.isdigit():
                        p_date_str = f"{s_date[:4]}-{s_date[4:6]}-{s_date[6:]}"
                    else:
                        p_date_str = s_date

                    if p_date_str not in dates:
                        continue

                    t_ids = [el["id"] for el in p.get("elements", []) if el.get("type") == 2 and not el.get("missing")]
                    s_ids = [el["id"] for el in p.get("elements", []) if el.get("type") == 3]
                    r_ids = [el["id"] for el in p.get("elements", []) if el.get("type") == 4]

                    t_names: List[str] = []
                    for tid in t_ids:
                        tn = teachers_map.get(tid, "")
                        if tn and tn not in t_names:
                            t_names.append(tn)

                    s_names = [subjects_map.get(sid, "") for sid in s_ids if sid in subjects_map]
                    r_names: List[str] = []
                    for rid in r_ids:
                        rn = rooms_map.get(rid, "")
                        if rn and rn not in r_names:
                            r_names.append(rn)

                    raw_subj = s_names[0] if s_names else "Unknown"
                    raw_grp = p.get("studentGroup") or p.get("sg") or ""
                    start_time = format_untis_time(p.get("startTime", 800))
                    end_time = format_untis_time(p.get("endTime", 850))

                    out_lessons.append(
                        UntisLesson(
                            id=str(p.get("id", f"les_{len(out_lessons)}")),
                            date=p_date_str,
                            start_time=start_time,
                            end_time=end_time,
                            period_num=1,
                            subject=raw_subj,
                            teacher=", ".join(t_names),
                            room=", ".join(r_names),
                            is_cancelled=bool(p.get("cellState") == "CANCELLED" or p.get("isCancelled")),
                            group=extract_subgroup(raw_grp, raw_subj),
                        )
                    )
        except Exception as e:
            print(f"Note fetching weekly timetable for {d_str}: {e}", file=sys.stderr)

    return out_lessons


_TIMETABLE_CACHE: Dict[str, List[UntisLesson]] = {}
_AUTHENTICATED_SESSION: Optional[requests.Session] = None
_AUTHENTICATED_SESSION_TIME: float = 0
_AUTHENTICATED_PERSON_ID: Optional[int] = None
_AUTHENTICATED_BASE_URL: str = ""
_AUTHENTICATED_SCHOOL: str = ""


def get_authenticated_untis_session() -> Tuple[Optional[requests.Session], str, str, Optional[int]]:
    """Gibt eine aktive, authentifizierte WebUntis-Session zurück (wiederverwendet bestehende für 15 Min)."""
    global _AUTHENTICATED_SESSION, _AUTHENTICATED_SESSION_TIME, _AUTHENTICATED_PERSON_ID
    global _AUTHENTICATED_BASE_URL, _AUTHENTICATED_SCHOOL

    now = time.time()
    if _AUTHENTICATED_SESSION and (now - _AUTHENTICATED_SESSION_TIME < 900) and _AUTHENTICATED_PERSON_ID:
        return _AUTHENTICATED_SESSION, _AUTHENTICATED_BASE_URL, _AUTHENTICATED_SCHOOL, _AUTHENTICATED_PERSON_ID

    from auth import get_existing_untis_credentials
    path, creds = get_existing_untis_credentials()
    if not creds:
        return None, "", "", None
    u = creds.get("username", "").strip()
    p = creds.get("password", "").strip()
    if not u or not p:
        return None, "", "", None

    base_url, school = resolve_webuntis_server(UNTIS_URL)
    session = requests.Session()
    ok, session_id, person_id, msg = authenticate_untis_api(session, base_url, school, u, p)
    if ok and person_id:
        _AUTHENTICATED_SESSION = session
        _AUTHENTICATED_SESSION_TIME = now
        _AUTHENTICATED_PERSON_ID = person_id
        _AUTHENTICATED_BASE_URL = base_url
        _AUTHENTICATED_SCHOOL = school
        return session, base_url, school, person_id
    return None, "", "", None


def parse_subject_parts(subj_str: str) -> Tuple[str, str, str, str, str]:
    """
    Zerlegt einen Fachnamen in:
    (raw_upper, norm_alnum_nogrp, base_letters, sub_num, trailing_group)
    Beispiele:
    'SPL_1x' -> ('SPL_1X', 'SPL1', 'SPL', '1', 'X')
    'SPL_3'  -> ('SPL_3',  'SPL3', 'SPL', '3', '')
    'SPL'    -> ('SPL',    'SPL',  'SPL', '',  '')
    'SWP_1x' -> ('SWP_1X', 'SWP1', 'SWP', '1', 'X')
    """
    s = (subj_str or "").strip().upper()
    if not s:
        return "", "", "", "", ""

    trailing_group = ""
    s_no_group = s
    m_grp = re.search(r'[_]?([XY])$', s)
    if m_grp:
        trailing_group = m_grp.group(1)
        s_no_group = s[:m_grp.start()].rstrip("_- ")

    norm_alnum_nogrp = re.sub(r'[^A-Z0-9]', '', s_no_group)

    m_parts = re.match(r'^([A-Z]+)[_\s\-]*(\d+)?', s_no_group)
    if m_parts:
        base_letters = m_parts.group(1)
        sub_num = m_parts.group(2) or ""
    else:
        base_letters = norm_alnum_nogrp
        sub_num = ""

    return s, norm_alnum_nogrp, base_letters, sub_num, trailing_group


def match_lesson_subject(query: str, lesson_subj: str) -> int:
    """
    Berechnet die Übereinstimmungs-Priorität zwischen Suchanfrage und Unterrichtsstunde:
    0: Kein Match oder Nummer-Konflikt (z.B. SPL_1 vs SPL_3)
    100: Exakter Voll-Match (z.B. SPL_1 == SPL_1x, SPL1 == SPL_1x, AMEC == AMEC)
    80: Normalisierter Mapped Match (z.B. Englisch -> E1x, SWP -> SWP_1x) oder Basis-Match (SPL -> SPL_1x)
    40: Substring/Präfix Fallback
    """
    q_raw, q_norm, q_base, q_num, q_grp = parse_subject_parts(query)
    l_raw, l_norm, l_base, l_num, l_grp = parse_subject_parts(lesson_subj)

    if not q_norm or not l_norm:
        return 0

    # Strenger Konflikt-Ausschluss:
    # Wenn die Anfrage einen spezifischen Index hat (z.B. '1' in 'SPL_1'),
    # und die Stunde einen anderen Index hat (z.B. '3' in 'SPL_3'),
    # darf NIEMALS gematcht werden!
    if q_num and l_num and q_num != l_num:
        return 0

    # 1. Exakter Match auf Original-String (ohne Case)
    if q_raw == l_raw:
        return 100

    # 2. Exakter Match ohne Gruppen-Suffix (z.B. SPL_1 vs SPL_1x -> beide SPL1)
    if q_norm == l_norm:
        return 100

    # 3. Basisbuchstaben und Sub-Nummer stimmen überein (z.B. SPL-1 vs SPL_1x)
    if q_base == l_base and q_num == l_num and q_num != "":
        return 100

    # 4. Über Config gemappte Namen (z.B. 'Englisch' -> 'E', 'Mathematik' -> 'AMEC')
    from config import normalize_subject_name as config_norm
    mapped_q = config_norm(query).upper()
    mapped_q_raw, mapped_q_norm, mapped_q_base, mapped_q_num, _ = parse_subject_parts(mapped_q)
    if mapped_q_base == l_base and (not mapped_q_num or mapped_q_num == l_num):
        if not q_num or q_num == l_num:
            return 80

    # 5. Basis-Fach Match (z.B. Anfrage 'SPL' ohne Nummer matcht sowohl 'SPL_1x' als auch 'SPL_3y')
    if q_base == l_base and not q_num:
        return 80

    if mapped_q_base == l_base and not q_num:
        return 80

    # 6. Teilstring/Präfix Fallback
    if len(q_base) >= 2 and (q_base in l_raw or l_base in q_raw):
        if not q_num or q_num == l_num:
            return 40

    return 0


def lookup_untis_lesson_details(
    target_date_iso: str,
    subject_query: str,
    preferred_group: Optional[str] = None
) -> Optional[Dict[str, str]]:
    """
    Sucht im WebUntis-Stundenplan nach einer passenden Unterrichtsstunde am angegebenen Datum (YYYY-MM-DD)
    für das gewünschte Fach (z.B. 'E', 'Englisch', 'BET', 'AMEC', 'SWP PM', 'SPL_1', 'SPL_3').
    
    Kombiniert aufeinanderfolgende Stunden (z.B. Doppelstunden) zu einem zusammenhängenden Zeitfenster.
    
    Gibt ein Dict zurück mit:
    {
        "start_time": "09:55",
        "end_time": "10:45",
        "time_str": "09:55 - 10:45",
        "teacher": "SO",
        "room": "A1.15",
        "group": "X",
        "matched_subject": "E1x"
    }
    oder None wenn keine passende Stunde gefunden wurde.
    """
    if not target_date_iso or not subject_query:
        return None

    if preferred_group is None:
        preferred_group = _load_untis_group() or "X"
    preferred_group = preferred_group.strip().upper()

    lessons = _TIMETABLE_CACHE.get(target_date_iso)
    if lessons is None:
        session, base_url, school, person_id = get_authenticated_untis_session()
        if not session or not person_id:
            return None
        fetched = fetch_untis_timetable_for_dates_api(session, base_url, school, person_id, {target_date_iso})
        lessons = [l for l in fetched if l.date == target_date_iso]
        _TIMETABLE_CACHE[target_date_iso] = lessons

    if not lessons:
        return None

    scored_lessons = []
    for l in lessons:
        if l.is_cancelled:
            continue
        score = match_lesson_subject(subject_query, l.subject)
        if score > 0:
            scored_lessons.append((l, score))

    if not scored_lessons:
        return None

    # Höchste Match-Priorität filtern (Exakte Matches haben Vorrang vor Teil-Matches)
    max_score = max(score for _, score in scored_lessons)
    matched = [l for l, score in scored_lessons if score == max_score]

    if preferred_group:
        grp_matched = [m for m in matched if not m.group or m.group.upper() == preferred_group]
        if grp_matched:
            matched = grp_matched

    matched.sort(key=lambda x: x.start_time)

    # Wenn mehrere aufeinanderfolgende Stunden vorliegen (z.B. Doppelstunde mit max 20 Min Pause)
    current_block = [matched[0]]
    for next_l in matched[1:]:
        prev_l = current_block[-1]
        if time_to_minutes(next_l.start_time) - time_to_minutes(prev_l.end_time) <= 20:
            current_block.append(next_l)
        else:
            break
    matched = current_block

    start_time = matched[0].start_time
    end_time = matched[-1].end_time

    teachers = []
    for m in matched:
        if m.teacher:
            for t in m.teacher.split(","):
                t = t.strip()
                if t and t not in teachers:
                    teachers.append(t)

    rooms = []
    for m in matched:
        if m.room:
            for r in m.room.split(","):
                r = r.strip()
                if r and r not in rooms:
                    rooms.append(r)

    group_res = matched[0].group or preferred_group or ""

    return {
        "start_time": start_time,
        "end_time": end_time,
        "time_str": f"{start_time} - {end_time}",
        "teacher": ", ".join(teachers),
        "room": ", ".join(rooms),
        "group": group_res,
        "matched_subject": matched[0].subject,
    }



def match_absences_with_timetable(
    absences: List[UntisAbsenceInterval],
    lessons: List[UntisLesson],
    student_group: str = "X",
) -> List[SubjectAbsenceSummary]:
    """
    Vergleicht jede Fehlzeit exakt mit den Unterrichtseinheiten dieses Tages:
    1. Datum muss exakt übereinstimmen (kein willkürlicher Wochentag)
    2. Zeitliches Overlap
    3. Auch entfallene Stunden zählen (wie gewünscht)
    4. Gruppenteilung (z.B. nur X Stunden zählen, wenn group="X")
    """
    grp = (student_group or _load_untis_group() or "").strip().upper()
    grp_norm = "X" if "X" in grp else ("Y" if "Y" in grp else grp)

    # Gruppiere Stunden nach Datum
    lessons_by_date: Dict[str, List[UntisLesson]] = {}
    for l in lessons:
        lessons_by_date.setdefault(l.date, []).append(l)

    missed_by_subject: Dict[str, List[MissedLesson]] = {}
    seen_lesson_keys: Set[str] = set()

    for abs_int in absences:
        day_lessons = lessons_by_date.get(abs_int.date, [])
        for l in day_lessons:
            # Gruppenfilter prüfen: Wenn Stunde einer anderen Gruppe zugeordnet ist
            lesson_grp = (l.group or "").strip().upper()
            if not lesson_grp:
                lesson_grp = extract_subgroup("", l.subject)
            lesson_norm = "X" if "X" in lesson_grp else ("Y" if "Y" in lesson_grp else lesson_grp)

            if grp_norm and lesson_norm and lesson_norm != grp_norm:
                continue

            # Zeit-Overlap prüfen
            if intervals_overlap(l.start_time, l.end_time, abs_int.start_time, abs_int.end_time):
                subj_clean = normalize_subject_name(l.subject)
                # Eindeutiger Key für diese Unterrichtseinheit am Tag (Datum + Startzeit + Fach)
                unit_key = f"{l.date}_{l.start_time}_{subj_clean}"
                if unit_key in seen_lesson_keys:
                    continue
                seen_lesson_keys.add(unit_key)

                m_s1 = time_to_minutes(l.start_time)
                m_e1 = time_to_minutes(l.end_time)
                m_s2 = time_to_minutes(abs_int.start_time)
                m_e2 = time_to_minutes(abs_int.end_time)

                overlap_start = max(m_s1, m_s2)
                overlap_end = min(m_e1, m_e2)
                overlap_mins = max(0, overlap_end - overlap_start)
                if overlap_mins == 0:
                    continue

                abs_start_str = minutes_to_time(overlap_start)
                abs_end_str = minutes_to_time(overlap_end)

                missed = MissedLesson(
                    date=l.date,
                    subject=subj_clean,
                    period_num=l.period_num,
                    start_time=abs_start_str,
                    end_time=abs_end_str,
                    lesson_start_time=l.start_time,
                    lesson_end_time=l.end_time,
                    duration_minutes=overlap_mins,
                    teacher=l.teacher,
                    room=l.room,
                    is_cancelled=l.is_cancelled,
                    reason=abs_int.reason or "Abwesend",
                    absence_status=abs_int.status or "Erfasst",
                )
                missed_by_subject.setdefault(subj_clean, []).append(missed)

    # Zusammenfassungen erstellen
    summaries: List[SubjectAbsenceSummary] = []
    for subj, m_list in missed_by_subject.items():
        m_list.sort(key=lambda m: (m.date, m.start_time))
        last_d = m_list[-1].date if m_list else ""
        summaries.append(
            SubjectAbsenceSummary(
                subject=subj,
                total_hours=len(m_list),
                missed_lessons=m_list,
                last_date=last_d,
            )
        )

    # Sortiere Fächer absteigend nach Gesamtstunden
    summaries.sort(key=lambda s: (-s.total_hours, s.subject))
    return summaries


def calculate_subject_absences(
    absences: List[UntisAbsenceInterval],
    lessons: List[UntisLesson],
    student_group: str = "1x",
) -> List[SubjectAbsenceSummary]:
    """Berechnet die Fehlstunden pro Fach."""
    return match_absences_with_timetable(absences, lessons, student_group)


def get_cached_untis_person_id() -> Optional[int]:
    """Liest die gespeicherte person_id aus dem Untis-Cache."""
    if not os.path.exists(UNTIS_CACHE_FILE):
        return None
    try:
        with open(UNTIS_CACHE_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d.get("person_id")
    except Exception:
        return None


def get_exam_web_url(exam: UntisExam) -> str:
    """Ermittelt die WebUntis-URL für eine Prüfung (entweder lessonDetails oder Tages-Stundenplan)."""
    if getattr(exam, "url", None):
        return exam.url
    base_url, _ = resolve_webuntis_server(UNTIS_URL)
    web_root = base_url.replace("/WebUntis", "").rstrip("/")
    person_id = get_cached_untis_person_id()
    if person_id and exam.date:
        return f"{web_root}/timetable/my-student?date={exam.date}&entityId={person_id}"
    elif exam.date:
        return f"{web_root}/timetable/my-student?date={exam.date}"
    return f"{web_root}/timetable/my-student"


def save_untis_cache(summaries: List[SubjectAbsenceSummary], exams: Optional[List[UntisExam]] = None, person_id: Optional[int] = None) -> None:
    """Speichert die berechneten Fehlstunden und optional Prüfungen im lokalen Cache."""
    try:
        data = {}
        if os.path.exists(UNTIS_CACHE_FILE):
            try:
                with open(UNTIS_CACHE_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        data = loaded
            except Exception:
                data = {}

        data["updated_at"] = datetime.datetime.now().isoformat()
        data["group"] = _load_untis_group()
        data["subjects"] = [s.to_dict() for s in summaries]

        if person_id is not None:
            data["person_id"] = person_id

        if exams is not None:
            data["exams"] = [e.to_dict() for e in exams]

        with open(UNTIS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving WebUntis cache: {e}", file=sys.stderr)


def save_untis_exams_cache(exams: List[UntisExam]) -> None:
    """Speichert ausschließlich die Prüfungsliste im Cache."""
    try:
        data = {}
        if os.path.exists(UNTIS_CACHE_FILE):
            try:
                with open(UNTIS_CACHE_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        data = loaded
            except Exception:
                data = {}
        data["exams"] = [e.to_dict() for e in exams]
        data["exams_updated_at"] = datetime.datetime.now().isoformat()
        with open(UNTIS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error caching exams: {e}", file=sys.stderr)


def load_custom_exams() -> List[UntisExam]:
    """Lädt manuell erstellte Prüfungen aus der lokalen JSON-Datei."""
    from config import CUSTOM_EXAMS_FILE, APP_CUSTOM_EXAMS_FILE, load_exam_notes
    custom_list: List[UntisExam] = []
    seen_ids = set()
    today = datetime.date.today()
    custom_notes = load_exam_notes()
    for path in [CUSTOM_EXAMS_FILE, APP_CUSTOM_EXAMS_FILE]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    items = json.load(f)
                    if isinstance(items, list):
                        for item in items:
                            ex = UntisExam.from_dict(item)
                            ex.is_custom = True
                            if ex.id not in seen_ids:
                                seen_ids.add(ex.id)
                                if ex.id in custom_notes:
                                    ex.custom_topics = custom_notes[ex.id]
                                if ex.date:
                                    try:
                                        dt = datetime.datetime.strptime(ex.date, "%Y-%m-%d").date()
                                        ex.days_until = (dt - today).days
                                        ex.is_past = ex.days_until < 0
                                    except Exception:
                                        pass
                                custom_list.append(ex)
            except Exception as e:
                print(f"Error loading custom exams from {path}: {e}", file=sys.stderr)
    return custom_list


def save_custom_exam(exam: UntisExam) -> None:
    """Speichert eine neue oder geänderte manuelle Prüfung persistent."""
    from config import CUSTOM_EXAMS_FILE, APP_CUSTOM_EXAMS_FILE
    exam.is_custom = True
    if not str(exam.id).startswith("custom_"):
        exam.id = f"custom_{exam.id}"

    current = load_custom_exams()
    updated = [e for e in current if e.id != exam.id]
    updated.append(exam)

    for path in [CUSTOM_EXAMS_FILE, APP_CUSTOM_EXAMS_FILE]:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp_p = f"{path}.tmp"
            with open(tmp_p, "w", encoding="utf-8") as f:
                json.dump([e.to_dict() for e in updated], f, indent=2, ensure_ascii=False)
            os.replace(tmp_p, path)
        except Exception as e:
            print(f"Error saving custom exam to {path}: {e}", file=sys.stderr)

    save_single_exam_note(exam.id, exam.custom_topics or "")
    try:
        from git_sync_service import is_git_configured, GitSyncService
        if is_git_configured():
            GitSyncService.async_push(f"Save custom exam {exam.subject}")
    except Exception:
        pass


def delete_custom_exam(exam_id: str) -> bool:
    """Löscht eine manuelle Prüfung persistent aus allen Speicherdateien."""
    from config import CUSTOM_EXAMS_FILE, APP_CUSTOM_EXAMS_FILE
    current = load_custom_exams()
    remaining = [e for e in current if e.id != exam_id]

    for path in [CUSTOM_EXAMS_FILE, APP_CUSTOM_EXAMS_FILE]:
        if os.path.exists(path):
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump([e.to_dict() for e in remaining], f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"Error deleting custom exam from {path}: {e}", file=sys.stderr)

    # Auch aus UNTIS_CACHE_FILE entfernen
    if os.path.exists(UNTIS_CACHE_FILE):
        try:
            with open(UNTIS_CACHE_FILE, "r", encoding="utf-8") as f:
                cdata = json.load(f)
            if isinstance(cdata, dict) and "exams" in cdata:
                cdata["exams"] = [x for x in cdata["exams"] if str(x.get("id")) != str(exam_id)]
                with open(UNTIS_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(cdata, f, indent=2)
        except Exception:
            pass

    try:
        from git_sync_service import is_git_configured, GitSyncService
        if is_git_configured():
            GitSyncService.async_push(f"Delete custom exam {exam_id}")
    except Exception:
        pass

    return True


def load_untis_exams_cache() -> List[UntisExam]:
    """Lädt gespeicherte Prüfungen aus dem lokalen Cache sowie benutzerdefinierte Prüfungen ab."""
    custom_exams = load_custom_exams()
    custom_notes = load_exam_notes()
    exams: List[UntisExam] = []
    seen_ids = set()
    today = datetime.date.today()

    if os.path.exists(UNTIS_CACHE_FILE):
        try:
            with open(UNTIS_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                raw_list = data.get("exams", [])
                for item in raw_list:
                    ex = UntisExam.from_dict(item)
                    if ex.id in seen_ids:
                        continue
                    seen_ids.add(ex.id)
                    # Aktualisiere Zeitberechnung
                    if ex.date:
                        try:
                            dt = datetime.datetime.strptime(ex.date, "%Y-%m-%d").date()
                            ex.days_until = (dt - today).days
                            ex.is_past = ex.days_until < 0
                        except Exception:
                            pass
                    if ex.id in custom_notes:
                        ex.custom_topics = custom_notes[ex.id]
                    if not ex.group:
                        ex.group = extract_exam_subgroup(item.get("raw_subject") or ex.subject, ex.name, ex.text)
                    if not ex.url and not ex.is_custom:
                        ex.url = get_exam_web_url(ex)
                    exams.append(ex)
        except Exception as e:
            print(f"Error loading exam cache: {e}", file=sys.stderr)

    # Merge custom exams
    for cex in custom_exams:
        if cex.id not in seen_ids:
            seen_ids.add(cex.id)
            if cex.id in custom_notes:
                cex.custom_topics = custom_notes[cex.id]
            exams.append(cex)

    exams.sort(key=lambda x: (x.date, x.start_time))
    return exams


def get_next_upcoming_exam(group: Optional[str] = None) -> Optional[UntisExam]:
    """Gibt die allernächste anstehende Prüfung für die gewünschte Gruppe (X oder Y) zurück."""
    exams = load_untis_exams_cache()
    if group is None:
        group = _load_untis_group() or "X"
    grp = group.strip().upper() if group else ""
    valid_exams = [e for e in exams if not e.group or e.group.upper() == grp]
    upcoming = [e for e in valid_exams if not e.is_past or e.days_until == 0]
    return upcoming[0] if upcoming else None


def load_untis_cache() -> List[SubjectAbsenceSummary]:
    """Lädt die Fehlstunden aus dem lokalen Cache."""
    if not os.path.exists(UNTIS_CACHE_FILE):
        return []
    try:
        with open(UNTIS_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            subjects = data.get("subjects", [])
            return [SubjectAbsenceSummary.from_dict(s) for s in subjects]
    except Exception as e:
        print(f"Error loading WebUntis cache: {e}", file=sys.stderr)
        return []


def get_daily_absence_summaries(summaries: Optional[List[SubjectAbsenceSummary]] = None) -> List[DailyAbsenceSummary]:
    """
    Aggregiert Fehlstunden tagesweise für das offizielle Entschuldigungsschreiben.
    Fasst alle Stunden an einem Tag zusammen (z.B. 4 Stunden = 3:20 Fehlstunden).
    """
    if summaries is None:
        summaries = load_untis_cache()

    lessons_by_date: Dict[str, List[MissedLesson]] = {}
    seen_keys: Set[str] = set()

    for s in summaries:
        for m in s.missed_lessons:
            # Eindeutiger Schlüssel für Unterrichtsstunde an dem Tag
            key = f"{m.date}_{m.lesson_start_time or m.start_time}_{m.subject}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            lessons_by_date.setdefault(m.date, []).append(m)

    daily_list: List[DailyAbsenceSummary] = []
    for d_str in sorted(lessons_by_date.keys(), reverse=True):
        m_list = lessons_by_date[d_str]
        m_list.sort(key=lambda x: x.start_time)
        hours = len(m_list)
        total_mins = 0
        for m in m_list:
            if getattr(m, "duration_minutes", 0) > 0:
                total_mins += m.duration_minutes
            elif m.start_time and m.end_time:
                diff = time_to_minutes(m.end_time) - time_to_minutes(m.start_time)
                total_mins += diff if diff > 0 else 50
            else:
                total_mins += 50
        dur_h = total_mins // 60
        dur_m = total_mins % 60
        dur_str = f"{dur_h}:{dur_m:02d}"

        # Formatiere Datum als DD.MM.YYYY
        d_display = d_str
        if len(d_str) == 10 and "-" in d_str:
            parts = d_str.split("-")
            d_display = f"{parts[2]}.{parts[1]}.{parts[0]}"

        subjs = list(dict.fromkeys(m.subject for m in m_list if m.subject))
        all_excused = all(
            any(w in (m.absence_status or "").lower() for w in ["entschuldigt", "excused"])
            for m in m_list
        )
        status_str = "Excused" if (all_excused and m_list) else "Open"

        daily_list.append(
            DailyAbsenceSummary(
                date=d_str,
                date_display=d_display,
                school_hours=hours,
                duration_str=dur_str,
                subjects=subjs,
                status=status_str,
                lessons=m_list,
            )
        )

    return daily_list


def sync_untis_data(headless: bool = True, console=None, progress_cb=None) -> Tuple[bool, str, List[SubjectAbsenceSummary]]:
    """
    Führt die vollständige WebUntis-Synchronisation über die native High-Speed API durch:
    1. Liest Zugangsdaten (Untis- oder Moodle-Schulaccount).
    2. Authentifiziert per WebUntis JSON-RPC.
    3. Ruft Fehlzeiten stundengenau ab.
    4. Lädt den Stundenplan für exakt diese Tage herunter.
    5. Gleicht Fehlzeiten mit dem Stundenplan ab und speichert das Ergebnis.
    """
    path, creds = get_existing_untis_credentials()
    if not creds:
        return False, "No WebUntis credentials configured. Please use [Login] -> [WebUntis Login].", []

    user = creds.get("username", "").strip()
    passw = creds.get("password", "").strip()
    if not user or not passw:
        return False, "Invalid WebUntis credentials stored in system.", []

    if progress_cb:
        progress_cb(10, "Connecting to WebUntis API...")

    base_url, school = resolve_webuntis_server(UNTIS_URL)
    session = requests.Session()

    ok, session_id, person_id, msg = authenticate_untis_api(session, base_url, school, user, passw)
    if not ok or not person_id:
        return False, f"WebUntis login failed: {msg}", []

    if progress_cb:
        progress_cb(35, "Downloading absences...")

    # Aktuelles Schuljahr abrufen (z.B. September bis Juli)
    today = datetime.date.today()
    curr_year = today.year
    start_year = curr_year if today.month >= 8 else curr_year - 1
    start_date_int = int(f"{start_year}0901")
    end_date_int = int(f"{start_year + 1}0715")

    absences = fetch_untis_absences_api(session, base_url, person_id, start_date=start_date_int, end_date=end_date_int)

    # Prüfungen und Tests synchronisieren
    if progress_cb:
        progress_cb(50, "Downloading exams and tests...")
    exams = fetch_untis_exams_api(session, base_url, person_id=person_id, start_date=start_date_int, end_date=end_date_int)

    unique_dates = {a.date for a in absences if a.date}
    if exams:
        for ex in exams:
            if ex.date:
                unique_dates.add(ex.date)

    if progress_cb:
        progress_cb(70, "Downloading timetable for lessons and exams...")

    lessons = fetch_untis_timetable_for_dates_api(session, base_url, school, person_id, unique_dates)

    # WebUntis Lesson-Details URLs für Tests generieren
    web_root = base_url.replace("/WebUntis", "").rstrip("/")
    lessons_by_date: Dict[str, List[UntisLesson]] = {}
    for l in lessons:
        lessons_by_date.setdefault(l.date, []).append(l)

    for ex in exams:
        m_id = None
        for l in lessons_by_date.get(ex.date, []):
            if l.start_time == ex.start_time:
                m_id = l.id
                break
        if m_id and person_id:
            ex.url = f"{web_root}/timetable/my-student/lessonDetails/{m_id}/{person_id}/5/{ex.date}T{ex.start_time}:00/{ex.date}T{ex.end_time}:00/false?date={ex.date}&entityId={person_id}"
        elif person_id and ex.date:
            ex.url = f"{web_root}/timetable/my-student?date={ex.date}&entityId={person_id}"
        elif ex.date:
            ex.url = f"{web_root}/timetable/my-student?date={ex.date}"

    if not absences:
        save_untis_cache([], exams=exams, person_id=person_id)
        return True, "No absences found in WebUntis (0 missed hours).", []

    if progress_cb:
        progress_cb(90, "Calculating missed hours per subject...")

    current_group = _load_untis_group() or "X"
    summaries = match_absences_with_timetable(absences, lessons, student_group=current_group)
    save_untis_cache(summaries, exams=exams, person_id=person_id)

    total_missed = sum(s.total_hours for s in summaries)
    subj_plural = "subjects" if len(summaries) != 1 else "subject"
    hour_plural = "missed hours" if total_missed != 1 else "missed hour"
    success_msg = f"WebUntis synchronized: {len(summaries)} {subj_plural}, {total_missed} {hour_plural} recorded."
    if progress_cb:
        progress_cb(100, success_msg)

    return True, success_msg, summaries


# Legacy DOM-Scraper als Fallbacks für Rückwärtskompatibilität
def scrape_dom_absences(page, out_list: List[UntisAbsenceInterval]) -> None:
    """Fallback-DOM-Scraping für Abwesenheiten."""
    pass


def scrape_dom_timetable_day(page, target_date: str, out_list: List[UntisLesson]) -> None:
    """Fallback-DOM-Scraping für den Stundenplan."""
    pass


def parse_json_absences(data: dict, out_list: List[UntisAbsenceInterval]) -> None:
    """Extrahiert Abwesenheiten aus WebUntis JSON-Antworten."""
    try:
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("data", {}).get("absences", []) or data.get("absences", []) or data.get("result", [])

        for it in items:
            if not isinstance(it, dict):
                continue
            s_date = str(it.get("startDate", it.get("date", "")))
            if len(s_date) == 8 and s_date.isdigit():
                d_str = f"{s_date[:4]}-{s_date[4:6]}-{s_date[6:]}"
            else:
                d_str = s_date

            s_time = format_untis_time(it.get("startTime", "08:00"))
            e_time = format_untis_time(it.get("endTime", "17:00"))
            reason = it.get("reason", it.get("text", "Absence"))
            status = "Excused" if it.get("isExcused") or it.get("excused") else "Open"

            if d_str:
                out_list.append(
                    UntisAbsenceInterval(
                        id=str(it.get("id", f"abs_{len(out_list)}")),
                        date=d_str,
                        start_time=s_time,
                        end_time=e_time,
                        reason=reason,
                        status=status,
                    )
                )
    except Exception:
        pass


def parse_json_timetable(data: dict, out_list: List[UntisLesson]) -> None:
    """Extrahiert Unterrichtsstunden aus WebUntis JSON-Antworten."""
    try:
        elements = []
        if isinstance(data, list):
            elements = data
        elif isinstance(data, dict):
            elements = data.get("data", {}).get("elements", []) or data.get("result", []) or data.get("periods", [])

        for el in elements:
            if not isinstance(el, dict):
                continue
            s_date = str(el.get("date", ""))
            if len(s_date) == 8 and s_date.isdigit():
                d_str = f"{s_date[:4]}-{s_date[4:6]}-{s_date[6:]}"
            else:
                d_str = s_date

            subj = el.get("su", [{}])[0].get("name", "") if isinstance(el.get("su"), list) else el.get("subject", "")
            teacher = el.get("te", [{}])[0].get("name", "") if isinstance(el.get("te"), list) else el.get("teacher", "")
            room = el.get("ro", [{}])[0].get("name", "") if isinstance(el.get("ro"), list) else el.get("room", "")
            cancelled = bool(el.get("cellState") == "CANCELLED" or el.get("isCancelled"))

            s_time = format_untis_time(el.get("startTime", "08:00"))
            e_time = format_untis_time(el.get("endTime", "08:50"))
            period = el.get("period", 1)

            if d_str and subj:
                out_list.append(
                    UntisLesson(
                        id=str(el.get("id", f"les_{len(out_list)}")),
                        date=d_str,
                        start_time=s_time,
                        end_time=e_time,
                        period_num=period,
                        subject=subj,
                        teacher=teacher,
                        room=room,
                        is_cancelled=cancelled,
                    )
                )
    except Exception:
        pass
