"""Reusable UI components. Screens are built from these so every page looks and
behaves the same (button hierarchy, spacing, tables, empty states)."""
from tkinter import ttk

import customtkinter as ctk

from . import theme as T
from .icons import icon

# ---------------------------------------------------------------- buttons
# Hierarchy: one "primary" per area; "secondary" for other actions;
# "ghost" for low-emphasis; "danger" only for destructive actions.
_VARIANTS = {
    "primary":   dict(fg="primary", hover="primary_hover", text="on_primary", border=None),
    "secondary": dict(fg="surface", hover="surface_alt", text="text", border="border"),
    "ghost":     dict(fg="transparent", hover="surface_alt", text="muted", border=None),
    "danger":    dict(fg="surface", hover="absent_soft", text="absent", border="border"),
    "soft":      dict(fg="primary_soft", hover="border", text="primary", border=None),
    "danger_solid": dict(fg="absent", hover="absent_hover", text="on_primary", border=None),
}


def Button(parent, text="", command=None, variant="secondary", icon_name=None, size="md",
           width=None, **kw):
    v = _VARIANTS[variant]
    h = {"sm": 30, "md": 38, "lg": 46}[size]
    font = T.f("small_bold") if size == "sm" else T.f("body_bold")
    pal = T.PALETTE
    btn = ctk.CTkButton(
        parent, text=text, command=command, height=h,
        width=width if width is not None else (h if not text else 0),
        corner_radius=T.R_CONTROL, font=font,
        fg_color=pal[v["fg"]] if v["fg"] != "transparent" else "transparent",
        hover_color=pal[v["hover"]], text_color=pal[v["text"]],
        text_color_disabled=pal["faint"],
        border_width=1 if v["border"] else 0,
        border_color=pal[v["border"]] if v["border"] else None,
        image=icon(icon_name, 16 if size != "lg" else 18, v["text"]) if icon_name else None,
        compound="left", anchor="center", **kw)
    if text:
        btn.configure(width=width or 0)
    return btn


def IconButton(parent, icon_name, command=None, variant="ghost", size=36, tooltip=None, **kw):
    v = _VARIANTS[variant]
    pal = T.PALETTE
    return ctk.CTkButton(
        parent, text="", command=command, width=size, height=size, corner_radius=T.R_CONTROL,
        fg_color=pal[v["fg"]] if v["fg"] != "transparent" else "transparent",
        hover_color=pal[v["hover"]], border_width=1 if v["border"] else 0,
        border_color=pal[v["border"]] if v["border"] else None,
        image=icon(icon_name, 18, v["text"]), **kw)


# ------------------------------------------------------------- containers
class Card(ctk.CTkFrame):
    """Flat surface with a hairline border (no drop shadow)."""

    def __init__(self, parent, radius=T.R_CARD, **kw):
        super().__init__(parent, fg_color=T.PALETTE["surface"], corner_radius=radius,
                         border_width=1, border_color=T.PALETTE["border"], **kw)


def Label(parent, text="", font="body", color="text", **kw):
    return ctk.CTkLabel(parent, text=text, font=T.f(font), text_color=T.PALETTE[color],
                        anchor=kw.pop("anchor", "w"), justify=kw.pop("justify", "left"), **kw)


class PageHeader(ctk.CTkFrame):
    """Title + subtitle on the left, the page's main actions on the right."""

    def __init__(self, parent, title, subtitle=""):
        super().__init__(parent, fg_color="transparent")
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.pack(side="left", fill="y")
        self.title = Label(left, title, "h1")
        self.title.pack(anchor="w")
        self.subtitle = Label(left, subtitle, "body", "muted")
        self.subtitle.pack(anchor="w", pady=(2, 0))
        self.actions = ctk.CTkFrame(self, fg_color="transparent")
        self.actions.pack(side="right", anchor="e")


class Pill(ctk.CTkLabel):
    """Small rounded status badge: Present / Late / Absent / Admin…"""

    def __init__(self, parent, text, kind="Present", **kw):
        fg, bg = T.STATUS.get(kind, ("primary", "primary_soft"))
        if kind == "info":
            fg, bg = "info", "info_soft"
        elif kind == "neutral":
            fg, bg = "muted", "surface_alt"
        super().__init__(parent, text=f"  {text}  ", font=T.f("small_bold"),
                         text_color=T.PALETTE[fg], fg_color=T.PALETTE[bg], corner_radius=10,
                         height=22, **kw)

    def set(self, text, kind):
        fg, bg = T.STATUS.get(kind, ("primary", "primary_soft"))
        if kind == "neutral":
            fg, bg = "muted", "surface_alt"
        self.configure(text=f"  {text}  ", text_color=T.PALETTE[fg], fg_color=T.PALETTE[bg])


class SearchEntry(ctk.CTkFrame):
    def __init__(self, parent, placeholder="Search", on_change=None, width=260):
        super().__init__(parent, fg_color=T.PALETTE["surface_alt"], corner_radius=T.R_CONTROL,
                         height=38, width=width)
        self.pack_propagate(False)
        ctk.CTkLabel(self, text="", image=icon("search", 16, "muted"), width=20).pack(
            side="left", padx=(12, 4))
        self.entry = ctk.CTkEntry(self, placeholder_text=placeholder, border_width=0,
                                  fg_color="transparent", font=T.f("body"),
                                  text_color=T.PALETTE["text"],
                                  placeholder_text_color=T.PALETTE["faint"])
        self.entry.pack(side="left", fill="both", expand=True, padx=(0, 10))
        if on_change:
            self.entry.bind("<KeyRelease>", lambda e: on_change())

    def get(self):
        return self.entry.get().strip()

    def clear(self):
        self.entry.delete(0, "end")

    def insert(self, text):
        self.entry.insert(0, text)


def Dropdown(parent, values, variable=None, command=None, width=170):
    return ctk.CTkOptionMenu(
        parent, values=values, variable=variable, command=command, width=width, height=38,
        corner_radius=T.R_CONTROL, font=T.f("body"), dropdown_font=T.f("body"),
        fg_color=T.PALETTE["surface_alt"], button_color=T.PALETTE["surface_alt"],
        button_hover_color=T.PALETTE["border"], text_color=T.PALETTE["text"],
        dropdown_fg_color=T.PALETTE["surface"], dropdown_hover_color=T.PALETTE["surface_alt"],
        dropdown_text_color=T.PALETTE["text"], dynamic_resizing=False)


def Entry(parent, placeholder="", show=None, width=280, **kw):
    return ctk.CTkEntry(parent, placeholder_text=placeholder, show=show, width=width, height=40,
                        corner_radius=T.R_CONTROL, border_width=1,
                        border_color=T.PALETTE["border"], fg_color=T.PALETTE["surface_alt"],
                        text_color=T.PALETTE["text"], font=T.f("body"),
                        placeholder_text_color=T.PALETTE["faint"], **kw)


def Field(parent, label, widget_factory, hint=None):
    """Label above an input (the layout used in all forms)."""
    box = ctk.CTkFrame(parent, fg_color="transparent")
    Label(box, label, "small_bold", "muted").pack(anchor="w", pady=(0, 6))
    w = widget_factory(box)
    w.pack(fill="x")
    if hint:
        Label(box, hint, "small", "faint", wraplength=360).pack(anchor="w", pady=(4, 0))
    return box, w


def Divider(parent):
    return ctk.CTkFrame(parent, height=1, fg_color=T.PALETTE["border"], corner_radius=0)


class EmptyState(ctk.CTkFrame):
    def __init__(self, parent, icon_name, title, text, action_text=None, action=None, wrap=360):
        super().__init__(parent, fg_color="transparent")
        bubble = ctk.CTkLabel(self, text="", image=icon(icon_name, 26, "primary"),
                              width=60, height=60, fg_color=T.PALETTE["primary_soft"],
                              corner_radius=30)
        bubble.pack(pady=(0, 14))
        Label(self, title, "h2", anchor="center").pack()
        Label(self, text, "body", "muted", anchor="center", justify="center",
              wraplength=wrap).pack(pady=(4, 14))
        if action_text:
            Button(self, action_text, action, "primary").pack()


# ------------------------------------------------------------------ table
class DataTable(ctk.CTkFrame):
    """ttk.Treeview styled to the theme, with optional avatar column,
    status colouring and an empty-state message."""

    def __init__(self, parent, columns, widths=None, anchors=None, avatar_label=None,
                 avatar_width=240, height=10, empty=("inbox", "Nothing here yet", "")):
        super().__init__(parent, fg_color="transparent")
        self.keys = [k for k, _ in columns]
        self.images = {}
        self.has_avatar = avatar_label is not None
        self.tree = ttk.Treeview(self, columns=self.keys, style="App.Treeview", height=height,
                                 show="tree headings" if self.has_avatar else "headings",
                                 selectmode="browse")
        if self.has_avatar:
            self.tree.heading("#0", text="   " + avatar_label, anchor="w")
            self.tree.column("#0", width=avatar_width, minwidth=160, stretch=True, anchor="w")
        for key, label in columns:
            self.tree.heading(key, text=label, anchor=(anchors or {}).get(key, "w"))
            self.tree.column(key, width=(widths or {}).get(key, 120), minwidth=60,
                             anchor=(anchors or {}).get(key, "w"), stretch=True)
        self.scroll = ctk.CTkScrollbar(self, command=self.tree.yview, width=12,
                                       button_color=T.PALETTE["border"],
                                       button_hover_color=T.PALETTE["faint"])
        self.tree.configure(yscrollcommand=self.scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")
        self._empty_cfg = empty
        self._empty = None
        self.restyle()
        T.on_mode_change(self.restyle)

    def restyle(self):
        # calm colouring: normal rows stay neutral, absences fade back,
        # late arrivals are tinted, red is kept for real warnings
        self.tree.tag_configure("Present", foreground=T.c("text"))
        self.tree.tag_configure("Late", foreground=T.c("late"))
        self.tree.tag_configure("Absent", foreground=T.c("faint"))
        self.tree.tag_configure("dim", foreground=T.c("faint"))
        self.tree.tag_configure("warn", foreground=T.c("absent"))
        self.tree.tag_configure("muted", foreground=T.c("muted"))
        self.tree.tag_configure("bold", font=T.tkfont(10, bold=True))
        self.tree.configure(style="App.Treeview")

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self.images.clear()

    def insert(self, iid, values, text="", image=None, tags=()):
        kw = {}
        if self.has_avatar:
            kw["text"] = "  " + text
            if image is not None:
                self.images[iid] = image
                kw["image"] = image
        self.tree.insert("", "end", iid=str(iid), values=values, tags=tags, **kw)

    def selected(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    def select(self, iid):
        if self.tree.exists(str(iid)):
            self.tree.selection_set(str(iid))
            self.tree.see(str(iid))

    def show_empty(self, show=True, title=None, text=None):
        if self._empty is not None:
            self._empty.destroy()
            self._empty = None
        if show:
            ic, t, x = self._empty_cfg
            self._empty = EmptyState(self, ic, title or t, text if text is not None else x)
            self._empty.place(relx=0.5, rely=0.45, anchor="center")
