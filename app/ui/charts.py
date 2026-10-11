"""Anti-aliased charts rendered with Pillow (Tk canvas arcs look jagged on Windows)."""
import datetime as dt
import math

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

from . import fonts
from . import theme as T

SS = 3  # supersampling factor


def _font(px, bold=False):
    name = "PlusJakartaSans-Bold.ttf" if bold else "PlusJakartaSans-Medium.ttf"
    try:
        return ImageFont.truetype(f"{fonts.FONT_DIR}/{name}", px)
    except OSError:
        return ImageFont.load_default()


def _both(render, size):
    """Render once per mode so CTkImage can swap with the theme."""
    imgs = {}
    for mode in ("Light", "Dark"):
        pal = {k: (v[0] if mode == "Light" else v[1]) for k, v in T.PALETTE.items()}
        imgs[mode] = render(pal).resize(size, Image.LANCZOS)
    return ctk.CTkImage(light_image=imgs["Light"], dark_image=imgs["Dark"], size=size)


def ring(present: int, late: int, total: int, size=176, width=16) -> ctk.CTkImage:
    """Donut showing present (green) + late (marigold) out of total."""
    def render(pal):
        s = size * SS
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        w = width * SS
        box = (w // 2, w // 2, s - w // 2, s - w // 2)
        d.arc(box, 0, 360, fill=pal["surface_alt"], width=w)
        if total and (present or late):
            r = (s - w) / 2

            def cap(ang, color):
                cx = s / 2 + r * math.cos(math.radians(ang))
                cy = s / 2 + r * math.sin(math.radians(ang))
                d.ellipse((cx - w / 2, cy - w / 2, cx + w / 2, cy + w / 2), fill=color)
            start = -90
            segs = [(v, c) for v, c in ((present, pal["present"]), (late, pal["late"])) if v]
            cap(start, segs[0][1])
            for value, color in segs:
                sweep = 360 * value / total
                d.arc(box, start, start + sweep, fill=color, width=w)
                start += sweep
            if start - (-90) < 359.5:
                cap(start, segs[-1][1])
        return img
    return _both(render, (size, size))


def week_bars(series, width=520, height=200) -> ctk.CTkImage:
    """Rounded bars for the last 7 days; today highlighted."""
    def render(pal):
        W, H = width * SS, height * SS
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if not series:
            return img
        maxv = max(max(v for _, v in series), 1)
        pad_b, pad_t = 30 * SS, 22 * SS
        n = len(series)
        slot = W / n
        bw = min(38 * SS, slot * 0.5)
        lab = _font(11 * SS)
        val = _font(11 * SS, bold=True)
        base = H - pad_b
        d.line((0, base, W, base), fill=pal["border"], width=SS)
        for i, (day, v) in enumerate(series):
            cx = slot * i + slot / 2
            today = i == n - 1
            bh = (base - pad_t) * v / maxv
            color = pal["primary"] if today else pal["primary_soft"]
            if v:
                d.rounded_rectangle((cx - bw / 2, base - bh, cx + bw / 2, base), radius=8 * SS,
                                    fill=color)
                t = str(v)
                tw = d.textlength(t, font=val)
                d.text((cx - tw / 2, base - bh - 18 * SS), t, font=val,
                       fill=pal["text"] if today else pal["muted"])
            name = "Today" if today else dt.date.fromisoformat(day).strftime("%a")
            tw = d.textlength(name, font=lab)
            d.text((cx - tw / 2, base + 9 * SS), name, font=lab,
                   fill=pal["text"] if today else pal["faint"])
        return img
    return _both(render, (width, height))
