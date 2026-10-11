import customtkinter as ctk


class Page(ctk.CTkFrame):
    """A screen shown in the main content area."""

    title = ""

    def __init__(self, parent, ctx):
        super().__init__(parent, fg_color="transparent")
        self.ctx = ctx

    def on_show(self):
        """Called every time the page becomes visible."""

    def on_hide(self):
        """Called when navigating away (stop cameras, timers…)."""

    def on_theme(self):
        """Called after light/dark mode changes (redraw images, tables)."""
        if self.winfo_ismapped():
            self.on_show()
