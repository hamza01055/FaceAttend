"""Admin-only screens: user accounts and settings."""
import datetime as dt
import os
import sqlite3
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from .. import config
from ..camera import Camera, CameraError
from ..database import DuplicateError
from . import avatars, notify
from . import theme as T
from .base import Page
from .dialogs import PasswordDialog, UserDialog
from .icons import icon
from .widgets import Button, Card, DataTable, Dropdown, Entry, Label, PageHeader


class UsersPage(Page):
    title = "Users"

    def __init__(self, parent, ctx):
        super().__init__(parent, ctx)
        h = PageHeader(self, "Users", "Who can sign in to this computer's attendance app.")
        h.pack(fill="x")
        Button(h.actions, "Add user", self.add, "primary", "user-plus", size="lg").pack()
        card = Card(self)
        card.pack(fill="both", expand=True, pady=(20, 0))
        bar = ctk.CTkFrame(card, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(16, 6))
        Label(bar, "Admins manage everything. Teachers take attendance and view records.",
              "small", "muted").pack(side="left")
        self.delete_btn = Button(bar, "Delete", self.delete, "danger", "trash-2", size="sm")
        self.delete_btn.pack(side="right")
        Button(bar, "Reset password", self.reset, "secondary", "key", size="sm").pack(
            side="right", padx=(0, 8))
        self.table = DataTable(card, [("username", "Username"), ("role", "Role"),
                                      ("created", "Added")],
                               widths={"username": 180, "role": 110, "created": 140},
                               avatar_label="Name", avatar_width=260, height=12)
        self.table.pack(fill="both", expand=True, padx=(10, 6), pady=(0, 10))
        self.tree = self.table.tree

    def on_show(self):
        self.table.clear()
        for u in self.ctx.db.list_users():
            name = u["full_name"] or u["username"]
            you = "  (you)" if self.ctx.user and u["id"] == self.ctx.user["id"] else ""
            self.table.insert(u["id"], ("@" + u["username"], u["role"].capitalize(),
                                        dt.date.fromisoformat(u["created_at"][:10]).strftime("%d %b %Y")),
                              text=name + you,
                              image=avatars.tk_avatar(None, {"id": -u["id"], "name": name}, 30),
                              tags=("bold",) if u["role"] == "admin" else ())

    def _selected_id(self):
        sel = self.table.selected()
        return int(sel) if sel else None

    def add(self):
        data = UserDialog(self).show()
        if not data:
            return
        try:
            self.ctx.db.add_user(data["username"], data["password"], data["full_name"],
                                 data["role"])
        except (DuplicateError, ValueError) as exc:
            notify.alert(self, "Couldn't add the user", str(exc))
            return
        self.on_show()
        notify.toast(self, "Account created", f"@{data['username']} can now sign in.")

    def reset(self):
        uid = self._selected_id()
        if uid is None:
            notify.toast(self, "Select a user first", "", "info")
            return
        user = self.ctx.db.get_user(uid)
        data = PasswordDialog(self, f"Reset password for @{user['username']}",
                              require_current=False).show()
        if data:
            self.ctx.db.set_password(uid, data["new"])
            notify.toast(self, "Password reset", f"Give @{user['username']} their new password.")

    def delete(self):
        uid = self._selected_id()
        if uid is None:
            notify.toast(self, "Select a user first", "", "info")
            return
        if uid == self.ctx.user["id"]:
            notify.alert(self, "You can't delete yourself",
                         "Sign in with another admin account to remove this one.", "warning")
            return
        user = self.ctx.db.get_user(uid)
        if not notify.confirm(self, f"Delete @{user['username']}?",
                              "They will no longer be able to sign in. Attendance they took "
                              "is kept.", "Delete user", danger=True):
            return
        try:
            self.ctx.db.delete_user(uid)
        except ValueError as exc:
            notify.alert(self, "Can't delete this user", str(exc), "warning")
            return
        self.on_show()
        notify.toast(self, "User deleted", f"@{user['username']}", "info")


class SettingsPage(Page):
    title = "Settings"

    def __init__(self, parent, ctx):
        super().__init__(parent, ctx)
        h = PageHeader(self, "Settings", "Camera, recognition and attendance rules.")
        h.pack(fill="x")
        Button(h.actions, "Save changes", self.save, "primary", "save", size="lg").pack()

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                        scrollbar_button_color=T.PALETTE["border"])
        scroll.pack(fill="both", expand=True, pady=(16, 0))
        cols = ctk.CTkFrame(scroll, fg_color="transparent")
        cols.pack(fill="both", expand=True)
        cols.columnconfigure(0, weight=1, uniform="s")
        cols.columnconfigure(1, weight=1, uniform="s")
        left = ctk.CTkFrame(cols, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = ctk.CTkFrame(cols, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        # ---- recognition
        rec = self._section(left, "aperture", "Recognition",
                            "How sure the app must be before checking a student in.")
        row = ctk.CTkFrame(rec, fg_color="transparent")
        row.pack(fill="x", pady=(4, 0))
        Label(row, "Match strictness", "body_bold").pack(side="left")
        self.thr_label = Label(row, "0.40", "body_bold", "primary")
        self.thr_label.pack(side="right")
        self.threshold = tk.DoubleVar(value=0.40)
        ctk.CTkSlider(rec, from_=config.THRESHOLD_MIN, to=config.THRESHOLD_MAX,
                      number_of_steps=int((config.THRESHOLD_MAX - config.THRESHOLD_MIN) * 100),
                      variable=self.threshold, button_color=T.PALETTE["primary"],
                      button_hover_color=T.PALETTE["primary_hover"],
                      progress_color=T.PALETTE["primary"], fg_color=T.PALETTE["surface_alt"],
                      command=lambda v: self.thr_label.configure(text=f"{float(v):.2f}")).pack(
            fill="x", pady=(8, 2))
        scale = ctk.CTkFrame(rec, fg_color="transparent")
        scale.pack(fill="x")
        Label(scale, "Relaxed", "small", "faint").pack(side="left")
        Label(scale, "Strict", "small", "faint").pack(side="right")
        Label(rec, "0.40 is recommended. Raise it if someone is ever matched wrongly; lower it "
                   "if students are sometimes not recognised.", "small", "muted",
              wraplength=420).pack(anchor="w", pady=(8, 14))
        two = ctk.CTkFrame(rec, fg_color="transparent")
        two.pack(fill="x")
        self.samples_var = tk.StringVar(value="20")
        self.confirm_var = tk.StringVar(value="3")
        self._labeled(two, "Photos per face capture",
                      lambda p: Dropdown(p, ["10", "15", "20", "30", "40"], self.samples_var,
                                         width=140)).pack(side="left")
        self._labeled(two, "Frames to confirm",
                      lambda p: Dropdown(p, ["1", "2", "3", "4", "5"], self.confirm_var,
                                         width=140)).pack(side="left", padx=(16, 0))

        # ---- attendance
        att = self._section(left, "clock", "Attendance rules",
                            "When an arrival counts as late.")
        lrow = ctk.CTkFrame(att, fg_color="transparent")
        lrow.pack(fill="x")
        self.late_on = tk.BooleanVar(value=False)
        ctk.CTkSwitch(lrow, text="Mark late arrivals", variable=self.late_on, font=T.f("body"),
                      text_color=T.PALETTE["text"], progress_color=T.PALETTE["primary"],
                      command=self._toggle_late).pack(side="left")
        self.late = Entry(lrow, "08:30", width=90)
        self.late.pack(side="right")
        Label(lrow, "after", "body", "muted").pack(side="right", padx=8)

        # ---- appearance
        app_sec = self._section(right, "sun", "Appearance", "")
        self.mode = ctk.CTkSegmentedButton(
            app_sec, values=["Light", "Dark", "System"], command=self._set_mode, height=36,
            corner_radius=T.R_CONTROL, font=T.f("body_bold"),
            selected_color=T.PALETTE["surface"], selected_hover_color=T.PALETTE["surface"],
            unselected_color=T.PALETTE["surface_alt"], unselected_hover_color=T.PALETTE["border"],
            text_color=T.PALETTE["text"], fg_color=T.PALETTE["surface_alt"])
        self.mode.pack(anchor="w")
        self.institution = None
        self._labeled(app_sec, "Institution name",
                      lambda p: Entry(p, "Shown on the dashboard", width=360)).pack(
            anchor="w", pady=(14, 0))
        self.institution = self._last_input

        # ---- camera
        cam = self._section(right, "camera", "Camera", "Built-in webcams are usually number 0.")
        crow = ctk.CTkFrame(cam, fg_color="transparent")
        crow.pack(fill="x")
        self.camera_var = tk.StringVar(value="0")
        Dropdown(crow, [str(i) for i in range(6)], self.camera_var, width=110).pack(side="left")
        Button(crow, "Test camera", self.test_camera, "secondary", "camera").pack(
            side="left", padx=(10, 0))

        # ---- data
        data = self._section(right, "database", "Your data",
                             "Everything is stored offline on this computer.")
        Label(data, config.DATA_DIR, "small", "faint", wraplength=420).pack(anchor="w")
        drow = ctk.CTkFrame(data, fg_color="transparent")
        drow.pack(fill="x", pady=(12, 0))
        Button(drow, "Back up database", self.backup, "secondary", "download").pack(side="left")
        Button(drow, "Open folder", self.open_folder, "ghost", "folder").pack(side="left",
                                                                              padx=(8, 0))
        self.stats = Label(data, "", "small", "muted")
        self.stats.pack(anchor="w", pady=(12, 0))

    # ----------------------------------------------------------- builders
    def _section(self, parent, icon_name, title, subtitle):
        card = Card(parent)
        card.pack(fill="x", pady=(0, 16))
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=22, pady=(18, 10))
        ctk.CTkLabel(head, text="", image=icon(icon_name, 18, "primary"), width=36, height=36,
                     corner_radius=18, fg_color=T.PALETTE["primary_soft"]).pack(side="left")
        txt = ctk.CTkFrame(head, fg_color="transparent")
        txt.pack(side="left", padx=(12, 0))
        Label(txt, title, "h3").pack(anchor="w")
        if subtitle:
            Label(txt, subtitle, "small", "muted").pack(anchor="w")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=22, pady=(0, 20))
        return inner

    def _labeled(self, parent, label, factory):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        Label(box, label, "small_bold", "muted").pack(anchor="w", pady=(0, 6))
        self._last_input = factory(box)
        self._last_input.pack(anchor="w")
        return box

    def _toggle_late(self):
        self.late.configure(state="normal" if self.late_on.get() else "disabled")

    def _set_mode(self, value):
        self.ctx.set_appearance(value)

    # --------------------------------------------------------------- data
    def on_show(self):
        db = self.ctx.db
        self.institution.delete(0, "end")
        self.institution.insert(0, db.get_setting("institution_name"))
        self.camera_var.set(db.get_setting("camera_index"))
        thr = self.ctx.match_threshold()
        self.threshold.set(thr)
        self.thr_label.configure(text=f"{thr:.2f}")
        self.samples_var.set(db.get_setting("samples_per_student"))
        self.confirm_var.set(db.get_setting("confirm_frames"))
        late = db.get_setting("late_after")
        self.late_on.set(bool(late))
        self.late.configure(state="normal")
        self.late.delete(0, "end")
        self.late.insert(0, late or "08:30")
        self._toggle_late()
        self.mode.set(db.get_setting("appearance", "Light") or "Light")
        size = os.path.getsize(config.DB_PATH) / 1024 if os.path.exists(config.DB_PATH) else 0
        self.stats.configure(text=f"{db.count_students()} students, database {size:.0f} KB, "
                                  f"version {config.APP_VERSION}")

    def save(self):
        late = self.late.get().strip() if self.late_on.get() else ""
        if late:
            try:
                dt.datetime.strptime(late, "%H:%M")
            except ValueError:
                notify.alert(self, "Check the late time",
                             "Use 24-hour HH:MM, for example 08:30.", "warning")
                return
        db = self.ctx.db
        db.set_setting("institution_name", self.institution.get().strip())
        db.set_setting("camera_index", int(self.camera_var.get()))
        db.set_setting("match_threshold", f"{self.threshold.get():.2f}")
        db.set_setting("samples_per_student", int(self.samples_var.get()))
        db.set_setting("confirm_frames", int(self.confirm_var.get()))
        db.set_setting("late_after", late)
        notify.toast(self, "Settings saved", "")

    def test_camera(self):
        try:
            cam = Camera(int(self.camera_var.get())).open()
            cam.release()
            notify.toast(self, "Camera works", f"Camera {self.camera_var.get()} is ready.")
        except (CameraError, ValueError) as exc:
            notify.alert(self, "Camera not available", str(exc))

    def open_folder(self):
        path = config.DATA_DIR
        try:
            if hasattr(os, "startfile"):
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path])
        except OSError as exc:
            notify.alert(self, "Couldn't open the folder", str(exc))

    def backup(self):
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".db",
            initialfile=f"attendance_backup_{dt.date.today().isoformat()}.db",
            filetypes=[("SQLite database", "*.db")])
        if not path:
            return
        with self.ctx.db._lock:
            dest = sqlite3.connect(path)
            self.ctx.db.conn.backup(dest)
            dest.close()
        notify.toast(self, "Backup saved", os.path.basename(path))
