"""Students: list on the left, the selected student's details and actions on
the right (add / edit / delete, capture or import face photos) — FR5."""
import datetime as dt
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from ..database import DuplicateError
from . import avatars, notify
from . import theme as T
from .base import Page
from .dialogs import EnrollDialog, StudentDialog
from .widgets import (Button, Card, DataTable, Divider, Dropdown, EmptyState, Label, PageHeader,
                      Pill, SearchEntry)

ALL = "All classes"


class StudentsPage(Page):
    title = "Students"

    def __init__(self, parent, ctx):
        super().__init__(parent, ctx)
        self.header = PageHeader(self, "Students", "")
        self.header.pack(fill="x")
        self.add_btn = Button(self.header.actions, "Add student", self.add, "primary",
                              "user-plus", size="lg")
        self.add_btn.pack()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, pady=(20, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        # ---- list
        listcard = Card(body)
        listcard.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        bar = ctk.CTkFrame(listcard, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(16, 8))
        self.search = SearchEntry(bar, "Search by name or roll number", self.refresh, width=280)
        self.search.pack(side="left")
        self.class_var = tk.StringVar(value=ALL)
        self.class_box = Dropdown(bar, [ALL], self.class_var, lambda v: self.refresh(), 160)
        self.class_box.pack(side="left", padx=(10, 0))
        self.retrain_btn = Button(bar, "Update model", self.retrain, "ghost", "refresh-cw",
                                  size="sm")
        self.retrain_btn.pack(side="right")
        self.table = DataTable(
            listcard, [("roll", "Roll no"), ("cls", "Class"), ("face", "Face")],
            widths={"roll": 150, "cls": 110, "face": 120}, avatar_label="Name",
            avatar_width=230, height=12,
            empty=("users", "No students yet", "Add your first student to get started."))
        self.table.pack(fill="both", expand=True, padx=(10, 6), pady=(0, 10))
        self.table.tree.bind("<<TreeviewSelect>>", lambda e: self._show_detail())
        self.table.tree.bind("<Double-1>", lambda e: self.edit())
        self.tree = self.table.tree

        # ---- detail panel
        self.detail = Card(body, radius=T.R_HERO, width=310)
        self.detail.grid(row=0, column=1, sticky="ns")
        self.detail.grid_propagate(False)
        self.detail.pack_propagate(False)
        self._detail_empty()

        # action buttons (created once, packed into the detail panel when relevant)
        self.capture_btn = self.import_btn = self.edit_btn = self.delete_btn = None

    # ---------------------------------------------------------------- view
    def on_show(self):
        classes = self.ctx.db.list_classes()
        self.class_box.configure(values=[ALL] + classes)
        if self.class_var.get() not in [ALL] + classes:
            self.class_var.set(ALL)
        if not self.ctx.is_admin:
            self.add_btn.pack_forget()
            self.retrain_btn.configure(state="disabled")
        self.refresh()

    def refresh(self):
        cls = None if self.class_var.get() == ALL else self.class_var.get()
        students = self.ctx.db.list_students(cls, self.search.get())
        sel = self.table.selected()
        self.table.clear()
        enrolled = 0
        for s in students:
            n = self.ctx.engine.sample_count(s["id"])
            enrolled += n > 0
            self.table.insert(s["id"], (s["roll_no"], s["class_name"] or "None",
                                        "Captured" if n else "Not captured"),
                              text=s["name"], image=avatars.tk_avatar(self.ctx.engine, s, 30),
                              tags=() if n else ("dim",))
        total = self.ctx.db.count_students()
        self.header.subtitle.configure(
            text=f"{total} registered, {self._count_enrolled()} with a face captured")
        filtered = bool(self.search.get()) or cls
        self.table.show_empty(not students,
                              title="No matches" if filtered and total else None,
                              text="Try another name, roll number or class."
                              if filtered and total else None)
        if sel and self.table.tree.exists(sel):
            self.table.select(sel)
        else:
            self._detail_empty()

    def _count_enrolled(self):
        return sum(1 for s in self.ctx.db.list_students() if self.ctx.engine.sample_count(s["id"]))

    def _selected(self):
        sel = self.table.selected()
        return self.ctx.db.get_student(int(sel)) if sel else None

    # -------------------------------------------------------------- detail
    def _clear_detail(self):
        for w in self.detail.winfo_children():
            w.destroy()

    def _detail_empty(self):
        self._clear_detail()
        EmptyState(self.detail, "user", "Select a student",
                   "Their face photo, attendance and actions appear here.", wrap=230).place(
            relx=0.5, rely=0.42, anchor="center")

    def _show_detail(self):
        s = self._selected()
        if not s:
            return self._detail_empty()
        self._clear_detail()
        d = self.detail
        n = self.ctx.engine.sample_count(s["id"])
        top = ctk.CTkFrame(d, fg_color="transparent")
        top.pack(fill="x", padx=22, pady=(24, 0))
        ring = T.c("present") if n else T.c("border")
        ctk.CTkLabel(top, text="", image=avatars.ctk_avatar(self.ctx.engine, s, 96, ring)).pack(
            anchor="w")
        Label(top, s["name"], "h2", wraplength=260).pack(anchor="w", pady=(12, 0))
        Label(top, s["roll_no"], "body", "muted").pack(anchor="w")
        pills = ctk.CTkFrame(top, fg_color="transparent")
        pills.pack(anchor="w", pady=(10, 0))
        if s["class_name"]:
            Pill(pills, s["class_name"], "info").pack(side="left", padx=(0, 6))
        Pill(pills, "Face captured" if n else "No face yet", "Present" if n else "Absent").pack(
            side="left")

        today = dt.date.today()
        rows = self.ctx.db.student_summary(today.replace(day=1).isoformat(), today.isoformat())
        me = next((r for r in rows if r["student_id"] == s["id"]), None)
        stats = ctk.CTkFrame(d, fg_color=T.PALETTE["surface_alt"], corner_radius=T.R_CONTROL)
        stats.pack(fill="x", padx=22, pady=(18, 0))
        for i, (value, label) in enumerate((
                (f"{me['percentage']:.0f}%" if me and me["working_days"] else "–", "this month"),
                (str((me["present"] + me["late"]) if me else 0), "days present"),
                (str(n), "face images"))):
            box = ctk.CTkFrame(stats, fg_color="transparent")
            box.grid(row=0, column=i, padx=10, pady=12, sticky="w")
            stats.columnconfigure(i, weight=1)
            Label(box, value, "h2").pack(anchor="w")
            Label(box, label, "small", "muted").pack(anchor="w")

        acts = ctk.CTkFrame(d, fg_color="transparent")
        acts.pack(fill="x", padx=22, pady=(20, 0))
        admin = self.ctx.is_admin
        self.capture_btn = Button(acts, "Recapture face" if n else "Capture face", self.capture,
                                  "primary" if not n else "secondary", "aperture")
        self.import_btn = Button(acts, "Import photos", self.import_photos, "secondary", "image")
        self.edit_btn = Button(acts, "Edit details", self.edit, "secondary", "edit-2")
        self.delete_btn = Button(d, "Delete student", self.delete, "danger", "trash-2")
        for b in (self.capture_btn, self.import_btn, self.edit_btn):
            b.pack(fill="x", pady=4)
        if admin:
            # destructive action kept apart at the bottom of the panel
            self.delete_btn.pack(fill="x", padx=22, pady=(0, 22), side="bottom")
            Divider(d).pack(fill="x", padx=22, pady=(14, 12), side="bottom")
        else:
            for b in (self.capture_btn, self.import_btn, self.edit_btn, self.delete_btn):
                b.configure(state="disabled")
            Label(d, "Only an admin can change student details or faces.", "small", "muted",
                  wraplength=260).pack(anchor="w", padx=22, pady=(8, 0))

    # ------------------------------------------------------------- actions
    def add(self):
        data = StudentDialog(self, self.ctx.db.list_classes()).show()
        if not data:
            return
        try:
            sid = self.ctx.db.add_student(**data)
        except (DuplicateError, ValueError) as exc:
            notify.alert(self, "Couldn't add the student", str(exc))
            return
        self.on_show()
        self.table.select(sid)
        if notify.confirm(self, "Capture their face now?",
                          f"{data['name']} was added. They need a face capture before they "
                          "can check in with the camera.", "Capture face"):
            self.capture()
        else:
            notify.toast(self, "Student added", f"{data['name']} ({data['roll_no']})")

    def edit(self):
        s = self._selected()
        if not s or not self.ctx.is_admin:
            return
        data = StudentDialog(self, self.ctx.db.list_classes(), s).show()
        if not data:
            return
        try:
            self.ctx.db.update_student(s["id"], **data)
        except (DuplicateError, ValueError) as exc:
            notify.alert(self, "Couldn't save the changes", str(exc))
            return
        avatars.forget(s["id"])
        self.on_show()
        notify.toast(self, "Changes saved", data["name"])

    def delete(self):
        s = self._selected()
        if not s:
            return
        if not notify.confirm(self, f"Delete {s['name']}?",
                              "Their face photos and every attendance record will be removed. "
                              "This can't be undone.", "Delete student", danger=True):
            return
        self.ctx.db.delete_student(s["id"])
        self.ctx.engine.delete_samples(s["id"])
        avatars.forget(s["id"])
        self.refresh()
        self.retrain(silent=True)
        notify.toast(self, "Student deleted", s["name"], "info")

    def capture(self):
        s = self._selected()
        if not s:
            return
        if self.ctx.engine.sample_count(s["id"]) and not notify.confirm(
                self, "Replace the saved face?", f"{s['name']} already has a face captured. "
                "A new capture replaces it.", "Recapture"):
            return
        EnrollDialog(self, self.ctx, s).show()
        self.refresh()
        self.table.select(s["id"])

    def import_photos(self):
        s = self._selected()
        if not s:
            return
        paths = filedialog.askopenfilenames(
            parent=self, title=f"Choose clear face photos of {s['name']}",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp"), ("All files", "*.*")])
        if not paths:
            return
        faces, skipped = [], []
        for p in paths:
            found = self.ctx.engine.faces_from_photo(p)
            (faces.extend(found) if found else skipped.append(p))
        if not faces:
            notify.alert(self, "No face found in those photos",
                         "Use clear, front-facing photos with one person in each.")
            return
        self.ctx.engine.save_samples(s["id"], faces, replace=False)
        avatars.forget(s["id"])
        msg = f"Added {len(faces)} photo{'s' if len(faces) != 1 else ''} for {s['name']}."
        if skipped:
            msg += f" {len(skipped)} skipped: no face found."
        self.refresh()
        self.table.select(s["id"])
        self.retrain(done_msg=msg)

    def retrain(self, silent=False, done_msg=None):
        self.retrain_btn.configure(state="disabled", text="Updating…")

        def reset():
            if self.retrain_btn.winfo_exists():
                self.retrain_btn.configure(text="Update model",
                                           state="normal" if self.ctx.is_admin else "disabled")

        def done(stats):
            reset()
            if not silent:
                notify.toast(self, "Photos imported" if done_msg else "Model updated",
                             done_msg or f"Recognises {stats['students']} student"
                             f"{'s' if stats['students'] != 1 else ''}.")

        def fail(exc):
            reset()
            notify.alert(self, "Couldn't update the model", str(exc))

        T.run_in_thread(self, self.ctx.retrain, done, fail)
