"""Design tokens (colour, type, spacing) and helpers shared by every screen.

Colours are (light, dark) pairs, which CustomTkinter switches automatically.
Plain Tk widgets (Treeview, Canvas, video Label) read the current value with
`c(token)` and re-style themselves through `on_mode_change` callbacks.
"""
import datetime as dt
import queue
import threading
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

# ----------------------------------------------------------------- colour
# Identity: Islamia University green, a cool green-tinted paper, deep pine.
PALETTE = {
    "bg":            ("#F5F8F6", "#0B1814"),   # window background
    "surface":       ("#FFFFFF", "#12241E"),   # cards
    "surface_alt":   ("#EEF4F1", "#183028"),   # inputs, table header, hover
    "border":        ("#DDE7E2", "#22413A"),
    "text":          ("#13241E", "#E6F0EC"),
    "muted":         ("#5E7169", "#93A9A0"),
    "faint":         ("#8EA19A", "#5F7A70"),
    "primary":       ("#0F7B5F", "#2BB38A"),   # emerald
    "primary_hover": ("#0B6650", "#25A07B"),
    "primary_soft":  ("#E1F2EB", "#173F33"),
    "on_primary":    ("#FFFFFF", "#05140F"),
    "sidebar":       ("#0F2A22", "#08130F"),
    "sidebar_hover": ("#173A30", "#11251E"),
    "sidebar_active": ("#1F4A3D", "#173A30"),
    "sidebar_text":  ("#B7CEC5", "#9DB5AB"),
    "present":       ("#12805F", "#3CC795"),
    "present_soft":  ("#E1F2EB", "#173F33"),
    "late":          ("#B7780A", "#F0B53D"),
    "late_soft":     ("#FBF1DC", "#3A2F14"),
    "absent":        ("#C23A52", "#F0768A"),
    "absent_soft":   ("#FBE6EA", "#40202A"),
    "absent_hover":  ("#A52F45", "#E5627A"),
    "info_soft":     ("#E6EEFB", "#1A2A44"),
    "info":          ("#2C5BB8", "#7EA6F2"),
    "video_bg":      ("#0F2A22", "#060E0B"),
}

STATUS = {"Present": ("present", "present_soft"), "Late": ("late", "late_soft"),
          "Absent": ("absent", "absent_soft")}

# corner radius by role (not one radius for everything)
R_HERO, R_CARD, R_CONTROL, R_ROW, R_PILL = 18, 14, 10, 8, 999

_mode_callbacks = []


def is_dark() -> bool:
    return ctk.get_appearance_mode() == "Dark"


def c(token: str) -> str:
    """Current hex value of a colour token (for plain Tk widgets)."""
    light, dark = PALETTE[token]
    return dark if is_dark() else light


def on_mode_change(callback) -> None:
    _mode_callbacks.append(callback)


def set_mode(mode: str, root=None) -> None:
    ctk.set_appearance_mode(mode)
    if root is not None:
        style_ttk(root)
    alive = []
    for cb in _mode_callbacks:
        try:
            cb()
            alive.append(cb)
        except tk.TclError:
            pass          # widget was destroyed; drop its callback
    _mode_callbacks[:] = alive


# ------------------------------------------------------------------ fonts
FONTS = {}


def init_fonts(root) -> None:
    from . import fonts
    fam = fonts.resolve(root)
    reg, semi, bold, xb = fam["regular"], fam["semibold"], fam["bold"], fam["extrabold"]
    semi_w = "normal" if semi != reg else "bold"
    xb_w = "normal" if xb != reg else "bold"
    FONTS.update({
        # size scale ~ 1.2 ratio: 11 / 12.5 / 14 / 17 / 22 / 30
        "display": ctk.CTkFont(family=xb, size=30, weight=xb_w),
        "h1": ctk.CTkFont(family=xb, size=22, weight=xb_w),
        "h2": ctk.CTkFont(family=semi, size=16, weight=semi_w),
        "h3": ctk.CTkFont(family=semi, size=13, weight=semi_w),
        "body": ctk.CTkFont(family=reg, size=13),
        "body_bold": ctk.CTkFont(family=bold, size=13, weight="bold"),
        "small": ctk.CTkFont(family=reg, size=11),
        "small_bold": ctk.CTkFont(family=bold, size=11, weight="bold"),
        "nav": ctk.CTkFont(family=semi, size=13, weight=semi_w),
        "stat": ctk.CTkFont(family=xb, size=26, weight=xb_w),
    })
    FONTS["_tk_family"] = reg
    FONTS["_tk_bold"] = bold


def f(name: str):
    return FONTS[name]


def tkfont(size=10, bold=False):
    """Font tuple for plain Tk/ttk widgets (point sizes)."""
    return (FONTS.get("_tk_bold" if bold else "_tk_family", "TkDefaultFont"), size,
            "bold" if bold else "normal")


# ------------------------------------------------------------- ttk tables
def style_ttk(root) -> None:
    """Style ttk.Treeview to match the current light/dark mode."""
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("App.Treeview", background=c("surface"), fieldbackground=c("surface"),
                    foreground=c("text"), rowheight=44, borderwidth=0, relief="flat",
                    font=tkfont(10))
    style.configure("App.Treeview.Heading", background=c("surface"), foreground=c("muted"),
                    font=tkfont(9, bold=True), relief="flat", borderwidth=0, padding=(8, 10))
    style.map("App.Treeview", background=[("selected", c("primary_soft"))],
              foreground=[("selected", c("text"))])
    style.map("App.Treeview.Heading", background=[("active", c("surface"))])
    style.layout("App.Treeview", [("App.Treeview.treearea", {"sticky": "nswe"})])
    style.configure("App.Vertical.TScrollbar", background=c("surface_alt"),
                    troughcolor=c("surface"), bordercolor=c("surface"), arrowcolor=c("muted"),
                    lightcolor=c("surface_alt"), darkcolor=c("surface_alt"), gripcount=0)


# ----------------------------------------------------------------- helpers
def today_str() -> str:
    return dt.date.today().isoformat()


def parse_date(text: str):
    try:
        return dt.datetime.strptime(text.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def nice_date(d: dt.date) -> str:
    return f"{d:%a}, {d.day} {d:%B %Y}"


def greeting() -> str:
    h = dt.datetime.now().hour
    return "Good morning" if h < 12 else ("Good afternoon" if h < 17 else "Good evening")


def run_in_thread(widget, func, on_done=None, on_error=None) -> None:
    """Run func() in a worker thread; call on_done(result) on the Tk thread."""
    q: "queue.Queue" = queue.Queue()

    def worker():
        try:
            q.put(("ok", func()))
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            q.put(("err", exc))

    def poll():
        try:
            if not widget.winfo_exists():
                return
        except tk.TclError:
            return
        try:
            kind, value = q.get_nowait()
        except queue.Empty:
            widget.after(100, poll)
            return
        if kind == "ok" and on_done:
            on_done(value)
        elif kind == "err":
            if on_error:
                on_error(value)
            else:
                from . import notify
                notify.alert(widget, "Something went wrong", str(value))

    threading.Thread(target=worker, daemon=True).start()
    widget.after(100, poll)
