"""Today at a glance: the attendance ring, this week's bars, today's check-ins."""
import datetime as dt

import customtkinter as ctk

from . import avatars, charts
from . import theme as T
from .base import Page
from .icons import icon
from .widgets import Button, Card, EmptyState, Label, PageHeader, Pill


class DashboardPage(Page):
    title = "Today"

    def __init__(self, parent, ctx):
        super().__init__(parent, ctx)
        self.header = PageHeader(self, "Today", "")
        self.header.pack(fill="x")
        Button(self.header.actions, "Start attendance", lambda: ctx.navigate("attendance"),
               "primary", "camera", size="lg").pack()

        # setup banner (only when something needs doing)
        self.banner = ctk.CTkFrame(self, fg_color=T.PALETTE["late_soft"], corner_radius=T.R_CARD)
        self.banner_icon = ctk.CTkLabel(self.banner, text="", image=icon("alert-triangle", 18, "late"))
        self.banner_icon.pack(side="left", padx=(16, 10), pady=12)
        self.banner_text = Label(self.banner, "", "body", "text")
        self.banner_text.pack(side="left", pady=12)
        self.banner_btn = Button(self.banner, "Go to students", lambda: ctx.navigate("students"),
                                 "secondary", size="sm")
        self.banner_btn.pack(side="right", padx=12)

        self.grid_area = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_area.pack(fill="both", expand=True, pady=(20, 0))
        g = self.grid_area
        g.columnconfigure(0, weight=3, uniform="d")
        g.columnconfigure(1, weight=2, uniform="d")
        g.rowconfigure(1, weight=1)

        # hero: attendance ring
        hero = Card(g, radius=T.R_HERO)
        hero.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        inner = ctk.CTkFrame(hero, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=26, pady=22)
        ring_box = ctk.CTkFrame(inner, fg_color="transparent", width=176, height=176)
        ring_box.pack(side="left")
        ring_box.pack_propagate(False)
        self.ring = ctk.CTkLabel(ring_box, text="")
        self.ring.place(relx=0.5, rely=0.5, anchor="center")
        self.ring_pct = ctk.CTkLabel(ring_box, text="0%", font=T.f("display"),
                                     text_color=T.PALETTE["text"], fg_color=T.PALETTE["surface"])
        self.ring_pct.place(relx=0.5, rely=0.46, anchor="center")
        self.ring_sub = ctk.CTkLabel(ring_box, text="present", font=T.f("small"),
                                     text_color=T.PALETTE["muted"], fg_color=T.PALETTE["surface"])
        self.ring_sub.place(relx=0.5, rely=0.64, anchor="center")

        facts = ctk.CTkFrame(inner, fg_color="transparent")
        facts.pack(side="left", fill="both", expand=True, padx=(28, 0))
        self.big = Label(facts, "0 of 0", "display")
        self.big.pack(anchor="w", pady=(10, 0))
        Label(facts, "students checked in today", "body", "muted").pack(anchor="w")
        legend = ctk.CTkFrame(facts, fg_color="transparent")
        legend.pack(anchor="w", pady=(18, 0))
        self.legend = {}
        for key, label in (("Present", "On time"), ("Late", "Late"), ("Absent", "Not yet")):
            r = ctk.CTkFrame(legend, fg_color="transparent")
            r.pack(side="left", padx=(0, 22))
            ctk.CTkFrame(r, width=10, height=10, corner_radius=5,
                         fg_color=T.PALETTE[T.STATUS[key][0]]).pack(side="left", padx=(0, 7))
            val = Label(r, "0", "h3")
            val.pack(side="left")
            Label(r, f"  {label}", "small", "muted").pack(side="left")
            self.legend[key] = val

        # week chart
        week = Card(g)
        week.grid(row=1, column=0, sticky="nsew", padx=(0, 16), pady=(16, 0))
        Label(week, "This week", "h2").pack(anchor="w", padx=22, pady=(18, 0))
        Label(week, "Students checked in per day", "small", "muted").pack(anchor="w", padx=22)
        self.chart = ctk.CTkLabel(week, text="")
        self.chart.pack(fill="both", expand=True, padx=16, pady=(8, 14))

        # check-ins list
        right = Card(g, radius=T.R_HERO)
        right.grid(row=0, column=1, rowspan=2, sticky="nsew")
        rh = ctk.CTkFrame(right, fg_color="transparent")
        rh.pack(fill="x", padx=22, pady=(20, 6))
        Label(rh, "Check-ins today", "h2").pack(side="left")
        self.count_pill = Pill(rh, "0", "neutral")
        self.count_pill.pack(side="right")
        self.list = ctk.CTkScrollableFrame(right, fg_color="transparent",
                                           scrollbar_button_color=T.PALETTE["border"])
        self.list.pack(fill="both", expand=True, padx=10, pady=(0, 12))

        self.footer = Label(self, "", "small", "faint")
        self.footer.pack(anchor="w", pady=(12, 0))

    def on_show(self):
        db, engine = self.ctx.db, self.ctx.engine
        u = self.ctx.user
        first = (u["full_name"] or u["username"]).split()[0] if u else ""
        if first.lower().rstrip(".") in ("dr", "mr", "ms", "mrs", "prof") and u and u["full_name"]:
            first = " ".join(u["full_name"].split()[:2])
        self.header.title.configure(text=f"{T.greeting()}, {first}")
        self.header.subtitle.configure(text=T.nice_date(dt.date.today()))

        s = db.today_stats()
        on_time = s["present"] - s["late"]
        self.ring.configure(image=charts.ring(on_time, s["late"], s["total"]))
        self.ring_pct.configure(text=f"{s['rate']:.0f}%")
        self.big.configure(text=f"{s['present']} of {s['total']}")
        self.legend["Present"].configure(text=str(on_time))
        self.legend["Late"].configure(text=str(s["late"]))
        self.legend["Absent"].configure(text=str(s["absent"]))
        self.chart.configure(image=charts.week_bars(db.counts_by_day(7), 560, 210))

        for w in self.list.winfo_children():
            w.destroy()
        rows = db.attendance_on(T.today_str())
        self.count_pill.set(str(len(rows)), "Present" if rows else "neutral")
        if not rows:
            EmptyState(self.list, "clock", "No one yet",
                       "Students appear here as they check in.").pack(pady=60)
        for r in rows[:40]:
            self._checkin_row(r)

        students = db.list_students()
        enrolled = sum(1 for st in students if engine.sample_count(st["id"]) > 0)
        if not students:
            self._banner("Add your students and capture their faces to start taking attendance.")
        elif enrolled < len(students):
            n = len(students) - enrolled
            self._banner(f"{n} student{'s' if n != 1 else ''} can't check in yet: "
                         f"their face hasn't been captured.")
        else:
            self.banner.pack_forget()
        self.footer.configure(text=f"{enrolled} of {len(students)} students have a face "
                                   f"captured.  Recognition works offline on this computer.")

    def _banner(self, text):
        self.banner_text.configure(text=text)
        self.banner.pack(fill="x", pady=(16, 0), after=self.header)

    def _checkin_row(self, r):
        row = ctk.CTkFrame(self.list, fg_color="transparent", height=56)
        row.pack(fill="x", pady=2)
        st = {"id": r["student_id"], "name": r["name"]}
        ctk.CTkLabel(row, text="", image=avatars.ctk_avatar(self.ctx.engine, st, 38)).pack(
            side="left", padx=(8, 12), pady=6)
        txt = ctk.CTkFrame(row, fg_color="transparent")
        txt.pack(side="left", fill="x", expand=True)
        Label(txt, r["name"], "body_bold").pack(anchor="w")
        Label(txt, f"{r['roll_no']}" + (f", {r['class_name']}" if r["class_name"] else ""),
              "small", "muted").pack(anchor="w")
        right = ctk.CTkFrame(row, fg_color="transparent")
        right.pack(side="right", padx=8)
        Label(right, dt.datetime.strptime(r["time"], "%H:%M:%S").strftime("%I:%M %p").lstrip("0"),
              "small_bold", anchor="e").pack(anchor="e")
        Pill(right, r["status"] if r["method"] == "face" else "Manual",
             r["status"] if r["method"] == "face" else "neutral").pack(anchor="e", pady=(2, 0))
