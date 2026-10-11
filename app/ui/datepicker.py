"""Date selector: ‹ [ Mon, 12 October 2026 ] › with a pop-up month calendar."""
import calendar
import datetime as dt

import customtkinter as ctk

from . import theme as T
from .icons import icon
from .widgets import IconButton


class DatePicker(ctk.CTkFrame):
    def __init__(self, parent, on_change=None, value=None, allow_future=False, compact=False):
        super().__init__(parent, fg_color="transparent")
        self.on_change = on_change
        self.allow_future = allow_future
        self.value = value or dt.date.today()
        self.compact = compact
        IconButton(self, "chevron-left", lambda: self.shift(-1), "secondary", 38).pack(side="left")
        self.btn = ctk.CTkButton(
            self, text="", height=38, width=210 if not compact else 150, corner_radius=T.R_CONTROL,
            fg_color=T.PALETTE["surface"], hover_color=T.PALETTE["surface_alt"],
            border_width=1, border_color=T.PALETTE["border"], text_color=T.PALETTE["text"],
            font=T.f("body_bold"), image=icon("calendar", 16, "primary"), compound="left",
            command=self.open_calendar)
        self.btn.pack(side="left", padx=6)
        self.next_btn = IconButton(self, "chevron-right", lambda: self.shift(1), "secondary", 38)
        self.next_btn.pack(side="left")
        self._popup = None
        self._render()

    # -------------------------------------------------------------- value
    def get(self) -> dt.date:
        return self.value

    def set(self, value: dt.date, notify=True):
        if not self.allow_future and value > dt.date.today():
            value = dt.date.today()
        self.value = value
        self._render()
        if notify and self.on_change:
            self.on_change(value)

    def shift(self, days):
        self.set(self.value + dt.timedelta(days=days))

    def _render(self):
        d = self.value
        label = (f"{d:%d %b %Y}" if self.compact else
                 ("Today, " if d == dt.date.today() else f"{d:%a}, ") + f"{d.day} {d:%B %Y}")
        self.btn.configure(text=f"  {label}")
        self.next_btn.configure(state="disabled" if (not self.allow_future and
                                                     d >= dt.date.today()) else "normal")

    # ----------------------------------------------------------- calendar
    def open_calendar(self):
        if self._popup is not None and self._popup.winfo_exists():
            self._popup.destroy()
            return
        self._popup = _CalendarPopup(self)


class _CalendarPopup(ctk.CTkToplevel):
    def __init__(self, picker: DatePicker):
        super().__init__(picker)
        self.picker = picker
        self.month = picker.value.replace(day=1)
        self.overrideredirect(True)
        self.configure(fg_color=T.PALETTE["border"])
        self.inner = ctk.CTkFrame(self, fg_color=T.PALETTE["surface"], corner_radius=0)
        self.inner.pack(padx=1, pady=1)
        x = picker.btn.winfo_rootx()
        y = picker.btn.winfo_rooty() + picker.btn.winfo_height() + 6
        self.geometry(f"+{x}+{y}")
        self._build()
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(100, self._watch_focus)

    def _watch_focus(self):
        # close when the user clicks elsewhere in the app
        try:
            self.picker.winfo_toplevel().bind("<Button-1>", self._outside, add="+")
        except Exception:  # noqa: BLE001
            pass

    def _outside(self, event):
        try:
            w = event.widget
            if str(w).startswith(str(self)):
                return
            if self.winfo_exists():
                self.destroy()
        except Exception:  # noqa: BLE001
            pass

    def _build(self):
        for w in self.inner.winfo_children():
            w.destroy()
        head = ctk.CTkFrame(self.inner, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(12, 6))
        IconButton(head, "chevron-left", lambda: self._move(-1), size=30).pack(side="left")
        ctk.CTkLabel(head, text=f"{self.month:%B %Y}", font=T.f("h3"),
                     text_color=T.PALETTE["text"]).pack(side="left", expand=True)
        IconButton(head, "chevron-right", lambda: self._move(1), size=30).pack(side="right")
        grid = ctk.CTkFrame(self.inner, fg_color="transparent")
        grid.pack(padx=12, pady=(0, 12))
        for i, name in enumerate(["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
            ctk.CTkLabel(grid, text=name, font=T.f("small"), text_color=T.PALETTE["faint"],
                         width=36).grid(row=0, column=i, pady=(0, 4))
        today = dt.date.today()
        for r, week in enumerate(calendar.Calendar().monthdatescalendar(self.month.year,
                                                                         self.month.month), 1):
            for col, day in enumerate(week):
                selected = day == self.picker.value
                is_today = day == today
                future = day > today and not self.picker.allow_future
                other = day.month != self.month.month
                b = ctk.CTkButton(
                    grid, text=str(day.day), width=36, height=32, corner_radius=8,
                    font=T.f("body_bold") if (selected or is_today) else T.f("body"),
                    fg_color=T.PALETTE["primary"] if selected else "transparent",
                    hover_color=T.PALETTE["primary_soft"],
                    text_color=T.PALETTE["on_primary"] if selected else (
                        T.PALETTE["faint"] if (other or future) else (
                            T.PALETTE["primary"] if is_today else T.PALETTE["text"])),
                    state="disabled" if future else "normal",
                    command=lambda d=day: self._pick(d))
                b.grid(row=r, column=col, padx=1, pady=1)
        ctk.CTkButton(self.inner, text="Today", height=30, fg_color="transparent",
                      hover_color=T.PALETTE["surface_alt"], text_color=T.PALETTE["primary"],
                      font=T.f("small_bold"), command=lambda: self._pick(today)).pack(
            pady=(0, 10))

    def _move(self, months):
        y, m = self.month.year, self.month.month + months
        y += (m - 1) // 12
        m = (m - 1) % 12 + 1
        self.month = dt.date(y, m, 1)
        self._build()

    def _pick(self, day):
        self.destroy()
        self.picker.set(day)
