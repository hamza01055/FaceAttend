"""Modal dialogs: student / user forms, password change, student picker and
the webcam face-capture (enrolment) dialog."""
import time

import customtkinter as ctk

from ..camera import Camera, CameraError
from . import avatars, notify, video
from . import theme as T
from .icons import icon
from .notify import _Modal
from .widgets import Button, DataTable, Entry, Field, Label, SearchEntry


class FormDialog(_Modal):
    """Title, fields stacked vertically, inline error, Cancel / primary action."""

    def __init__(self, parent, title, subtitle="", action="Save", icon_name="edit-2", width=400):
        super().__init__(parent, title)
        self.body = ctk.CTkFrame(self, fg_color="transparent", width=width)
        self.body.pack(padx=28, pady=(24, 22), fill="both", expand=True)
        head = ctk.CTkFrame(self.body, fg_color="transparent")
        head.pack(fill="x", pady=(0, 18))
        ctk.CTkLabel(head, text="", image=icon(icon_name, 20, "primary"), width=40, height=40,
                     corner_radius=20, fg_color=T.PALETTE["primary_soft"]).pack(side="left")
        txt = ctk.CTkFrame(head, fg_color="transparent")
        txt.pack(side="left", padx=(12, 0))
        Label(txt, title, "h2").pack(anchor="w")
        if subtitle:
            Label(txt, subtitle, "small", "muted", wraplength=width - 70).pack(anchor="w")
        self.fields = ctk.CTkFrame(self.body, fg_color="transparent")
        self.fields.pack(fill="x")
        self.error = Label(self.body, "", "small", "absent", wraplength=width)
        self.error.pack(anchor="w", pady=(8, 0))
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x", pady=(12, 0))
        self.ok_btn = Button(row, action, self.ok, "primary", width=110)
        self.ok_btn.pack(side="right")
        Button(row, "Cancel", self._cancel, "secondary", width=96).pack(side="right", padx=(0, 8))
        self.bind("<Return>", lambda e: self.ok())

    def add(self, label, factory, hint=None):
        box, w = Field(self.fields, label, factory, hint)
        box.pack(fill="x", pady=(0, 14))
        return w

    def fail(self, message):
        self.error.configure(text=message)

    def _cancel(self):
        self.result = None
        self.destroy()

    def show(self):
        return self.run()

    def ok(self):
        raise NotImplementedError


class StudentDialog(FormDialog):
    def __init__(self, parent, classes, student=None):
        super().__init__(parent, "Edit student" if student else "Add student",
                         "Face capture comes next." if not student else "",
                         "Save changes" if student else "Add student",
                         "edit-2" if student else "user-plus")
        self.roll = self.add("Roll number", lambda p: Entry(p, "e.g. S25BINFT7M04037"))
        self.name = self.add("Full name", lambda p: Entry(p, "e.g. Nida Batool"))
        self.cls = self.add("Class or section", lambda p: ctk.CTkComboBox(
            p, values=classes or [""], height=40, corner_radius=T.R_CONTROL,
            border_width=1, border_color=T.PALETTE["border"], fg_color=T.PALETTE["surface_alt"],
            button_color=T.PALETTE["surface_alt"], button_hover_color=T.PALETTE["border"],
            text_color=T.PALETTE["text"], font=T.f("body"), dropdown_font=T.f("body")),
            "Pick an existing class or type a new one.")
        if student:
            self.roll.insert(0, student["roll_no"])
            self.name.insert(0, student["name"])
            self.cls.set(student["class_name"])
        else:
            self.cls.set(classes[0] if classes else "")
        self.after(80, self.roll.focus_set)

    def ok(self):
        roll, name = self.roll.get().strip(), self.name.get().strip()
        if not roll or not name:
            return self.fail("Enter both a roll number and a name.")
        self.result = {"roll_no": roll, "name": name, "class_name": self.cls.get().strip()}
        self.destroy()


class UserDialog(FormDialog):
    def __init__(self, parent):
        super().__init__(parent, "Add user", "Teachers take attendance and view records. "
                         "Admins can also manage students, users and settings.",
                         "Create account", "user-plus")
        self.username = self.add("Username", lambda p: Entry(p, "e.g. rana.nazeer"))
        self.full_name = self.add("Full name", lambda p: Entry(p, "e.g. Dr. Rana Nazeer Ahmed"))
        self.password = self.add("Password", lambda p: Entry(p, "At least 4 characters", show="•"))
        self.role = self.add("Role", lambda p: ctk.CTkSegmentedButton(
            p, values=["Teacher", "Admin"], height=38, corner_radius=T.R_CONTROL,
            font=T.f("body_bold"), selected_color=T.PALETTE["surface"],
            selected_hover_color=T.PALETTE["surface"],
            unselected_color=T.PALETTE["surface_alt"], unselected_hover_color=T.PALETTE["border"],
            text_color=T.PALETTE["text"], fg_color=T.PALETTE["surface_alt"]))
        self.role.set("Teacher")
        self.after(80, self.username.focus_set)

    def ok(self):
        if not self.username.get().strip():
            return self.fail("Enter a username.")
        if len(self.password.get()) < 4:
            return self.fail("The password needs at least 4 characters.")
        self.result = {"username": self.username.get().strip(),
                       "full_name": self.full_name.get().strip(),
                       "password": self.password.get(), "role": self.role.get().lower()}
        self.destroy()


class PasswordDialog(FormDialog):
    def __init__(self, parent, title="Change password", require_current=True):
        super().__init__(parent, title, "", "Save password", "key")
        self.require_current = require_current
        self.current = None
        if require_current:
            self.current = self.add("Current password", lambda p: Entry(p, show="•"))
        self.new = self.add("New password", lambda p: Entry(p, "At least 4 characters", show="•"))
        self.confirm = self.add("Confirm new password", lambda p: Entry(p, show="•"))
        self.after(80, (self.current or self.new).focus_set)

    def ok(self):
        if len(self.new.get()) < 4:
            return self.fail("The new password needs at least 4 characters.")
        if self.new.get() != self.confirm.get():
            return self.fail("The two new passwords don't match.")
        self.result = {"current": self.current.get() if self.current else "",
                       "new": self.new.get()}
        self.destroy()


class PickStudentDialog(_Modal):
    """Search and pick a student (manual attendance)."""

    def __init__(self, parent, db, class_name=None, date_s=None, engine=None):
        super().__init__(parent, "Mark attendance manually")
        self.db, self.class_name, self.engine = db, class_name, engine
        self.date_s = date_s or T.today_str()
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(padx=24, pady=22, fill="both", expand=True)
        Label(body, "Mark attendance manually", "h2").pack(anchor="w")
        Label(body, f"For {T.nice_date(T.parse_date(self.date_s))}"
              + (f", class {class_name}" if class_name else ""), "small", "muted").pack(
            anchor="w", pady=(2, 12))
        self.search = SearchEntry(body, "Search by name or roll number", self.refresh, width=440)
        self.search.pack(fill="x")
        self.table = DataTable(body, [("roll", "Roll no"), ("st", "Status")],
                               widths={"roll": 130, "st": 90}, avatar_label="Student",
                               avatar_width=220, height=7,
                               empty=("search", "No matching students", ""))
        self.table.pack(fill="both", expand=True, pady=12)
        self.table.tree.bind("<Double-1>", lambda e: self.ok())
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        Button(row, "Mark present", self.ok, "primary", "check").pack(side="right")
        Button(row, "Cancel", self._cancel, "secondary").pack(side="right", padx=(0, 8))
        self.after(80, self.search.entry.focus_set)
        self.refresh()

    def refresh(self):
        self.table.clear()
        term = self.search.get().lower()
        n = 0
        for r in self.db.daily_sheet(self.date_s, self.class_name):
            if term and term not in r["name"].lower() and term not in r["roll_no"].lower():
                continue
            st = {"id": r["student_id"], "name": r["name"]}
            self.table.insert(r["student_id"], (r["roll_no"], r["status"]), text=r["name"],
                              image=avatars.tk_avatar(self.engine, st, 28), tags=(r["status"],))
            n += 1
        self.table.show_empty(n == 0)

    def _cancel(self):
        self.result = None
        self.destroy()

    def ok(self):
        sel = self.table.selected()
        if not sel:
            return
        self.result = int(sel)
        self.destroy()

    def show(self):
        return self.run()


class EnrollDialog(_Modal):
    """Capture face samples from the webcam for one student, then update the model."""

    PREVIEW_W, PREVIEW_H = 520, 390

    def __init__(self, parent, ctx, student):
        super().__init__(parent, f"Capture face: {student['name']}")
        self.ctx, self.student = ctx, student
        self.target = max(5, ctx.db.get_int_setting("samples_per_student", 20))
        self.samples = []
        self.capturing = False
        self.training = False
        self.last_capture = 0.0
        self.camera = None
        self._photo = None
        self._job = None

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(padx=24, pady=22)
        head = ctk.CTkFrame(body, fg_color="transparent")
        head.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(head, text="", image=avatars.ctk_avatar(ctx.engine, student, 44)).pack(
            side="left")
        txt = ctk.CTkFrame(head, fg_color="transparent")
        txt.pack(side="left", padx=12)
        Label(txt, student["name"], "h2").pack(anchor="w")
        Label(txt, f"{student['roll_no']}" + (f"  ·  {student['class_name']}"
                                               if student.get("class_name") else ""),
              "small", "muted").pack(anchor="w")

        cols = ctk.CTkFrame(body, fg_color="transparent")
        cols.pack()
        view_frame, self.view = video.make_view(cols, self.PREVIEW_W, self.PREVIEW_H,
                                                "Starting camera…")
        view_frame.pack(side="left")
        tips = ctk.CTkFrame(cols, fg_color="transparent", width=210)
        tips.pack(side="left", fill="y", padx=(18, 0))
        Label(tips, "For a good capture", "h3").pack(anchor="w", pady=(4, 10))
        for ic, text in (("sun", "Face a window or lamp; avoid bright light behind you"),
                         ("user", "Only the student in view, about an arm's length away"),
                         ("refresh-cw", "Slowly turn your head a little left and right")):
            r = ctk.CTkFrame(tips, fg_color="transparent")
            r.pack(fill="x", pady=5)
            ctk.CTkLabel(r, text="", image=icon(ic, 16, "primary"), width=22).pack(
                side="left", anchor="n", pady=2)
            Label(r, text, "small", "muted", wraplength=170).pack(side="left", padx=(8, 0))

        self.status = Label(body, "Starting camera…", "body_bold")
        self.status.pack(anchor="w", pady=(16, 8))
        self.progress = ctk.CTkProgressBar(body, height=8, corner_radius=4,
                                           progress_color=T.PALETTE["primary"],
                                           fg_color=T.PALETTE["surface_alt"])
        self.progress.set(0)
        self.progress.pack(fill="x")
        self.count = Label(body, f"0 of {self.target} images", "small", "muted")
        self.count.pack(anchor="w", pady=(6, 0))
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(14, 0))
        self.start_btn = Button(row, "Start capture", self.start_capture, "primary", "aperture",
                                state="disabled")
        self.start_btn.pack(side="right")
        self.cancel_btn = Button(row, "Cancel", self.cancel, "secondary")
        self.cancel_btn.pack(side="right", padx=(0, 8))
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.after(60, self._open_camera)

    def show(self):
        return self.run()

    def _open_camera(self):
        try:
            self.camera = Camera(self.ctx.camera_source()).open()
        except CameraError as exc:
            notify.alert(self, "Camera not available", str(exc))
            self.cancel()
            return
        self.start_btn.configure(state="normal")
        self._tick()

    def start_capture(self):
        self.samples.clear()
        self.progress.set(0)
        self.capturing = True
        self.start_btn.configure(state="disabled")

    def _tick(self):
        if self.camera is None:
            return
        frame = self.camera.read()
        clean = frame.copy() if frame is not None else None
        if frame is not None:
            faces = self.ctx.engine.detect(frame)
            if len(faces) == 1:
                face = faces[0]
                too_small = face.box[2] < 80
                color = video.AMBER if too_small else (video.BLUE if self.capturing else video.GREEN)
                video.draw_box(frame, face.box, f"{len(self.samples)}/{self.target}"
                               if self.capturing else ("Move closer" if too_small else "Ready"),
                               color)
                if too_small:
                    msg = "Face too small. Move closer to the camera."
                else:
                    if self.capturing and time.time() - self.last_capture >= 0.15:
                        self.samples.append(self.ctx.engine.align(clean, face))
                        self.last_capture = time.time()
                        self.progress.set(len(self.samples) / self.target)
                        self.count.configure(text=f"{len(self.samples)} of {self.target} images")
                    msg = "Capturing. Keep looking at the camera." if self.capturing \
                        else "Face found. Press Start capture."
            elif len(faces) > 1:
                for fc in faces:
                    video.draw_box(frame, fc.box, "", video.RED)
                msg = "More than one face. Only the student should be in view."
            else:
                msg = "No face found. Move closer or improve the lighting."
            self.status.configure(text=msg)
            self._photo = video.to_photo(frame, self.PREVIEW_W, self.PREVIEW_H)
            self.view.configure(image=self._photo, text="")
        if self.capturing and len(self.samples) >= self.target:
            self._finish()
            return
        self._job = self.after(40, self._tick)

    def _finish(self):
        self.capturing = False
        self._stop_camera()
        engine, sid = self.ctx.engine, self.student["id"]
        samples = list(self.samples)

        clash = self._existing_match(samples)
        if clash and not notify.confirm(
                self, "Face already registered",
                f"This face looks like {clash['name']} ({clash['roll_no']}), who is already "
                f"enrolled. Save it for {self.student['name']} anyway?", "Save anyway",
                danger=True):
            self.cancel()
            return

        self.training = True
        self.status.configure(text="Saving and updating the recognition model…")
        self.cancel_btn.configure(state="disabled")

        def work():
            count = engine.save_samples(sid, samples, replace=True)
            stats = self.ctx.retrain()
            return count, stats

        def done(res):
            self.training = False
            self.result = res[0]
            avatars.forget(sid)
            notify.toast(self, "Face captured", f"{self.student['name']} can now check in "
                         f"with the camera ({res[0]} images saved).")
            self.destroy()

        def fail(exc):
            self.training = False
            notify.alert(self, "Couldn't save the face", str(exc))
            self.destroy()

        T.run_in_thread(self, work, done, fail)

    def _existing_match(self, samples):
        engine = self.ctx.engine
        if not engine.is_trained or not samples:
            return None
        threshold = self.ctx.match_threshold()
        votes = {}
        for face in samples[:: max(1, len(samples) // 5)]:
            for sid, sim in engine.match(face)[:1]:
                if sid != self.student["id"] and sim >= threshold:
                    votes[sid] = votes.get(sid, 0) + 1
        if not votes:
            return None
        sid = max(votes, key=votes.get)
        return self.ctx.db.get_student(sid) if votes[sid] >= 2 else None

    def _stop_camera(self):
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        if self.camera:
            self.camera.release()
            self.camera = None

    def cancel(self):
        if self.training:
            return
        self._stop_camera()
        self.result = None
        self.destroy()
