"""App-style feedback: slide-in toasts, confirm dialogs and alerts.

toast()   - non-blocking confirmation of something that just happened
confirm() - asks before a consequential action (returns True / False)
alert()   - blocking message for errors the user must read
"""
import customtkinter as ctk

from . import theme as T
from .icons import icon

_KIND = {
    "success": ("check-circle", "present"),
    "info": ("info", "info"),
    "warning": ("alert-triangle", "late"),
    "error": ("x-circle", "absent"),
}
_stack = []


def _app_root(widget):
    top = widget.winfo_toplevel()
    root = getattr(top, "master", None)
    # toasts always appear in the main window, even when raised from a dialog
    while root is not None and not isinstance(top, ctk.CTk):
        top, root = root.winfo_toplevel(), getattr(root, "master", None)
    return top


def toast(widget, title, message="", kind="success", duration=3200):
    try:
        root = _app_root(widget)
    except Exception:  # noqa: BLE001
        return
    ic, color = _KIND.get(kind, _KIND["info"])
    card = ctk.CTkFrame(root, fg_color=T.PALETTE["surface"], corner_radius=12, border_width=1,
                        border_color=T.PALETTE["border"])
    stripe = ctk.CTkFrame(card, width=4, height=10, fg_color=T.PALETTE[color], corner_radius=2)
    stripe.pack(side="left", fill="y", padx=(10, 0), pady=12)
    ctk.CTkLabel(card, text="", image=icon(ic, 20, color), width=24).pack(
        side="left", padx=(10, 8), pady=12)
    body = ctk.CTkFrame(card, fg_color="transparent")
    body.pack(side="left", padx=(0, 18), pady=10)
    ctk.CTkLabel(body, text=title, font=T.f("body_bold"), text_color=T.PALETTE["text"],
                 anchor="w").pack(anchor="w")
    if message:
        ctk.CTkLabel(body, text=message, font=T.f("small"), text_color=T.PALETTE["muted"],
                     anchor="w", justify="left", wraplength=320).pack(anchor="w")

    _stack.append(card)
    card.update_idletasks()

    def layout():
        y = -24
        for c in reversed(_stack):
            if c.winfo_exists():
                c.place(relx=1.0, rely=1.0, x=-24, y=y, anchor="se")
                y -= c.winfo_reqheight() + 10
    # slide in from the right (responds to the user's action, then settles)
    steps = 8

    def slide(i=0):
        if not card.winfo_exists():
            return
        layout()
        card.place_configure(x=-24 + int(60 * (1 - i / steps) ** 2))
        if i < steps:
            card.after(16, slide, i + 1)
    slide()

    def close():
        if card in _stack:
            _stack.remove(card)
        if card.winfo_exists():
            card.destroy()
        layout()
    card.after(duration, close)
    card.bind("<Button-1>", lambda e: close())


class _Modal(ctk.CTkToplevel):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.resizable(False, False)
        self.configure(fg_color=T.PALETTE["surface"])
        self.transient(parent.winfo_toplevel())
        self.result = None
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda e: self._cancel())

    def _cancel(self):
        self.result = False
        self.destroy()

    def run(self):
        self.update_idletasks()
        top = self.master.winfo_toplevel()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = top.winfo_rootx() + (top.winfo_width() - w) // 2
        y = top.winfo_rooty() + (top.winfo_height() - h) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.deiconify()
        self.lift()
        self.after(50, self._grab)
        self.wait_window()
        return self.result

    def _grab(self):
        try:
            self.grab_set()
            self.focus_force()
        except Exception:  # noqa: BLE001 - window may already be gone
            pass


def _message_dialog(parent, title, message, icon_name, color, buttons):
    dlg = _Modal(parent, title)
    body = ctk.CTkFrame(dlg, fg_color="transparent")
    body.pack(padx=28, pady=(26, 22), fill="both")
    head = ctk.CTkFrame(body, fg_color="transparent")
    head.pack(fill="x")
    soft = {"absent": "absent_soft", "late": "late_soft", "present": "present_soft",
            "info": "info_soft", "primary": "primary_soft"}[color]
    ctk.CTkLabel(head, text="", image=icon(icon_name, 22, color), width=44, height=44,
                 corner_radius=22, fg_color=T.PALETTE[soft]).pack(side="left", anchor="n")
    txt = ctk.CTkFrame(head, fg_color="transparent")
    txt.pack(side="left", padx=(14, 0), fill="x")
    ctk.CTkLabel(txt, text=title, font=T.f("h2"), text_color=T.PALETTE["text"],
                 anchor="w").pack(anchor="w")
    ctk.CTkLabel(txt, text=message, font=T.f("body"), text_color=T.PALETTE["muted"],
                 anchor="w", justify="left", wraplength=340).pack(anchor="w", pady=(4, 0))
    row = ctk.CTkFrame(body, fg_color="transparent")
    row.pack(fill="x", pady=(22, 0))
    from .widgets import Button
    for text, value, variant in reversed(buttons):
        b = Button(row, text, lambda v=value: (setattr(dlg, "result", v), dlg.destroy()),
                   variant, width=110)
        b.pack(side="right", padx=(8, 0))
    dlg.bind("<Return>", lambda e: (setattr(dlg, "result", buttons[-1][1]), dlg.destroy()))
    return dlg.run()


def confirm(parent, title, message, confirm_text="Confirm", danger=False) -> bool:
    return bool(_message_dialog(
        parent, title, message, "alert-triangle" if danger else "info",
        "absent" if danger else "primary",
        [("Cancel", False, "secondary"),
         (confirm_text, True, "danger_solid" if danger else "primary")]))


def alert(parent, title, message, kind="error") -> None:
    ic, color = _KIND.get(kind, _KIND["error"])
    _message_dialog(parent, title, message, ic, color, [("OK", True, "primary")])
