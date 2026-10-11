"""Attendance records: daily sheet and per-student report, CSV export (FR6)."""
import datetime as dt
import os
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from .. import config
from ..reports import export_csv
from . import avatars, notify
from . import theme as T
from .base import Page
from .datepicker import DatePicker
from .dialogs import PickStudentDialog
from .widgets import Button, Card, DataTable, Dropdown, Label, PageHeader, Pill

ALL = "All classes"


class RecordsPage(Page):
    title = "Records"

    def __init__(self, parent, ctx):
        super().__init__(parent, ctx)
        self.header = PageHeader(self, "Records", "Who was present, and how often.")
        self.header.pack(fill="x")
        Button(self.header.actions, "Export CSV", self.export, "secondary", "download",
               size="lg").pack()

        self.tabs = ctk.CTkSegmentedButton(
            self, values=["Daily sheet", "Student report"], command=self._switch, height=38,
            corner_radius=T.R_CONTROL, font=T.f("body_bold"),
            selected_color=T.PALETTE["surface"], selected_hover_color=T.PALETTE["surface"],
            unselected_color=T.PALETTE["surface_alt"], unselected_hover_color=T.PALETTE["border"],
            text_color=T.PALETTE["text"], fg_color=T.PALETTE["surface_alt"])
        self.tabs.pack(anchor="w", pady=(18, 14))
        self.holder = ctk.CTkFrame(self, fg_color="transparent")
        self.holder.pack(fill="both", expand=True)
        self.daily = DailyTab(self.holder, ctx)
        self.summary = SummaryTab(self.holder, ctx)
        self.tabs.set("Daily sheet")
        self._switch("Daily sheet")

    def _switch(self, name):
        for tab in (self.daily, self.summary):
            tab.pack_forget()
        tab = self.daily if name == "Daily sheet" else self.summary
        tab.pack(fill="both", expand=True)
        tab.refresh()

    def select_tab(self, index):
        name = ["Daily sheet", "Student report"][index]
        self.tabs.set(name)
        self._switch(name)

    @property
    def active(self):
        return self.daily if self.tabs.get() == "Daily sheet" else self.summary

    def on_show(self):
        classes = [ALL] + self.ctx.db.list_classes()
        for tab in (self.daily, self.summary):
            tab.class_box.configure(values=classes)
            if tab.class_var.get() not in classes:
                tab.class_var.set(ALL)
        self.active.refresh()

    def export(self):
        self.active.export()


class DailyTab(Card):
    def __init__(self, parent, ctx):
        super().__init__(parent)
        self.ctx = ctx
        self.rows = []
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(16, 6))
        self.picker = DatePicker(bar, on_change=lambda d: self.refresh())
        self.picker.pack(side="left")
        self.class_var = tk.StringVar(value=ALL)
        self.class_box = Dropdown(bar, [ALL], self.class_var, lambda v: self.refresh(), 160)
        self.class_box.pack(side="left", padx=(10, 0))
        self.remove_btn = Button(bar, "Remove mark", self.remove, "danger", "x", size="sm")
        self.remove_btn.pack(side="right")
        self.mark_btn = Button(bar, "Mark present", self.mark, "soft", "check", size="sm")
        self.mark_btn.pack(side="right", padx=(0, 8))

        self.pills = ctk.CTkFrame(self, fg_color="transparent")
        self.pills.pack(fill="x", padx=18, pady=(6, 8))
        self.summary = {}
        for key, label in (("Present", "present"), ("Late", "late"), ("Absent", "absent")):
            p = Pill(self.pills, f"0 {label}", key)
            p.pack(side="left", padx=(0, 8))
            self.summary[key] = (p, label)
        self.pct = Label(self.pills, "", "small", "muted")
        self.pct.pack(side="left", padx=(6, 0))

        self.table = DataTable(
            self, [("roll", "Roll no"), ("cls", "Class"), ("status", "Status"), ("time", "Time"),
                   ("method", "How")],
            widths={"roll": 150, "cls": 100, "status": 90, "time": 90, "method": 90},
            avatar_label="Student", avatar_width=230, height=11,
            empty=("calendar", "No students on this day",
                   "Students only appear from the day they were registered."))
        self.table.pack(fill="both", expand=True, padx=(10, 6), pady=(0, 10))
        self.tree = self.table.tree

    # compatibility helpers (used by tests and keyboard shortcuts)
    @property
    def date_var(self):
        return _DateVar(self.picker)

    def _class(self):
        return None if self.class_var.get() == ALL else self.class_var.get()

    def shift(self, days):
        self.picker.shift(days)

    def today(self):
        self.picker.set(dt.date.today())

    def refresh(self):
        d = self.picker.get()
        self.rows = self.ctx.db.daily_sheet(d.isoformat(), self._class())
        self.table.clear()
        for r in self.rows:
            st = {"id": r["student_id"], "name": r["name"]}
            how = {"face": "Camera", "manual": "Manual"}.get(r["method"], "")
            t = dt.datetime.strptime(r["time"], "%H:%M:%S").strftime("%I:%M %p").lstrip("0") \
                if r["time"] else ""
            self.table.insert(r["student_id"], (r["roll_no"], r["class_name"] or "None",
                                                r["status"], t, how),
                              text=r["name"], image=avatars.tk_avatar(self.ctx.engine, st, 30),
                              tags=(r["status"],))
        self.table.show_empty(not self.rows)
        counts = {k: sum(1 for r in self.rows if r["status"] == k) for k in self.summary}
        for k, (pill, label) in self.summary.items():
            pill.set(f"{counts[k]} {label}", k)
        total = len(self.rows)
        self.pct.configure(text=f"{100 * (counts['Present'] + counts['Late']) / total:.0f}% "
                                f"attendance" if total else "")
        self.remove_btn.configure(state="normal" if self.ctx.is_admin else "disabled")

    def mark(self):
        d = self.picker.get()
        if d > dt.date.today():
            notify.alert(self, "That date is in the future",
                         "Attendance can only be marked for today or earlier.", "warning")
            return
        sid = PickStudentDialog(self, self.ctx.db, self._class(), d.isoformat(),
                                engine=self.ctx.engine).show()
        if sid is None:
            return
        now = dt.datetime.now()
        past = d != now.date()
        when = dt.datetime.combine(d, now.time()) if past else now
        created, _ = self.ctx.db.mark_attendance(sid, method="manual",
                                                 marked_by=self.ctx.user["id"], when=when,
                                                 status="Present" if past else None)
        name = self.ctx.db.get_student(sid)["name"]
        if created:
            notify.toast(self, "Marked present", f"{name}, {T.nice_date(d)}")
        else:
            notify.toast(self, "Already marked", f"{name} is already marked on this day.", "info")
        self.refresh()

    def remove(self):
        sel = self.table.selected()
        if not sel:
            notify.toast(self, "Select a student first", "Choose a row, then remove its mark.",
                         "info")
            return
        row = next((r for r in self.rows if str(r["student_id"]) == sel), None)
        if not row or not row["attendance_id"]:
            notify.toast(self, "Nothing to remove", f"{row['name'] if row else 'This student'} "
                         "has no mark on this day.", "info")
            return
        if notify.confirm(self, "Remove this mark?",
                          f"{row['name']} will show as absent on {T.nice_date(self.picker.get())}.",
                          "Remove mark", danger=True):
            self.ctx.db.delete_attendance(row["attendance_id"])
            self.refresh()
            notify.toast(self, "Mark removed", row["name"], "info")

    def export(self):
        d = self.picker.get()
        if not self.rows:
            notify.toast(self, "Nothing to export", "There are no students on this sheet.", "info")
            return
        cls = self._class()
        default = f"attendance_{d.isoformat()}{'_' + cls if cls else ''}.csv".replace(" ", "_")
        os.makedirs(config.EXPORT_DIR, exist_ok=True)
        path = filedialog.asksaveasfilename(parent=self, initialdir=config.EXPORT_DIR,
                                            initialfile=default, defaultextension=".csv",
                                            filetypes=[("CSV (Excel)", "*.csv")])
        if not path:
            return
        n = export_csv(path, ["Date", "Roll No", "Name", "Class", "Status", "Time", "Method"],
                       [(d.isoformat(), r["roll_no"], r["name"], r["class_name"], r["status"],
                         r["time"], r["method"]) for r in self.rows])
        notify.toast(self, "Exported", f"{n} rows saved to {os.path.basename(path)}")


class SummaryTab(Card):
    def __init__(self, parent, ctx):
        super().__init__(parent)
        self.ctx = ctx
        self.rows = []
        today = dt.date.today()
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(16, 6))
        self.from_picker = DatePicker(bar, value=today.replace(day=1), compact=True,
                                      on_change=lambda d: self.refresh())
        self.from_picker.pack(side="left")
        Label(bar, "to", "body", "muted").pack(side="left", padx=8)
        self.to_picker = DatePicker(bar, value=today, compact=True,
                                    on_change=lambda d: self.refresh())
        self.to_picker.pack(side="left")
        self.class_var = tk.StringVar(value=ALL)
        self.class_box = Dropdown(bar, [ALL], self.class_var, lambda v: self.refresh(), 150)
        self.class_box.pack(side="left", padx=(10, 0))
        Button(bar, "Last 30 days", self.last_30, "ghost", size="sm").pack(side="right")
        Button(bar, "This month", self.this_month, "ghost", size="sm").pack(side="right")

        self.info = Label(self, "", "small", "muted")
        self.info.pack(anchor="w", padx=20, pady=(6, 8))
        self.table = DataTable(
            self, [("roll", "Roll no"), ("cls", "Class"), ("present", "On time"),
                   ("late", "Late"), ("absent", "Absent"), ("pct", "Attendance")],
            widths={"roll": 140, "cls": 100, "present": 80, "late": 70, "absent": 80, "pct": 100},
            anchors={"present": "center", "late": "center", "absent": "center", "pct": "center"},
            avatar_label="Student", avatar_width=220, height=11,
            empty=("bar-chart-2", "No students yet", ""))
        self.table.pack(fill="both", expand=True, padx=(10, 6), pady=(0, 6))
        Label(self, "Below 75% is shown in red. Absences only count days the student's class "
                    "met, from the day they were registered.", "small", "faint").pack(
            anchor="w", padx=20, pady=(0, 14))

    # compatibility helpers
    @property
    def from_var(self):
        return _DateVar(self.from_picker)

    @property
    def to_var(self):
        return _DateVar(self.to_picker)

    def this_month(self):
        t = dt.date.today()
        self.from_picker.set(t.replace(day=1), notify=False)
        self.to_picker.set(t, notify=False)
        self.refresh()

    def last_30(self):
        t = dt.date.today()
        self.from_picker.set(t - dt.timedelta(days=29), notify=False)
        self.to_picker.set(t, notify=False)
        self.refresh()

    def _range(self):
        a, b = self.from_picker.get(), self.to_picker.get()
        if a > b:
            notify.alert(self, "Check the dates", "The start date must be before the end date.",
                         "warning")
            return None
        return a, b

    def refresh(self):
        rng = self._range()
        if not rng:
            return
        cls = None if self.class_var.get() == ALL else self.class_var.get()
        self.rows = self.ctx.db.student_summary(rng[0].isoformat(), rng[1].isoformat(), cls)
        self.table.clear()
        for r in self.rows:
            st = {"id": r["student_id"], "name": r["name"]}
            low = r["working_days"] and r["percentage"] < 75
            self.table.insert(r["student_id"], (
                r["roll_no"], r["class_name"] or "None", r["present"], r["late"], r["absent"],
                f"{r['percentage']:.0f}%" if r["working_days"] else "No sessions"),
                text=r["name"], image=avatars.tk_avatar(self.ctx.engine, st, 30),
                tags=("warn",) if low else ())
        self.table.show_empty(not self.rows)
        days = max((r["working_days"] for r in self.rows), default=0)
        counted = [r for r in self.rows if r["working_days"]]
        avg = sum(r["percentage"] for r in counted) / len(counted) if counted else 0
        self.info.configure(text=f"{days} class session{'s' if days != 1 else ''} between "
                                 f"{rng[0]:%d %b} and {rng[1]:%d %b %Y}. "
                                 f"Average attendance {avg:.0f}%.")

    def export(self):
        rng = self._range()
        if not rng:
            return
        if not self.rows:
            notify.toast(self, "Nothing to export", "There are no students in this report.", "info")
            return
        os.makedirs(config.EXPORT_DIR, exist_ok=True)
        path = filedialog.asksaveasfilename(
            parent=self, initialdir=config.EXPORT_DIR, defaultextension=".csv",
            initialfile=f"attendance_report_{rng[0]}_to_{rng[1]}.csv",
            filetypes=[("CSV (Excel)", "*.csv")])
        if not path:
            return
        n = export_csv(path, ["Roll No", "Name", "Class", "Present", "Late", "Absent",
                              "Working Days", "Attendance %"],
                       [(r["roll_no"], r["name"], r["class_name"], r["present"], r["late"],
                         r["absent"], r["working_days"], r["percentage"]) for r in self.rows])
        notify.toast(self, "Exported", f"{n} rows saved to {os.path.basename(path)}")


class _DateVar:
    """Lets callers read/set a DatePicker like a StringVar of YYYY-MM-DD."""

    def __init__(self, picker):
        self.picker = picker

    def get(self):
        return self.picker.get().isoformat()

    def set(self, text):
        d = T.parse_date(text)
        if d:
            self.picker.value = d          # set without clamping (for range checks)
            self.picker._render()
