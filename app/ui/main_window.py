"""Main window: sign-in screen and the app shell (sidebar + pages)."""
import os
import time
import tkinter as tk

import customtkinter as ctk

from .. import config
from . import avatars, brand, fonts, notify
from . import theme as T
from .admin import SettingsPage, UsersPage
from .attendance import AttendancePage
from .dashboard import DashboardPage
from .dialogs import PasswordDialog
from .icons import icon
from .records import RecordsPage
from .students import StudentsPage
from .widgets import Button, Entry, Label

# key, label, icon, page class, admin only
NAV = [
    ("dashboard", "Today", "home", DashboardPage, False),
    ("attendance", "Take attendance", "camera", AttendancePage, False),
    ("students", "Students", "users", StudentsPage, False),
    ("records", "Records", "clipboard", RecordsPage, False),
    ("users", "Users", "shield", UsersPage, True),
    ("settings", "Settings", "sliders", SettingsPage, True),
]


class AppContext:
    """Shared state handed to every page."""

    def __init__(self, app, db, engine):
        self.app, self.db, self.engine = app, db, engine
        self.user = None

    @property
    def is_admin(self) -> bool:
        return bool(self.user and self.user["role"] == "admin")

    def camera_source(self):
        override = os.environ.get("FACEATTEND_CAMERA", "").strip()
        if override:
            return int(override) if override.isdigit() else override
        return self.db.get_int_setting("camera_index", 0)

    def match_threshold(self) -> float:
        t = self.db.get_float_setting("match_threshold", 0.40)
        return min(max(t, config.THRESHOLD_MIN), config.THRESHOLD_MAX)

    def retrain(self) -> dict:
        valid = {s["id"] for s in self.db.list_students()}
        return self.engine.train(valid_ids=valid)

    def navigate(self, key):
        self.app.shell.show(key)

    def set_appearance(self, mode: str):
        self.db.set_setting("appearance", mode)
        self.app.apply_appearance(mode)


# ====================================================================== login
class LoginFrame(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app, fg_color=T.PALETTE["bg"], corner_radius=0)
        self.app = app
        self.failures = 0
        self.locked_until = 0.0

        art = ctk.CTkFrame(self, fg_color=T.PALETTE["sidebar"], corner_radius=0, width=460)
        art.pack(side="left", fill="y")
        art.pack_propagate(False)
        self.art_img = ctk.CTkLabel(art, text="", image=brand.login_art(460, 1000))
        self.art_img.place(x=0, y=0)
        story = ctk.CTkFrame(art, fg_color=T.PALETTE["sidebar"], corner_radius=16)
        story.place(relx=0.08, rely=0.62, anchor="nw")
        ctk.CTkLabel(story, text="", image=brand.logo(48)).pack(anchor="w", padx=20, pady=(20, 14))
        ctk.CTkLabel(story, text="FaceAttend", font=T.f("display"), text_color="#FFFFFF",
                     anchor="w").pack(anchor="w", padx=20)
        ctk.CTkLabel(story, text="Attendance that takes a glance,\nnot a roll call.",
                     font=T.f("h2"), text_color="#B7CEC5", anchor="w", justify="left").pack(
            anchor="w", padx=20, pady=(6, 0))
        ctk.CTkLabel(story, text="Runs offline on this computer.", font=T.f("small"),
                     text_color="#7FA397", anchor="w").pack(anchor="w", padx=20, pady=(16, 20))

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)
        form = ctk.CTkFrame(right, fg_color="transparent", width=360)
        form.place(relx=0.5, rely=0.47, anchor="center")
        Label(form, "Sign in", "display").pack(anchor="w")
        self.inst = Label(form, "", "body", "muted")
        self.inst.pack(anchor="w", pady=(4, 28))
        Label(form, "Username", "small_bold", "muted").pack(anchor="w", pady=(0, 6))
        self.username = Entry(form, "admin or your username", width=360)
        self.username.pack(fill="x")
        Label(form, "Password", "small_bold", "muted").pack(anchor="w", pady=(16, 6))
        pw = ctk.CTkFrame(form, fg_color="transparent")
        pw.pack(fill="x")
        self.password = Entry(pw, "Password", show="•", width=312)
        self.password.pack(side="left", fill="x", expand=True)
        self.eye = ctk.CTkButton(pw, text="", width=40, height=40, corner_radius=T.R_CONTROL,
                                 fg_color=T.PALETTE["surface_alt"],
                                 hover_color=T.PALETTE["border"],
                                 image=icon("eye", 18, "muted"), command=self._toggle_pw)
        self.eye.pack(side="left", padx=(8, 0))
        self.error = Label(form, "", "small", "absent")
        self.error.pack(anchor="w", pady=(10, 0))
        Button(form, "Sign in", self.login, "primary", size="lg").pack(fill="x", pady=(12, 0))
        self.hint = Label(form, "", "small", "muted")
        self.hint.pack(anchor="w", pady=(18, 0))
        self.password.bind("<Return>", lambda e: self.login())
        self.username.bind("<Return>", lambda e: self.password.focus_set())

    def _toggle_pw(self):
        hidden = self.password.cget("show") == "•"
        self.password.configure(show="" if hidden else "•")
        self.eye.configure(image=icon("eye-off" if hidden else "eye", 18, "muted"))

    def reset(self):
        self.password.delete(0, "end")
        self.error.configure(text="")
        self.inst.configure(text=self.app.db.get_setting("institution_name") or
                            "Welcome back")
        default = self.app.db.authenticate(config.DEFAULT_ADMIN_USER, config.DEFAULT_ADMIN_PASSWORD)
        self.hint.configure(text=f"First time here? Use {config.DEFAULT_ADMIN_USER} / "
                                 f"{config.DEFAULT_ADMIN_PASSWORD}, then change the password."
                            if default else "")
        self.after(100, self.username.focus_set)

    def login(self):
        now = time.time()
        if now < self.locked_until:
            self.error.configure(text=f"Too many attempts. Try again in "
                                      f"{int(self.locked_until - now) + 1} seconds.")
            return
        user = self.app.db.authenticate(self.username.get(), self.password.get())
        if not user:
            self.failures += 1
            self.password.delete(0, "end")
            if self.failures >= 5:
                self.locked_until = now + 30
                self.failures = 0
                self.error.configure(text="Too many attempts. Locked for 30 seconds.")
            else:
                self.error.configure(text="That username and password don't match.")
            return
        self.failures = 0
        self.app.on_login(user)


# ====================================================================== shell
class Shell(ctk.CTkFrame):
    def __init__(self, app, ctx):
        super().__init__(app, fg_color=T.PALETTE["bg"], corner_radius=0)
        self.app, self.ctx = app, ctx
        self.sidebar = ctk.CTkFrame(self, fg_color=T.PALETTE["sidebar"], corner_radius=0,
                                    width=236)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        brand_row = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand_row.pack(fill="x", padx=20, pady=(24, 28))
        ctk.CTkLabel(brand_row, text="", image=brand.logo(34)).pack(side="left")
        ctk.CTkLabel(brand_row, text="FaceAttend", font=T.f("h2"), text_color="#FFFFFF").pack(
            side="left", padx=(10, 0))

        self.nav_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.nav_frame.pack(fill="x", padx=12)
        self.nav_buttons = {}

        # user card at the bottom
        bottom = ctk.CTkFrame(self.sidebar, fg_color=T.PALETTE["sidebar_hover"],
                              corner_radius=T.R_CARD)
        bottom.pack(side="bottom", fill="x", padx=12, pady=14)
        top = ctk.CTkFrame(bottom, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(12, 6))
        self.user_avatar = ctk.CTkLabel(top, text="")
        self.user_avatar.pack(side="left")
        names = ctk.CTkFrame(top, fg_color="transparent")
        names.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self.user_label = ctk.CTkLabel(names, text="", font=T.f("body_bold"),
                                       text_color="#FFFFFF", anchor="w")
        self.user_label.pack(anchor="w", fill="x")
        self.role_label = ctk.CTkLabel(names, text="", font=T.f("small"),
                                       text_color=T.PALETTE["sidebar_text"], anchor="w")
        self.role_label.pack(anchor="w")
        tools = ctk.CTkFrame(bottom, fg_color="transparent")
        tools.pack(fill="x", padx=8, pady=(0, 10))
        self.mode_btn = self._tool(tools, "moon", self.toggle_mode)
        self._tool(tools, "key", self.change_password)
        self._tool(tools, "log-out", app.logout)

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(side="left", fill="both", expand=True, padx=32, pady=(26, 24))
        self.pages = {}
        self.current = None

    def _tool(self, parent, icon_name, cmd):
        b = ctk.CTkButton(parent, text="", width=40, height=34, corner_radius=8,
                          fg_color="transparent", hover_color=T.PALETTE["sidebar_active"],
                          image=icon(icon_name, 17, "#B7CEC5"), command=cmd)
        b.pack(side="left", padx=2)
        return b

    def build_for_user(self):
        for w in self.nav_frame.winfo_children():
            w.destroy()
        for p in self.pages.values():
            p.destroy()
        self.pages.clear()
        self.nav_buttons.clear()
        self.current = None
        for key, label, ic, cls, admin_only in NAV:
            if admin_only and not self.ctx.is_admin:
                continue
            b = ctk.CTkButton(
                self.nav_frame, text="  " + label, anchor="w", height=44,
                corner_radius=T.R_CONTROL, font=T.f("nav"), fg_color="transparent",
                hover_color=T.PALETTE["sidebar_hover"], text_color=T.PALETTE["sidebar_text"],
                image=icon(ic, 19, "#B7CEC5"), command=lambda k=key: self.show(k))
            b.pack(fill="x", pady=2)
            b._icon_name = ic
            self.nav_buttons[key] = b
            self.pages[key] = cls(self.content, self.ctx)
        u = self.ctx.user
        name = u["full_name"] or u["username"]
        self.user_label.configure(text=name if len(name) <= 20 else name[:19] + "…")
        self.role_label.configure(text=f"{u['role'].capitalize()}, @{u['username']}")
        self.user_avatar.configure(image=avatars.ctk_avatar(None, {"id": -u["id"], "name": name}, 36))
        self._sync_mode_icon()

    def show(self, key):
        if key not in self.pages:
            return
        if self.current:
            self.pages[self.current].on_hide()
            self.pages[self.current].pack_forget()
            old = self.nav_buttons[self.current]
            old.configure(fg_color="transparent", text_color=T.PALETTE["sidebar_text"],
                          image=icon(old._icon_name, 19, "#B7CEC5"))
        self.current = key
        b = self.nav_buttons[key]
        b.configure(fg_color=T.PALETTE["sidebar_active"], text_color="#FFFFFF",
                    image=icon(b._icon_name, 19, "#5FD3AC"))
        page = self.pages[key]
        page.pack(fill="both", expand=True)
        page.on_show()

    def hide_current(self):
        if self.current:
            self.pages[self.current].on_hide()

    def toggle_mode(self):
        self.ctx.set_appearance("Light" if T.is_dark() else "Dark")

    def _sync_mode_icon(self):
        self.mode_btn.configure(image=icon("sun" if T.is_dark() else "moon", 17, "#B7CEC5"))

    def on_theme(self):
        self._sync_mode_icon()
        if self.current:
            self.pages[self.current].on_theme()

    def change_password(self):
        data = PasswordDialog(self).show()
        if not data:
            return
        u = self.ctx.user
        if not self.ctx.db.authenticate(u["username"], data["current"]):
            notify.alert(self, "Current password is wrong",
                         "Your password wasn't changed. Try again.")
            return
        self.ctx.db.set_password(u["id"], data["new"])
        notify.toast(self, "Password changed", "Use it next time you sign in.")


# ======================================================================== app
class App(ctk.CTk):
    def __init__(self, db, engine):
        fonts.load_fonts()
        mode = db.get_setting("appearance", "Light") or "Light"
        ctk.set_appearance_mode(mode)
        ctk.set_default_color_theme("green")
        super().__init__(fg_color=T.PALETTE["bg"])
        self.db, self.engine = db, engine
        self.title(config.APP_TITLE)
        self.geometry("1280x800")
        self.minsize(1180, 740)
        T.init_fonts(self)
        T.style_ttk(self)
        self.after(0, self._maximise)
        self.ctx = AppContext(self, db, engine)
        self.login_frame = LoginFrame(self)
        self.shell = Shell(self, self.ctx)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.show_login()

    def _maximise(self):
        try:
            self.state("zoomed")          # Windows
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)   # Linux
            except tk.TclError:
                pass

    def apply_appearance(self, mode):
        T.set_mode(mode, self)
        self.shell.on_theme()

    def show_login(self):
        self.shell.pack_forget()
        self.login_frame.pack(fill="both", expand=True)
        self.login_frame.reset()

    def on_login(self, user):
        self.ctx.user = user
        self.login_frame.pack_forget()
        self.shell.build_for_user()
        self.shell.pack(fill="both", expand=True)
        self.shell.show("dashboard")
        if user["username"] == config.DEFAULT_ADMIN_USER and self.db.authenticate(
                config.DEFAULT_ADMIN_USER, config.DEFAULT_ADMIN_PASSWORD):
            self.after(600, lambda: notify.toast(
                self, "Change the default password",
                "You're using admin123. Use the key button at the bottom left.", "warning", 7000))

    def logout(self):
        self.shell.hide_current()
        self.ctx.user = None
        self.show_login()

    def on_close(self):
        self.shell.hide_current()
        self.db.close()
        self.destroy()
