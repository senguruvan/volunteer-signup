import sqlite3
from typing import List, Dict, Optional, Any
from datetime import datetime, date, timedelta, timezone

DB_PATH = "tamilschool.db"

CREATE_VOLUNTEERS_SQL = """
CREATE TABLE IF NOT EXISTS volunteers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    committed_weekly INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    service_id INTEGER,
    assigned_date TEXT,
    assigned_dates TEXT
);
"""

CREATE_SERVICES_SQL = """
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    max_capacity INTEGER DEFAULT 0,
    start_date TEXT,
    end_date TEXT,
    created_at TEXT NOT NULL
);
"""

CREATE_SERVICE_DATES_SQL = """
CREATE TABLE IF NOT EXISTS service_dates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    FOREIGN KEY(service_id) REFERENCES services(id)
);
"""

CREATE_SUBSERVICES_SQL = """
CREATE TABLE IF NOT EXISTS subservices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    max_capacity INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(service_id) REFERENCES services(id)
);
"""

CREATE_SUBSERVICE_ASSIGN_SQL = """
CREATE TABLE IF NOT EXISTS subservice_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subservice_id INTEGER NOT NULL,
    volunteer_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    completed INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(subservice_id) REFERENCES subservices(id),
    FOREIGN KEY(volunteer_id) REFERENCES volunteers(id)
);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_columns():
    # Add new columns if missing (safe to run repeatedly)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(volunteers)")
    cols = [r[1] for r in cur.fetchall()]
    if 'service_id' not in cols:
        try:
            cur.execute("ALTER TABLE volunteers ADD COLUMN service_id INTEGER")
        except Exception:
            pass
    if 'assigned_date' not in cols:
        try:
            cur.execute("ALTER TABLE volunteers ADD COLUMN assigned_date TEXT")
        except Exception:
            pass
    if 'assigned_dates' not in cols:
        try:
            cur.execute("ALTER TABLE volunteers ADD COLUMN assigned_dates TEXT")
        except Exception:
            pass
    cur.execute("PRAGMA table_info(subservice_assignments)")
    cols = [r[1] for r in cur.fetchall()]
    if 'completed' not in cols:
        try:
            cur.execute("ALTER TABLE subservice_assignments ADD COLUMN completed INTEGER DEFAULT 0")
        except Exception:
            pass
    conn.commit()
    conn.close()


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(CREATE_VOLUNTEERS_SQL)
    cur.execute(CREATE_SERVICES_SQL)
    cur.execute(CREATE_SERVICE_DATES_SQL)
    cur.execute(CREATE_SUBSERVICES_SQL)
    cur.execute(CREATE_SUBSERVICE_ASSIGN_SQL)
    conn.commit()
    conn.close()
    _ensure_columns()


import json


def add_volunteer(name: str, email: str, phone: Optional[str], assigned_dates: Optional[dict], committed_weekly: bool) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        # assigned_dates expected as mapping: {service_id: [date1, date2], ...}
        assigned_dates_json = json.dumps(assigned_dates) if assigned_dates else None
        cur.execute(
            "INSERT INTO volunteers (name, email, phone, committed_weekly, created_at, assigned_dates, assigned_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, email, phone, int(committed_weekly), created_at, assigned_dates_json, None),
        )
        conn.commit()
        vid = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        raise
    conn.close()
    return {"id": vid, "name": name, "email": email}


def list_volunteers() -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT v.id, v.name, v.email, v.phone, v.committed_weekly, v.created_at, v.assigned_date, v.assigned_dates, v.service_id, s.name as service_name FROM volunteers v LEFT JOIN services s ON v.service_id = s.id ORDER BY v.created_at DESC"
    )
    rows = cur.fetchall()
    conn.close()
    result = []
    for r in rows:
        # assigned_dates is stored as JSON mapping service_id->list of dates
        assigned_dates = None
        try:
            assigned_dates = json.loads(r["assigned_dates"]) if r["assigned_dates"] else None
        except Exception:
            assigned_dates = None
        # legacy single assigned_date -> convert to mapping under key None
        if not assigned_dates and r["assigned_date"]:
            assigned_dates = {None: [r["assigned_date"]]}
        result.append({
            "id": r["id"],
            "name": r["name"],
            "email": r["email"],
            "phone": r["phone"],
            "service_id": r["service_id"],
            "service_name": r["service_name"],
            "committed_weekly": bool(r["committed_weekly"]),
            "assigned_dates": assigned_dates,
            "created_at": r["created_at"],
        })
    return result


def get_volunteer_by_email(email: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT v.id, v.name, v.email, v.phone, v.committed_weekly, v.created_at, v.assigned_date, v.assigned_dates FROM volunteers v WHERE v.email = ?", (email,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return None
    assigned_dates = None
    try:
        assigned_dates = json.loads(r["assigned_dates"]) if r["assigned_dates"] else None
    except Exception:
        assigned_dates = None
    if not assigned_dates and r["assigned_date"]:
        assigned_dates = {None: [r["assigned_date"]]}
    return {
        "id": r["id"],
        "name": r["name"],
        "email": r["email"],
        "phone": r["phone"],
        "committed_weekly": bool(r["committed_weekly"]),
        "assigned_dates": assigned_dates,
        "created_at": r["created_at"],
    }


def assign_service(email: str, service_id: int, assigned_dates_list: Optional[list], committed_weekly: bool=False) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    # load existing mapping
    cur.execute("SELECT assigned_dates FROM volunteers WHERE email = ?", (email,))
    r = cur.fetchone()
    existing = {}
    try:
        if r and r["assigned_dates"]:
            existing = json.loads(r["assigned_dates"]) or {}
    except Exception:
        existing = {}
    # update mapping for this service_id
    if assigned_dates_list:
        existing[str(service_id)] = assigned_dates_list
    else:
        # remove key if no dates provided
        existing.pop(str(service_id), None)
    assigned_dates_json = json.dumps(existing) if existing else None
    cur.execute("UPDATE volunteers SET assigned_dates = ?, committed_weekly = ? WHERE email = ?", (assigned_dates_json, int(committed_weekly), email))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed > 0


def update_volunteer(volunteer_id: int, name: str, email: str, phone: Optional[str], assigned_dates: Optional[dict], committed_weekly: bool) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    assigned_dates_json = None
    try:
        if assigned_dates:
            assigned_dates_json = json.dumps(assigned_dates)
    except Exception:
        assigned_dates_json = None
    cur.execute("UPDATE volunteers SET name = ?, email = ?, phone = ?, assigned_dates = ?, committed_weekly = ? WHERE id = ?", (name, email, phone, assigned_dates_json, int(committed_weekly), volunteer_id))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed > 0


def delete_volunteer(volunteer_id: int) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    # remove any subservice assignments for this volunteer
    cur.execute("DELETE FROM subservice_assignments WHERE volunteer_id = ?", (volunteer_id,))
    cur.execute("DELETE FROM volunteers WHERE id = ?", (volunteer_id,))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed > 0


def create_service(name: str, max_capacity: int, start_date: Optional[str], end_date: Optional[str]) -> int:
    conn = get_conn()
    cur = conn.cursor()
    created_at = datetime.now(timezone.utc).isoformat()
    cur.execute("INSERT INTO services (name, max_capacity, start_date, end_date, created_at) VALUES (?, ?, ?, ?, ?)", (name, max_capacity, start_date, end_date, created_at))
    conn.commit()
    sid = cur.lastrowid
    # populate service_dates for Saturdays between range
    if start_date and end_date:
        try:
            s = datetime.fromisoformat(start_date).date()
            e = datetime.fromisoformat(end_date).date()
            current = s
            # advance to next Saturday
            while current.weekday() != 5 and current <= e:
                current = current + timedelta(days=1)
            while current <= e:
                cur.execute("INSERT INTO service_dates (service_id, date) VALUES (?, ?)", (sid, current.isoformat()))
                current = current + timedelta(days=7)
            conn.commit()
        except Exception:
            pass
    conn.close()
    return sid


def update_service(service_id: int, name: str, max_capacity: int, start_date: Optional[str], end_date: Optional[str]) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE services SET name = ?, max_capacity = ?, start_date = ?, end_date = ? WHERE id = ?", (name, max_capacity, start_date, end_date, service_id))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed > 0


def delete_service(service_id: int) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    # delete service dates, subservices, assignments and service
    cur.execute("DELETE FROM service_dates WHERE service_id = ?", (service_id,))
    # find subservices
    cur.execute("SELECT id FROM subservices WHERE service_id = ?", (service_id,))
    subs = [r["id"] for r in cur.fetchall()]
    for sid in subs:
        cur.execute("DELETE FROM subservice_assignments WHERE subservice_id = ?", (sid,))
    cur.execute("DELETE FROM subservices WHERE service_id = ?", (service_id,))
    cur.execute("DELETE FROM services WHERE id = ?", (service_id,))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed > 0


def create_subservice(service_id: int, name: str, max_capacity: int=0) -> int:
    conn = get_conn()
    cur = conn.cursor()
    created_at = datetime.now(timezone.utc).isoformat()
    cur.execute("INSERT INTO subservices (service_id, name, max_capacity, created_at) VALUES (?, ?, ?, ?)", (service_id, name, max_capacity, created_at))
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    return sid


def update_subservice(subservice_id: int, name: str, max_capacity: int) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE subservices SET name = ?, max_capacity = ? WHERE id = ?", (name, max_capacity, subservice_id))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed > 0


def delete_subservice(subservice_id: int) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    # delete assignments for this subservice first
    cur.execute("DELETE FROM subservice_assignments WHERE subservice_id = ?", (subservice_id,))
    cur.execute("DELETE FROM subservices WHERE id = ?", (subservice_id,))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed > 0


def mark_assignment_completed(assignment_id: int, completed: bool) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE subservice_assignments SET completed = ? WHERE id = ?", (int(completed), assignment_id))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed > 0


def list_subservices(service_id: Optional[int]=None) -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    if service_id is None:
        cur.execute("SELECT id, service_id, name, max_capacity, created_at FROM subservices ORDER BY name")
    else:
        cur.execute("SELECT id, service_id, name, max_capacity, created_at FROM subservices WHERE service_id = ? ORDER BY name", (service_id,))
    rows = cur.fetchall()
    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "service_id": r["service_id"],
            "name": r["name"],
            "max_capacity": r["max_capacity"],
            "created_at": r["created_at"],
        })
    conn.close()
    return result


def assign_subservice(subservice_id: int, date_iso: str, volunteer_ids: List[int]) -> int:
    conn = get_conn()
    cur = conn.cursor()
    created_at = datetime.now(timezone.utc).isoformat()
    # remove existing assignments for this subservice and date
    cur.execute("DELETE FROM subservice_assignments WHERE subservice_id = ? AND date = ?", (subservice_id, date_iso))
    inserted = 0
    for vid in volunteer_ids:
        cur.execute("INSERT INTO subservice_assignments (subservice_id, volunteer_id, date, created_at) VALUES (?, ?, ?, ?)", (subservice_id, vid, date_iso, created_at))
        inserted += 1
    conn.commit()
    conn.close()
    return inserted


def list_subservice_assignments(subservice_id: Optional[int]=None, date_iso: Optional[str]=None) -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    q = "SELECT a.id, a.subservice_id, a.volunteer_id, a.date, a.completed, a.created_at, v.name as volunteer_name, v.email as volunteer_email FROM subservice_assignments a LEFT JOIN volunteers v ON a.volunteer_id = v.id WHERE 1=1"
    params: List[Any] = []
    if subservice_id:
        q += " AND a.subservice_id = ?"
        params.append(subservice_id)
    if date_iso:
        q += " AND a.date = ?"
        params.append(date_iso)
    q += " ORDER BY a.date, v.name"
    cur.execute(q, tuple(params))
    rows = cur.fetchall()
    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "subservice_id": r["subservice_id"],
            "volunteer_id": r["volunteer_id"],
            "volunteer_name": r["volunteer_name"],
            "volunteer_email": r["volunteer_email"],
            "date": r["date"],
            "completed": bool(r["completed"]),
            "created_at": r["created_at"],
        })
    conn.close()
    return result


def list_services() -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, max_capacity, start_date, end_date, created_at FROM services ORDER BY name")
    rows = cur.fetchall()
    services = []
    for r in rows:
        services.append({
            "id": r["id"],
            "name": r["name"],
            "max_capacity": r["max_capacity"],
            "start_date": r["start_date"],
            "end_date": r["end_date"],
            "created_at": r["created_at"],
        })
    conn.close()
    return services


def list_service_dates(service_id: int) -> List[str]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT date FROM service_dates WHERE service_id = ? ORDER BY date", (service_id,))
    rows = cur.fetchall()
    conn.close()
    return [r["date"] for r in rows]


def list_all_dates() -> List[str]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT date FROM service_dates ORDER BY date")
    rows = cur.fetchall()
    conn.close()
    return [r["date"] for r in rows]


def services_for_date(date_iso: str) -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT s.id, s.name FROM services s JOIN service_dates sd ON s.id = sd.service_id WHERE sd.date = ? ORDER BY s.name", (date_iso,))
    rows = cur.fetchall()
    conn.close()
    return [{"id": r["id"], "name": r["name"]} for r in rows]


def volunteers_by_date(date_iso: str) -> List[Dict[str, Any]]:
    # Return volunteers who have the given date in their assigned_dates mapping or assigned_date
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, phone, assigned_date, assigned_dates, committed_weekly, created_at FROM volunteers ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    result: List[Dict[str, Any]] = []
    for r in rows:
        found = False
        # check JSON mapping
        try:
            ad = json.loads(r["assigned_dates"]) if r["assigned_dates"] else None
        except Exception:
            ad = None
        if ad:
            for sid, dates in ad.items():
                if date_iso in dates:
                    found = True
                    break
        if not found and r["assigned_date"]:
            if r["assigned_date"] == date_iso:
                found = True
        if found:
            result.append({
                "id": r["id"],
                "name": r["name"],
                "email": r["email"],
                "phone": r["phone"],
                "committed_weekly": bool(r["committed_weekly"]),
                "created_at": r["created_at"],
            })
    return result


def report_volunteers(service_id: Optional[int]=None, start_date: Optional[str]=None, end_date: Optional[str]=None) -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    q = "SELECT v.id, v.name, v.email, v.phone, v.committed_weekly, v.created_at, v.assigned_date, v.assigned_dates FROM volunteers v WHERE 1=1"
    params: List[Any] = []
    if start_date:
        q += " AND v.created_at >= ?"
        params.append(start_date)
    if end_date:
        q += " AND v.created_at <= ?"
        params.append(end_date)
    q += " ORDER BY v.created_at DESC"
    cur.execute(q, tuple(params))
    rows = cur.fetchall()
    conn.close()
    result = []
    for r in rows:
        assigned_dates = None
        try:
            assigned_dates = json.loads(r["assigned_dates"]) if r["assigned_dates"] else None
        except Exception:
            assigned_dates = None
        if not assigned_dates and r["assigned_date"]:
            assigned_dates = {None: [r["assigned_date"]]}
        # if service_id filter provided, only include rows with that key
        if service_id is not None:
            if not assigned_dates or str(service_id) not in assigned_dates:
                continue
            # narrow to only the dates for that service
            service_dates = assigned_dates.get(str(service_id))
            assigned_dates = {str(service_id): service_dates}
        result.append({
            "id": r["id"],
            "name": r["name"],
            "email": r["email"],
            "phone": r["phone"],
            "assigned_dates": assigned_dates,
            "committed_weekly": bool(r["committed_weekly"]),
            "created_at": r["created_at"],
        })
    return result
