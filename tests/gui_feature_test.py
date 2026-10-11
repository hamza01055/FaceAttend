"""End-to-end feature test: drives the real app window through every feature.

Run:   python tests/gui_feature_test.py
(Linux servers: xvfb-run -a python tests/gui_feature_test.py)

Uses a temporary data folder and short videos of the test photos instead of a
webcam, so it never touches your real database. Prints PASS/FAIL per check and
saves feature_results.csv (and screenshots if FACEATTEND_SNAP=1) to the temp folder.
"""
import csv
import datetime as dt
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback

import cv2
import numpy as np

S = tempfile.mkdtemp(prefix="faceattend_test_")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
data = os.path.join(S, "data")
os.environ["FACEATTEND_DATA_DIR"] = data
sys.path.insert(0, ROOT)


def make_video(img, name, frames=45):
    path = os.path.join(S, name)
    w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), 15, (640, 480))
    for i in range(frames):
        f = np.full((480, 640, 3), 40, np.uint8)
        dx = int(15 * np.sin(i / 6))
        bright = 0.85 + 0.15 * np.sin(i / 9)
        f[:, 64 + dx:576 + dx] = cv2.convertScaleAbs(cv2.resize(img, (512, 480)), alpha=bright)
        w.write(f)
    w.release()
    return path


astro = cv2.imread(f"{ROOT}/tests/fixtures/face_sample.jpg")
camman = cv2.imread(f"{ROOT}/tests/fixtures/face_other.jpg")[30:330, 80:400]  # face ~100 px
VID_A, VID_B = make_video(astro, "vid_a.avi"), make_video(camman, "vid_b.avi")
VID_EMPTY = make_video(np.full((512, 512, 3), 90, np.uint8), "vid_empty.avi", 10)

from app import config  # noqa: E402
config.ensure_dirs()
from app.database import Database  # noqa: E402
from app.face_engine import FaceEngine  # noqa: E402
from app.ui import admin as admin_mod  # noqa: E402
from app.ui import dialogs, main_window, notify  # noqa: E402
from app.ui import records as rec_mod  # noqa: E402
from app.ui import students as students_mod  # noqa: E402
from app.ui import attendance as att_mod  # noqa: E402

# ---- capture all user feedback instead of showing it
LOG = []
ASK = []
notify.toast = lambda w, t, m="", kind="success", duration=0: LOG.append(("toast", t, m))
notify.alert = lambda w, t, m="", kind="error": LOG.append(("alert", t, m))
notify.confirm = lambda w, t, m="", confirm_text="", danger=False: (
    LOG.append(("ask", t, m)), ASK.pop(0) if ASK else False)[1]

db = Database(config.DB_PATH)
eng = FaceEngine()
app = main_window.App(db, eng)
app.state("normal")
app.geometry("1366x768+0+0")
results = []


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def snap(name):
    pump(0.3)
    if os.environ.get("FACEATTEND_SNAP") != "1":
        return
    try:
        from PIL import ImageGrab
        kw = {"xdisplay": os.environ["DISPLAY"]} if os.environ.get("DISPLAY") else {}
        ImageGrab.grab(bbox=(0, 0, 1366, 768), **kw).save(os.path.join(S, "ft_" + name))
    except Exception:  # noqa: BLE001
        pass


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))


def last(kind=None):
    for e in reversed(LOG):
        if kind is None or e[0] == kind:
            return e
    return ("", "", "")


def logged(kind, title, text_in=None):
    return any(e[0] == kind and e[1] == title and (text_in is None or text_in in e[2]) for e in LOG)


def step(fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        check(fn.__name__ + " (crashed)", False, repr(exc))


def fake_dialog(cls, value):
    orig = cls.show
    cls.show = lambda self: (self.destroy(), value)[1]
    return lambda: setattr(cls, "show", orig)


lf = app.login_frame


def do_login(u, p):
    lf.username.delete(0, "end")
    lf.username.insert(0, u)
    lf.password.delete(0, "end")
    lf.password.insert(0, p)
    lf.login()
    pump(0.3)


def sid_of(name):
    return db.list_students(search=name)[0]["id"]


TODAY = dt.date.today().isoformat()


# ------------------------------------------------------------------ 1. login
def t_login():
    pump(0.4)
    do_login("admin", "wrong")
    check("Login: wrong password rejected", app.ctx.user is None and "don't match" in lf.error.cget("text"))
    for _ in range(4):
        do_login("admin", "wrong")
    check("Login: locked after 5 failures", "Locked" in lf.error.cget("text"))
    do_login("admin", "admin123")
    check("Login: blocked while locked, even with correct password", app.ctx.user is None)
    lf.locked_until = 0
    do_login("admin", "admin123")
    pump(1.0)
    check("Login: admin signs in", app.ctx.user and app.ctx.user["role"] == "admin")
    check("Login: default-password reminder shown", logged("toast", "Change the default password"))
    check("Admin sees all 6 screens", list(app.shell.nav_buttons) ==
          ["dashboard", "attendance", "students", "records", "users", "settings"])
    check("Show/hide password button", (lf._toggle_pw(), lf.password.cget("show") == "")[1])
    lf._toggle_pw()


step(t_login)

sp = None


# --------------------------------------------------------------- 2. students
def t_students():
    global sp
    app.shell.show("students")
    pump(0.3)
    sp = app.shell.pages["students"]
    for roll, name, cls in [("S25-001", "Nida Batool", "ADP-7A"), ("S25-002", "Ayesha Khan", "ADP-7A"),
                            ("S25-003", "Usman Tariq", "ADP-7B")]:
        undo = fake_dialog(dialogs.StudentDialog, {"roll_no": roll, "name": name, "class_name": cls})
        ASK.append(False)
        sp.add()
        undo()
        pump(0.1)
    check("Add student x3", db.count_students() == 3, db.count_students())
    check("Offers face capture right after adding", logged("ask", "Capture their face now?"))
    check("Confirmation toast after adding", logged("toast", "Student added"))
    undo = fake_dialog(dialogs.StudentDialog, {"roll_no": "s25-001", "name": "Dup", "class_name": ""})
    sp.add()
    undo()
    check("Duplicate roll number rejected", last("alert")[1] == "Couldn't add the student"
          and db.count_students() == 3)
    sid = sid_of("Ayesha")
    sp.table.select(sid)
    pump(0.2)
    check("Selecting a student opens the detail panel", sp.capture_btn is not None
          and sp.capture_btn.winfo_ismapped())
    undo = fake_dialog(dialogs.StudentDialog, {"roll_no": "S25-002", "name": "Ayesha Noor",
                                               "class_name": "ADP-7A"})
    sp.edit()
    undo()
    check("Edit student", db.get_student(sid)["name"] == "Ayesha Noor")
    sp.search.insert("usman")
    sp.refresh()
    check("Search students", len(sp.tree.get_children()) == 1)
    sp.search.clear()
    sp.class_var.set("ADP-7A")
    sp.refresh()
    check("Filter by class", len(sp.tree.get_children()) == 2)
    sp.class_var.set(students_mod.ALL)
    sp.refresh()
    snap("students.png")


step(t_students)


def enroll(name, video, answers=()):
    os.environ["FACEATTEND_CAMERA"] = video
    s = db.get_student(sid_of(name))
    ASK.extend(answers)
    dlg = dialogs.EnrollDialog(sp, app.ctx, s)
    dlg.update_idletasks()
    dlg.deiconify()
    pump(1.2)
    dlg.start_capture()
    t0 = time.time()
    while dlg.winfo_exists() and time.time() - t0 < 40:
        if dlg.capturing and len(dlg.samples) == 6 and name == "Nida Batool":
            snap("enroll.png")
        pump(0.05)
    return not dlg.winfo_exists()


# ------------------------------------------------------------- 3. enrolment
def t_enroll():
    closed = enroll("Nida Batool", VID_A)
    n = eng.sample_count(sid_of("Nida Batool"))
    check("Capture face (webcam enrolment) saves samples", closed and n >= 15, n)
    check("Model updated after enrolment", eng.is_trained and sid_of("Nida Batool") in eng.enrolled_ids)
    check("Enrolment confirmation shown", logged("toast", "Face captured"))


step(t_enroll)

ap_ = None


def run_camera(video, seconds=4, cls=None):
    global ap_
    os.environ["FACEATTEND_CAMERA"] = video
    app.shell.show("attendance")
    pump(0.3)
    ap_ = app.shell.pages["attendance"]
    ap_.class_var.set(cls or att_mod.ALL)
    ap_._refresh_session()
    ap_.start()
    pump(seconds)


# ------------------------------------------------------------- 4. attendance
def t_stranger():
    run_camera(VID_B, 5)
    marked = db.attendance_on(TODAY)
    check("SECURITY: unenrolled stranger is NOT marked", len(marked) == 0, [m["name"] for m in marked])
    snap("attendance_stranger.png")
    ap_.stop()


step(t_stranger)


def t_class_filter():
    run_camera(VID_A, 4, cls="ADP-7B")
    check("Class filter: student from another class is not marked",
          not db.is_marked(sid_of("Nida Batool"), TODAY))
    ap_.stop()


step(t_class_filter)


def t_attendance():
    run_camera(VID_A, 5)
    rec = [m for m in db.attendance_on(TODAY) if m["name"] == "Nida Batool"]
    check("Enrolled student recognised and marked automatically", len(rec) == 1)
    if rec:
        check("Record has date, time, method=face, similarity score",
              rec[0]["date"] == TODAY and len(rec[0]["time"]) == 8 and rec[0]["method"] == "face"
              and rec[0]["confidence"] and rec[0]["confidence"] >= 0.4, rec[0])
    check("Check-in card shows the student", ap_.hero_name.cget("text") == "Nida Batool")
    snap("attendance.png")
    pump(2)
    check("Marked only once per day (no duplicates while camera keeps running)",
          len([m for m in db.attendance_on(TODAY) if m["name"] == "Nida Batool"]) == 1)
    check("Live list shows the marked student", len(ap_.rows) == 1)
    ap_.stop()
    check("Stop camera", ap_.camera is None)


step(t_attendance)


def t_no_face():
    run_camera(VID_EMPTY, 1.5)
    check("Empty frame: shows 'No face in view'", "No face" in ap_.status.cget("text"))
    ap_.stop()


step(t_no_face)


def t_second():
    app.shell.show("students")
    pump(0.2)
    enroll("Usman Tariq", VID_B)
    check("Second student enrolled", sid_of("Usman Tariq") in eng.enrolled_ids)
    before = eng.sample_count(sid_of("Ayesha"))
    enroll("Ayesha Noor", VID_A, answers=[False])     # Nida's face for Ayesha -> warn
    check("Duplicate-face guard: warns when face belongs to another student",
          logged("ask", "Face already registered", "Nida"))
    check("Duplicate-face guard: nothing saved when admin says No",
          eng.sample_count(sid_of("Ayesha")) == before)
    run_camera(VID_B, 5)
    check("Second student recognised and marked", db.is_marked(sid_of("Usman Tariq"), TODAY))
    m = [r for r in db.attendance_on(TODAY) if r["name"] == "Usman Tariq"]
    check("...and not confused with the first student", len(m) == 1 and
          len([r for r in db.attendance_on(TODAY) if r["name"] == "Nida Batool"]) == 1)
    ap_.stop()


step(t_second)


def t_manual():
    app.shell.show("attendance")
    pump(0.2)
    undo = fake_dialog(dialogs.PickStudentDialog, sid_of("Ayesha"))
    ap_.manual_mark()
    undo()
    rec = [r for r in db.attendance_on(TODAY) if r["name"] == "Ayesha Noor"]
    check("Manual mark from attendance screen", len(rec) == 1 and rec[0]["method"] == "manual")
    undo = fake_dialog(dialogs.PickStudentDialog, sid_of("Ayesha"))
    ap_.manual_mark()
    undo()
    check("Manual mark twice -> 'Already checked in'", last("toast")[1] == "Already checked in")


step(t_manual)


def t_import():
    app.shell.show("students")
    pump(0.2)
    sid = sid_of("Ayesha")
    sp.table.select(sid)
    pump(0.1)
    orig = students_mod.filedialog.askopenfilenames
    blank = os.path.join(S, "blank.png")
    cv2.imwrite(blank, np.full((300, 300, 3), 200, np.uint8))
    students_mod.filedialog.askopenfilenames = lambda **k: (blank,)
    sp.import_photos()
    check("Import photos: rejects photo with no face", last("alert")[1] == "No face found in those photos")
    students_mod.filedialog.askopenfilenames = lambda **k: (f"{ROOT}/tests/fixtures/face_other.jpg", blank)
    sp.import_photos()
    pump(2)
    students_mod.filedialog.askopenfilenames = orig
    check("Import photos: adds face from photo, skips bad one",
          eng.sample_count(sid) >= 1 and logged("toast", "Photos imported", "skipped"))


step(t_import)

rp = None


# ---------------------------------------------------------------- 5. records
def t_records():
    global rp
    app.shell.show("records")
    pump(0.3)
    rp = app.shell.pages["records"]
    d = rp.daily
    present = [r for r in d.rows if r["status"] != "Absent"]
    check("Daily sheet lists today's students", len(d.rows) == 3 and len(present) == 3, len(present))
    snap("records_daily.png")
    d.shift(-1)
    yday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    check("Daily sheet: previous-day navigation", d.date_var.get() == yday)
    check("Students registered today are not shown absent for yesterday", len(d.rows) == 0, len(d.rows))
    d.today()
    d.picker.set(dt.date.today() + dt.timedelta(days=1))
    check("Date picker won't go into the future", d.picker.get() == dt.date.today())
    sid = sid_of("Ayesha")
    d.refresh()
    d.tree.selection_set(str(sid))
    ASK.append(True)
    d.remove()
    check("Remove mark (admin correction)", not db.is_marked(sid, TODAY))
    undo = fake_dialog(dialogs.PickStudentDialog, sid)
    d.mark()
    undo()
    check("Mark present from Records", db.is_marked(sid, TODAY))
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    d.date_var.set(tomorrow)
    undo = fake_dialog(dialogs.PickStudentDialog, sid)
    d.mark()
    undo()
    check("Future date marking blocked", last("alert")[1] == "That date is in the future"
          and not db.is_marked(sid, tomorrow))
    d.today()
    out = os.path.join(S, "daily.csv")
    rec_mod.filedialog.asksaveasfilename = lambda **k: out
    rp.export()
    rows = list(csv.reader(open(out, encoding="utf-8-sig")))
    check("Export daily sheet to CSV", rows[0][0] == "Date" and len(rows) == 4, len(rows))
    rp.select_tab(1)
    pump(0.2)
    s = rp.summary
    s.this_month()
    check("Student report (this month)", len(s.rows) == 3 and all(r["percentage"] == 100.0 for r in s.rows),
          [(r["name"], r["percentage"]) for r in s.rows])
    s.last_30()
    out2 = os.path.join(S, "summary.csv")
    rec_mod.filedialog.asksaveasfilename = lambda **k: out2
    rp.export()
    rows = list(csv.reader(open(out2, encoding="utf-8-sig")))
    check("Export student report to CSV", rows[0][-1] == "Attendance %" and len(rows) == 4)
    s.from_var.set("2026-12-01")
    s.to_var.set("2026-01-01")
    s.refresh()
    check("Report rejects start date after end date", last("alert")[1] == "Check the dates")
    s.this_month()
    snap("records_summary.png")


step(t_records)


# -------------------------------------------------------------- 6. dashboard
def t_dashboard():
    app.shell.show("dashboard")
    pump(0.5)
    dp = app.shell.pages["dashboard"]
    check("Dashboard: today's total", dp.big.cget("text") == "3 of 3", dp.big.cget("text"))
    check("Dashboard: check-ins list", "3" in dp.count_pill.cget("text"))
    check("Dashboard: greeting uses the user's name", "Administrator" in dp.header.title.cget("text"))
    snap("dashboard.png")


step(t_dashboard)


# ---------------------------------------------------- 7. users & settings
def t_users():
    app.shell.show("users")
    pump(0.2)
    up = app.shell.pages["users"]
    undo = fake_dialog(dialogs.UserDialog, {"username": "teacher", "full_name": "Dr. Rana Nazeer",
                                            "password": "teach123", "role": "teacher"})
    up.add()
    undo()
    check("Add teacher account", db.authenticate("teacher", "teach123") is not None)
    undo = fake_dialog(dialogs.UserDialog, {"username": "TEACHER", "full_name": "", "password": "xxxx",
                                            "role": "teacher"})
    up.add()
    undo()
    check("Duplicate username rejected", last("alert")[1] == "Couldn't add the user")
    tid = db.authenticate("teacher", "teach123")["id"]
    up.on_show()
    up.tree.selection_set(str(tid))
    undo = fake_dialog(dialogs.PasswordDialog, {"current": "", "new": "newpass1"})
    up.reset()
    undo()
    check("Admin resets a user's password", db.authenticate("teacher", "newpass1") is not None)
    up.tree.selection_set(str(app.ctx.user["id"]))
    up.delete()
    check("Cannot delete own account", last("alert")[1] == "You can't delete yourself")
    undo = fake_dialog(dialogs.UserDialog, {"username": "temp", "full_name": "", "password": "temp1",
                                            "role": "teacher"})
    up.add()
    undo()
    tmp = db.authenticate("temp", "temp1")["id"]
    up.on_show()
    up.tree.selection_set(str(tmp))
    ASK.append(True)
    up.delete()
    check("Delete user", db.get_user(tmp) is None)
    snap("users.png")


step(t_users)


def t_settings():
    app.shell.show("settings")
    pump(0.2)
    st = app.shell.pages["settings"]
    st.late_on.set(True)
    st._toggle_late()
    st.late.delete(0, "end")
    st.late.insert(0, "25:99")
    st.save()
    check("Settings: invalid late time rejected", last("alert")[1] == "Check the late time")
    st.late.delete(0, "end")
    st.late.insert(0, "08:30")
    st.threshold.set(0.45)
    st.save()
    check("Settings: saved", db.get_setting("late_after") == "08:30" and
          db.get_setting("match_threshold") == "0.45")
    check("Threshold used by app", abs(app.ctx.match_threshold() - 0.45) < 1e-9)
    st.threshold.set(0.40)
    st.late_on.set(False)
    st.save()
    check("Settings: switching off late arrivals clears the rule", db.get_setting("late_after") == "")
    out = os.path.join(S, "backup.db")
    admin_mod.filedialog.asksaveasfilename = lambda **k: out
    st.backup()
    n = sqlite3.connect(out).execute("SELECT COUNT(*) FROM students").fetchone()[0]
    check("Backup database creates a working copy", n == 3)
    snap("settings.png")


step(t_settings)


def t_theme():
    app.shell.toggle_mode()
    pump(0.6)
    from app.ui import theme as T
    check("Dark mode switch", T.is_dark() and db.get_setting("appearance") == "Dark")
    snap("settings_dark.png")
    app.shell.show("dashboard")
    pump(0.4)
    app.shell.toggle_mode()
    pump(0.4)
    check("Back to light mode", not T.is_dark() and db.get_setting("appearance") == "Light")


step(t_theme)


def t_change_pw():
    undo = fake_dialog(dialogs.PasswordDialog, {"current": "bad", "new": "secure99"})
    app.shell.change_password()
    undo()
    check("Change password: wrong current password rejected", last("alert")[1] == "Current password is wrong")
    undo = fake_dialog(dialogs.PasswordDialog, {"current": "admin123", "new": "secure99"})
    app.shell.change_password()
    undo()
    check("Change own password", db.authenticate("admin", "secure99") is not None)


step(t_change_pw)


# ------------------------------------------------------------ 8. teacher role
def t_teacher():
    app.logout()
    pump(0.3)
    check("Logout returns to sign-in", app.ctx.user is None and lf.winfo_ismapped())
    check("Default-login hint hidden once password changed", lf.hint.cget("text") == "")
    do_login("teacher", "newpass1")
    pump(0.4)
    check("Teacher signs in", app.ctx.user and app.ctx.user["role"] == "teacher")
    check("Teacher cannot see Users/Settings", list(app.shell.nav_buttons) ==
          ["dashboard", "attendance", "students", "records"])
    app.shell.show("students")
    pump(0.3)
    tsp = app.shell.pages["students"]
    tsp.table.select(tsp.tree.get_children()[0])
    pump(0.2)
    check("Teacher cannot add/edit/delete/capture students",
          all(str(b.cget("state")) == "disabled" for b in
              (tsp.capture_btn, tsp.edit_btn, tsp.delete_btn, tsp.retrain_btn))
          and not tsp.add_btn.winfo_ismapped())
    app.shell.show("records")
    pump(0.2)
    check("Teacher cannot remove attendance marks",
          str(app.shell.pages["records"].daily.remove_btn.cget("state")) == "disabled")
    snap("teacher_students.png")
    app.logout()
    do_login("admin", "secure99")


step(t_teacher)


# -------------------------------------------------------- 9. delete student
def t_delete():
    app.shell.show("students")
    pump(0.2)
    sp2 = app.shell.pages["students"]
    sid = sid_of("Usman")
    sp2.table.select(sid)
    pump(0.2)
    ASK.append(True)
    sp2.delete()
    pump(3)
    check("Delete student removes record + face samples", db.get_student(sid) is None
          and eng.sample_count(sid) == 0)
    check("Deleted student removed from recognition model", sid not in eng.enrolled_ids)
    run_camera(VID_B, 4)
    check("Deleted student's face no longer marks anyone",
          all(r["name"] != "Usman Tariq" for r in db.attendance_on(TODAY))
          and len(db.attendance_on(TODAY)) == 2)
    ap_.stop()


step(t_delete)


def t_restart():
    eng2 = FaceEngine()
    check("Model persists after restart", sid_of("Nida") in eng2.enrolled_ids)


step(t_restart)

app.on_close()
passed = sum(1 for r in results if r[1])
print(f"\n==== {passed}/{len(results)} checks passed ====   (output folder: {S})")
with open(os.path.join(S, "feature_results.csv"), "w", newline="") as fh:
    csv.writer(fh).writerows([("check", "result", "detail")] +
                             [(n, "PASS" if ok else "FAIL", d) for n, ok, d in results])
shutil.copy(os.path.join(S, "feature_results.csv"), os.path.join(S, "..", "faceattend_last_results.csv")) \
    if os.access(os.path.join(S, ".."), os.W_OK) else None
sys.exit(0 if passed == len(results) else 1)
