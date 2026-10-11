"""Live attendance: webcam -> detect -> recognise -> mark (FR1–FR4)."""
import datetime as dt
import tkinter as tk

import customtkinter as ctk

from ..camera import Camera, CameraError
from . import avatars, notify, video
from . import theme as T
from .base import Page
from .dialogs import PickStudentDialog
from .icons import icon
from .widgets import Button, Card, Dropdown, EmptyState, Label, PageHeader, Pill

ALL = "All classes"


class AttendancePage(Page):
    title = "Take attendance"

    def __init__(self, parent, ctx):
        super().__init__(parent, ctx)
        self.camera = None
        self._job = None
        self._photo = None
        self.streaks = {}
        self.session_ids = set()
        self.students = {}
        self.session_date = T.today_str()
        self.threshold = 0.40
        self.confirm = 3
        big = self.winfo_screenwidth() >= 1600 and self.winfo_screenheight() >= 900
        self.VIEW_W, self.VIEW_H = (640, 480) if big else (560, 420)

        self.header = PageHeader(self, "Take attendance",
                                 "Students look at the camera one at a time. "
                                 "Recognised students are checked in automatically.")
        self.header.pack(fill="x")
        acts = self.header.actions
        self.class_var = tk.StringVar(value=ALL)
        self.class_box = Dropdown(acts, [ALL], self.class_var,
                                  command=lambda v: self._refresh_session(), width=170)
        self.class_box.pack(side="left", padx=(0, 10))
        self.toggle_btn = Button(acts, "Start camera", self.toggle, "primary", "play", size="lg",
                                 width=170)
        self.toggle_btn.pack(side="left")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, pady=(20, 0))
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # ---- camera
        left = ctk.CTkFrame(body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nw", padx=(0, 18))
        view_frame, self.view = video.make_view(left, self.VIEW_W, self.VIEW_H, "")
        view_frame.pack()
        self._idle_view()
        status = ctk.CTkFrame(left, fg_color="transparent")
        status.pack(fill="x", pady=(12, 0))
        self.status_dot = ctk.CTkFrame(status, width=10, height=10, corner_radius=5,
                                       fg_color=T.PALETTE["faint"])
        self.status_dot.pack(side="left", padx=(4, 8))
        self.status = Label(status, "Camera is off", "body", "muted")
        self.status.pack(side="left")

        # ---- right column
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")

        # latest check-in (the one animated moment)
        self.hero_holder = ctk.CTkFrame(right, fg_color="transparent", height=150)
        self.hero_holder.pack(fill="x")
        self.hero_holder.pack_propagate(False)
        self.hero = Card(self.hero_holder, radius=T.R_HERO)
        self.hero.place(x=0, y=0, relwidth=1, relheight=1)
        self.hero_avatar = ctk.CTkLabel(self.hero, text="", width=84, height=84,
                                        image=icon("user-check", 30, "faint"),
                                        fg_color=T.PALETTE["surface_alt"], corner_radius=42)
        self.hero_avatar.pack(side="left", padx=(22, 16), pady=22)
        hero_txt = ctk.CTkFrame(self.hero, fg_color="transparent")
        hero_txt.pack(side="left", fill="both", expand=True, pady=18)
        self.hero_kicker = Label(hero_txt, "Waiting for the first check-in", "small", "muted")
        self.hero_kicker.pack(anchor="w")
        self.hero_name = Label(hero_txt, "Start the camera to begin", "h2")
        self.hero_name.pack(anchor="w", pady=(2, 2))
        self.hero_meta = Label(hero_txt, "", "small", "muted")
        self.hero_meta.pack(anchor="w")
        self.hero_pill = Pill(hero_txt, "", "neutral")

        # progress + list
        lst = Card(right)
        lst.pack(fill="both", expand=True, pady=(16, 0))
        lh = ctk.CTkFrame(lst, fg_color="transparent")
        lh.pack(fill="x", padx=20, pady=(18, 4))
        Label(lh, "Checked in today", "h3").pack(side="left")
        self.count_label = Label(lh, "0 of 0", "h3", "primary")
        self.count_label.pack(side="right")
        self.bar = ctk.CTkProgressBar(lst, height=6, corner_radius=3,
                                      progress_color=T.PALETTE["primary"],
                                      fg_color=T.PALETTE["surface_alt"])
        self.bar.set(0)
        self.bar.pack(fill="x", padx=20, pady=(4, 8))
        self.list = ctk.CTkScrollableFrame(lst, fg_color="transparent",
                                           scrollbar_button_color=T.PALETTE["border"])
        self.list.pack(fill="both", expand=True, padx=8)
        foot = ctk.CTkFrame(lst, fg_color="transparent")
        foot.pack(fill="x", padx=16, pady=14)
        Button(foot, "Mark manually", self.manual_mark, "secondary", "edit-2").pack(side="left")
        Button(foot, "View records", lambda: ctx.navigate("records"), "ghost").pack(side="right")
        self.rows = []

    # ------------------------------------------------------------- lifecycle
    def on_show(self):
        classes = self.ctx.db.list_classes()
        self.class_box.configure(values=[ALL] + classes)
        if self.class_var.get() not in [ALL] + classes:
            self.class_var.set(ALL)
        self._refresh_session()
        if not self.camera:
            if not self.ctx.engine.is_trained:
                self._set_status("No faces captured yet. Add students and capture their faces "
                                 "first.", "late")
            else:
                self._set_status("Camera is off", "faint")

    def on_hide(self):
        self.stop()

    def on_theme(self):
        self._refresh_session()

    # -------------------------------------------------------------- helpers
    def _selected_class(self):
        v = self.class_var.get()
        return None if v == ALL else v

    def _set_status(self, text, color="muted"):
        self.status.configure(text=text, text_color=T.PALETTE["text" if color != "faint" else "muted"])
        self.status_dot.configure(fg_color=T.PALETTE[color])

    def _idle_view(self):
        self.view.configure(image="", text="Camera is off\n\nPress Start camera to begin")

    def _refresh_session(self):
        today = T.today_str()
        self.session_date = today
        cls = self._selected_class()
        self.students = {s["id"]: s for s in self.ctx.db.list_students()}
        marked = self.ctx.db.attendance_on(today)
        self.rows = [r for r in marked if not cls or r["class_name"] == cls]
        self.session_ids = {r["student_id"] for r in marked}
        total = self.ctx.db.count_students(cls)
        self.count_label.configure(text=f"{len(self.rows)} of {total}")
        self.bar.set(len(self.rows) / total if total else 0)
        for w in self.list.winfo_children():
            w.destroy()
        if not self.rows:
            EmptyState(self.list, "user-check", "No check-ins yet",
                       "Each recognised student is added here with their time.").pack(pady=30)
        for r in self.rows:
            self._row(r)

    def _row(self, r):
        row = ctk.CTkFrame(self.list, fg_color="transparent")
        row.pack(fill="x", pady=1)
        st = {"id": r["student_id"], "name": r["name"]}
        ctk.CTkLabel(row, text="", image=avatars.ctk_avatar(self.ctx.engine, st, 32)).pack(
            side="left", padx=(8, 10), pady=5)
        Label(row, r["name"], "body_bold").pack(side="left")
        Label(row, f"  {r['roll_no']}", "small", "muted").pack(side="left")
        Pill(row, r["status"], r["status"]).pack(side="right", padx=8)
        Label(row, r["time"][:5], "small", "muted").pack(side="right")

    # --------------------------------------------------------------- camera
    def toggle(self):
        if self.camera:
            self.stop()
        else:
            self.start()

    def start(self):
        if not self.ctx.engine.is_trained:
            notify.alert(self, "No faces captured yet",
                         "Go to Students, add your students and use Capture face. "
                         "Then come back here.", "warning")
            return
        try:
            self.camera = Camera(self.ctx.camera_source()).open()
        except CameraError as exc:
            notify.alert(self, "Camera not available", str(exc))
            return
        self.streaks.clear()
        self._refresh_session()
        self.threshold = self.ctx.match_threshold()
        self.confirm = max(1, self.ctx.db.get_int_setting("confirm_frames", 3))
        self.toggle_btn.configure(text="Stop camera", image=icon("square", 16, "absent"),
                                  fg_color=T.PALETTE["surface"], hover_color=T.PALETTE["absent_soft"],
                                  text_color=T.PALETTE["absent"], border_width=1,
                                  border_color=T.PALETTE["border"])
        self._set_status("Looking for faces…", "primary")
        self._tick()

    def stop(self):
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        if self.camera:
            self.camera.release()
            self.camera = None
        self._photo = None
        try:
            self._idle_view()
            self.toggle_btn.configure(text="Start camera", image=icon("play", 18, "on_primary"),
                                      fg_color=T.PALETTE["primary"],
                                      hover_color=T.PALETTE["primary_hover"],
                                      text_color=T.PALETTE["on_primary"], border_width=0)
            self._set_status("Camera is off", "faint")
        except tk.TclError:
            pass

    def _tick(self):
        if not self.camera:
            return
        if T.today_str() != self.session_date:
            self.streaks.clear()
            self._refresh_session()
        frame = self.camera.read()
        if frame is not None:
            self._process(frame)
            self._photo = video.to_photo(frame, self.VIEW_W, self.VIEW_H)
            self.view.configure(image=self._photo, text="")
        self._job = self.after(30, self._tick)

    def _process(self, frame):
        engine = self.ctx.engine
        faces = engine.detect(frame)
        clean = frame.copy()
        seen = set()
        cls = self._selected_class()
        results = []
        for face in faces:
            if face.box[2] < 60:
                results.append((face, None, None, "Come closer"))
                continue
            sid, sim = engine.recognize(engine.align(clean, face), self.threshold)
            results.append((face, sid, sim, None))
        best = {}
        for face, sid, sim, _ in results:
            if sid is not None and (sid not in best or sim > best[sid][1]):
                best[sid] = (face, sim)
        for face, sid, sim, note in results:
            box = face.box
            if note:
                video.draw_box(frame, box, note, video.AMBER)
                continue
            student = self.students.get(sid) if sid is not None else None
            if student is None or best.get(sid, (None,))[0] is not face:
                video.draw_box(frame, box, "Unknown", video.RED)
                continue
            if cls and student["class_name"] != cls:
                video.draw_box(frame, box, f"{student['name']} (other class)", video.AMBER)
                continue
            seen.add(sid)
            if sid in self.session_ids:
                video.draw_box(frame, box, f"{student['name']}  checked in", video.GREEN)
                continue
            self.streaks[sid] = self.streaks.get(sid, 0) + 1
            if self.streaks[sid] >= self.confirm:
                self._mark(student, sim)
                video.draw_box(frame, box, f"{student['name']}  checked in", video.GREEN)
            else:
                video.draw_box(frame, box, f"{student['name']}?", video.AMBER)
        for sid in list(self.streaks):
            if sid not in seen:
                del self.streaks[sid]
        if faces:
            n = len(faces)
            self._set_status(f"{n} face{'s' if n != 1 else ''} in view", "primary")
        else:
            self._set_status("No face in view", "faint")

    def _mark(self, student, sim, method="face"):
        try:
            created, rec = self.ctx.db.mark_attendance(
                student["id"], method=method,
                confidence=round(sim, 3) if sim is not None else None,
                marked_by=self.ctx.user["id"])
        except ValueError:
            self.streaks.pop(student["id"], None)
            self.students.pop(student["id"], None)
            return
        self.session_ids.add(student["id"])
        self.streaks.pop(student["id"], None)
        if created:
            self.bell()
            self._show_checkin(student, rec)
            self._refresh_session()

    def _show_checkin(self, student, rec):
        """Fill the latest check-in card and slide it in."""
        ring = T.c(T.STATUS[rec["status"]][0])
        self.hero_avatar.configure(image=avatars.ctk_avatar(self.ctx.engine, student, 84, ring),
                                   fg_color="transparent")
        t = dt.datetime.strptime(rec["time"], "%H:%M:%S").strftime("%I:%M %p").lstrip("0")
        self.hero_kicker.configure(text=f"Checked in at {t}"
                                   + (" (manual)" if rec["method"] == "manual" else ""))
        self.hero_name.configure(text=student["name"])
        self.hero_meta.configure(text=student["roll_no"] + (f", {student['class_name']}"
                                                             if student["class_name"] else ""))
        self.hero_pill.set(rec["status"], rec["status"])
        self.hero_pill.pack(anchor="w", pady=(6, 0))
        steps = 10

        def slide(i=0):
            if not self.hero.winfo_exists():
                return
            ease = (1 - i / steps) ** 3
            self.hero.place_configure(x=int(80 * ease))
            if i < steps:
                self.after(16, slide, i + 1)
        slide()

    def manual_mark(self):
        sid = PickStudentDialog(self, self.ctx.db, self._selected_class(),
                                engine=self.ctx.engine).show()
        if sid is None:
            return
        student = self.ctx.db.get_student(sid)
        if self.ctx.db.is_marked(sid, T.today_str()):
            notify.toast(self, "Already checked in", f"{student['name']} is already marked "
                         "for today.", "info")
            return
        self.session_ids.discard(sid)
        self._mark(student, None, method="manual")
