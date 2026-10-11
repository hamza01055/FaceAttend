"""SQLite data layer: users, students, attendance and settings."""
import datetime as dt
import os
import sqlite3
import threading
from typing import Optional

from . import auth, config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT    NOT NULL,
    full_name     TEXT    NOT NULL DEFAULT '',
    role          TEXT    NOT NULL CHECK (role IN ('admin', 'teacher')),
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS students (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_no     TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    name        TEXT    NOT NULL,
    class_name  TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS attendance (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    date        TEXT    NOT NULL,             -- YYYY-MM-DD
    time        TEXT    NOT NULL,             -- HH:MM:SS
    status      TEXT    NOT NULL DEFAULT 'Present',
    method      TEXT    NOT NULL DEFAULT 'face',   -- face | manual
    confidence  REAL,
    marked_by   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE (student_id, date)
);
CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(date);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _now() -> dt.datetime:
    return dt.datetime.now()


class DuplicateError(Exception):
    """Raised when a unique value (username / roll number) already exists."""


class Database:
    def __init__(self, path: str = config.DB_PATH):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        with self._lock, self.conn:
            self.conn.executescript(SCHEMA)
        self._seed()

    # ------------------------------------------------------------------ util
    def _q(self, sql: str, params=()) -> list:
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    def _one(self, sql: str, params=()) -> Optional[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, params).fetchone()

    def _exec(self, sql: str, params=()) -> sqlite3.Cursor:
        with self._lock, self.conn:
            return self.conn.execute(sql, params)

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def _seed(self) -> None:
        for key, value in config.DEFAULT_SETTINGS.items():
            self._exec("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
        if not self._one("SELECT 1 FROM users WHERE role = 'admin'"):
            self.add_user(config.DEFAULT_ADMIN_USER, config.DEFAULT_ADMIN_PASSWORD,
                          "Administrator", "admin")

    # -------------------------------------------------------------- settings
    def get_setting(self, key: str, default: str = "") -> str:
        row = self._one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else config.DEFAULT_SETTINGS.get(key, default)

    def get_int_setting(self, key: str, default: int) -> int:
        try:
            return int(float(self.get_setting(key, str(default))))
        except ValueError:
            return default

    def get_float_setting(self, key: str, default: float) -> float:
        try:
            return float(self.get_setting(key, str(default)))
        except ValueError:
            return default

    def set_setting(self, key: str, value) -> None:
        self._exec("INSERT INTO settings(key, value) VALUES (?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))

    # ----------------------------------------------------------------- users
    def add_user(self, username: str, password: str, full_name: str, role: str) -> int:
        username = username.strip()
        if not username or not password:
            raise ValueError("Username and password are required.")
        if role not in ("admin", "teacher"):
            raise ValueError("Role must be admin or teacher.")
        try:
            cur = self._exec(
                "INSERT INTO users(username, password_hash, full_name, role, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (username, auth.hash_password(password), full_name.strip(), role,
                 _now().isoformat(timespec="seconds")))
        except sqlite3.IntegrityError as exc:
            raise DuplicateError(f"Username '{username}' already exists.") from exc
        return cur.lastrowid

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        row = self._one("SELECT * FROM users WHERE username = ?", (username.strip(),))
        if row and auth.verify_password(password, row["password_hash"]):
            return dict(row)
        return None

    def list_users(self) -> list:
        return [dict(r) for r in self._q(
            "SELECT id, username, full_name, role, created_at FROM users ORDER BY role, username")]

    def get_user(self, user_id: int) -> Optional[dict]:
        row = self._one("SELECT * FROM users WHERE id = ?", (user_id,))
        return dict(row) if row else None

    def set_password(self, user_id: int, new_password: str) -> None:
        if not new_password:
            raise ValueError("Password cannot be empty.")
        self._exec("UPDATE users SET password_hash = ? WHERE id = ?",
                   (auth.hash_password(new_password), user_id))

    def delete_user(self, user_id: int) -> None:
        user = self.get_user(user_id)
        if not user:
            return
        if user["role"] == "admin":
            admins = self._one("SELECT COUNT(*) AS n FROM users WHERE role = 'admin'")["n"]
            if admins <= 1:
                raise ValueError("Cannot delete the last administrator.")
        self._exec("DELETE FROM users WHERE id = ?", (user_id,))

    # -------------------------------------------------------------- students
    def add_student(self, roll_no: str, name: str, class_name: str = "") -> int:
        roll_no, name = roll_no.strip(), name.strip()
        if not roll_no or not name:
            raise ValueError("Roll number and name are required.")
        try:
            cur = self._exec(
                "INSERT INTO students(roll_no, name, class_name, created_at) VALUES (?, ?, ?, ?)",
                (roll_no, name, class_name.strip(), _now().isoformat(timespec="seconds")))
        except sqlite3.IntegrityError as exc:
            raise DuplicateError(f"Roll number '{roll_no}' already exists.") from exc
        return cur.lastrowid

    def update_student(self, student_id: int, roll_no: str, name: str, class_name: str) -> None:
        roll_no, name = roll_no.strip(), name.strip()
        if not roll_no or not name:
            raise ValueError("Roll number and name are required.")
        try:
            self._exec("UPDATE students SET roll_no = ?, name = ?, class_name = ? WHERE id = ?",
                       (roll_no, name, class_name.strip(), student_id))
        except sqlite3.IntegrityError as exc:
            raise DuplicateError(f"Roll number '{roll_no}' already exists.") from exc

    def delete_student(self, student_id: int) -> None:
        self._exec("DELETE FROM students WHERE id = ?", (student_id,))

    def get_student(self, student_id: int) -> Optional[dict]:
        row = self._one("SELECT * FROM students WHERE id = ?", (student_id,))
        return dict(row) if row else None

    def list_students(self, class_name: Optional[str] = None, search: str = "") -> list:
        sql = "SELECT * FROM students WHERE 1=1"
        params: list = []
        if class_name:
            sql += " AND class_name = ?"
            params.append(class_name)
        if search:
            sql += " AND (name LIKE ? OR roll_no LIKE ?)"
            params += [f"%{search}%", f"%{search}%"]
        sql += " ORDER BY class_name, roll_no"
        return [dict(r) for r in self._q(sql, params)]

    def list_classes(self) -> list:
        return [r["class_name"] for r in self._q(
            "SELECT DISTINCT class_name FROM students WHERE class_name <> '' ORDER BY class_name")]

    def count_students(self, class_name: Optional[str] = None) -> int:
        if class_name:
            return self._one("SELECT COUNT(*) AS n FROM students WHERE class_name = ?",
                             (class_name,))["n"]
        return self._one("SELECT COUNT(*) AS n FROM students")["n"]

    # ------------------------------------------------------------ attendance
    def _status_for(self, time_str: str) -> str:
        late_after = self.get_setting("late_after").strip()
        if late_after:
            try:
                cutoff = dt.datetime.strptime(late_after, "%H:%M").time()
                if dt.datetime.strptime(time_str, "%H:%M:%S").time() > cutoff:
                    return "Late"
            except ValueError:
                pass
        return "Present"

    def mark_attendance(self, student_id: int, method: str = "face",
                        confidence: Optional[float] = None, marked_by: Optional[int] = None,
                        when: Optional[dt.datetime] = None,
                        status: Optional[str] = None) -> tuple:
        """Mark a student for the day. Returns (created: bool, record: dict).

        A student can only be marked once per date; repeated calls return the
        existing record with created=False. `status` overrides the automatic
        Present/Late decision (used for manual corrections of past dates).
        """
        when = when or _now()
        date_s, time_s = when.strftime("%Y-%m-%d"), when.strftime("%H:%M:%S")
        if status not in (None, "Present", "Late"):
            raise ValueError("status must be Present or Late")
        with self._lock:
            if not self._one("SELECT 1 FROM students WHERE id = ?", (student_id,)):
                raise ValueError("Student no longer exists.")
            existing = self._one("SELECT * FROM attendance WHERE student_id = ? AND date = ?",
                                 (student_id, date_s))
            if existing:
                return False, dict(existing)
            cur = self._exec(
                "INSERT INTO attendance(student_id, date, time, status, method, confidence, marked_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (student_id, date_s, time_s, status or self._status_for(time_s), method,
                 confidence, marked_by))
            return True, dict(self._one("SELECT * FROM attendance WHERE id = ?", (cur.lastrowid,)))

    def delete_attendance(self, attendance_id: int) -> None:
        self._exec("DELETE FROM attendance WHERE id = ?", (attendance_id,))

    def is_marked(self, student_id: int, date_s: str) -> bool:
        return self._one("SELECT 1 FROM attendance WHERE student_id = ? AND date = ?",
                         (student_id, date_s)) is not None

    def daily_sheet(self, date_s: str, class_name: Optional[str] = None) -> list:
        """Every student with their status for one date (Absent if unmarked).

        Students registered after that date are left out (they weren't
        enrolled yet), unless they were marked on it.
        """
        sql = """
            SELECT s.id AS student_id, s.roll_no, s.name, s.class_name,
                   a.id AS attendance_id, a.time, a.method, a.confidence,
                   COALESCE(a.status, 'Absent') AS status
            FROM students s
            LEFT JOIN attendance a ON a.student_id = s.id AND a.date = ?
            WHERE (substr(s.created_at, 1, 10) <= ? OR a.id IS NOT NULL)"""
        params: list = [date_s, date_s]
        if class_name:
            sql += " AND s.class_name = ?"
            params.append(class_name)
        sql += " ORDER BY s.class_name, s.roll_no"
        return [dict(r) for r in self._q(sql, params)]

    def attendance_on(self, date_s: str) -> list:
        return [dict(r) for r in self._q(
            """SELECT a.*, s.roll_no, s.name, s.class_name FROM attendance a
               JOIN students s ON s.id = a.student_id
               WHERE a.date = ? ORDER BY a.time DESC""", (date_s,))]

    def student_summary(self, start: str, end: str, class_name: Optional[str] = None) -> list:
        """Per-student totals between two dates (inclusive).

        "Working days" = distinct dates in range on which attendance was taken
        for the student's class (all classes if the student has none), counted
        only from the day the student was registered. Weekends/holidays with
        no session are therefore never counted as absences.
        """
        session_rows = self._q(
            """SELECT DISTINCT a.date, s.class_name FROM attendance a
               JOIN students s ON s.id = a.student_id WHERE a.date BETWEEN ? AND ?""",
            (start, end))
        all_dates = sorted({r["date"] for r in session_rows})
        class_dates: dict = {}
        for r in session_rows:
            class_dates.setdefault(r["class_name"], set()).add(r["date"])

        marks: dict = {}
        for r in self._q("SELECT student_id, date, status FROM attendance WHERE date BETWEEN ? AND ?",
                         (start, end)):
            marks.setdefault(r["student_id"], {})[r["date"]] = r["status"]

        rows = []
        for s in self.list_students(class_name):
            joined = s["created_at"][:10]
            own = marks.get(s["id"], {})
            dates = class_dates.get(s["class_name"], set()) if s["class_name"] else set(all_dates)
            days = {d for d in dates if d >= joined} | set(own)
            present = sum(1 for v in own.values() if v == "Present")
            late = sum(1 for v in own.values() if v == "Late")
            wd = len(days)
            rows.append({
                "student_id": s["id"], "roll_no": s["roll_no"], "name": s["name"],
                "class_name": s["class_name"], "present": present, "late": late,
                "absent": max(wd - present - late, 0), "working_days": wd,
                "percentage": round(100.0 * (present + late) / wd, 1) if wd else 0.0,
            })
        return rows

    def counts_by_day(self, days: int = 7) -> list:
        """[(date_str, count)] for the last `days` days including today."""
        today = _now().date()
        start = today - dt.timedelta(days=days - 1)
        counts = {r["date"]: r["n"] for r in self._q(
            "SELECT date, COUNT(*) AS n FROM attendance WHERE date >= ? GROUP BY date",
            (start.isoformat(),))}
        return [((start + dt.timedelta(days=i)).isoformat(),
                 counts.get((start + dt.timedelta(days=i)).isoformat(), 0)) for i in range(days)]

    def today_stats(self) -> dict:
        today = _now().strftime("%Y-%m-%d")
        total = self.count_students()
        present = self._one("SELECT COUNT(*) AS n FROM attendance WHERE date = ?", (today,))["n"]
        late = self._one("SELECT COUNT(*) AS n FROM attendance WHERE date = ? AND status = 'Late'",
                         (today,))["n"]
        return {
            "total": total,
            "present": present,
            "late": late,
            "absent": max(total - present, 0),
            "rate": round(100.0 * present / total, 1) if total else 0.0,
        }
