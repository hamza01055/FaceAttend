"""Round avatars made from each student's enrolled face photo (or initials)."""
import glob
import hashlib
import os

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk

from . import fonts
from . import theme as T

# muted, distinct hues for initials (derived from the palette's green family)
_HUES = ["#0F7B5F", "#2C6E8F", "#7A5AA6", "#A0613A", "#3E7D3A", "#9C4A6B", "#4F6B8A", "#8A7A2C"]
_cache = {}


def _initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    return ((parts[0][0] if parts else "?") + (parts[-1][0] if len(parts) > 1 else "")).upper()


def _font(px: int):
    for path in glob.glob(os.path.join(fonts.FONT_DIR, "PlusJakartaSans-Bold.ttf")):
        try:
            return ImageFont.truetype(path, px)
        except OSError:
            pass
    return ImageFont.load_default()


def _circle(img: Image.Image, size: int, ring: str = None) -> Image.Image:
    scale = 3   # draw big, shrink: smooth anti-aliased edge
    big = size * scale
    img = img.convert("RGBA").resize((big, big), Image.LANCZOS)
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
    out = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    if ring:
        ImageDraw.Draw(out).ellipse((2, 2, big - 3, big - 3), outline=ring, width=3 * scale)
    return out.resize((size, size), Image.LANCZOS)


def _face_file(engine, student_id):
    folder = engine.student_dir(student_id)
    files = sorted(glob.glob(os.path.join(folder, "*.png")))
    return files[len(files) // 2] if files else None   # a middle frame: usually frontal


def pil_avatar(engine, student: dict, size: int, ring: str = None) -> Image.Image:
    path = _face_file(engine, student["id"]) if engine else None
    stamp = os.path.getmtime(path) if path else 0
    key = (student["id"], student["name"], size, ring, path, stamp)
    if key in _cache:
        return _cache[key]
    if path:
        img = Image.open(path)
        # aligned crops are 112x112 with the face centred; trim a little border
        w, h = img.size
        img = img.crop((int(w * 0.08), int(h * 0.04), int(w * 0.92), int(h * 0.88)))
        out = _circle(img, size, ring)
    else:
        hue = _HUES[int(hashlib.md5(student["name"].encode()).hexdigest(), 16) % len(_HUES)]
        big = size * 3
        base = Image.new("RGBA", (big, big), hue)
        d = ImageDraw.Draw(base)
        text = _initials(student["name"])
        fnt = _font(int(big * 0.38))
        box = d.textbbox((0, 0), text, font=fnt)
        d.text(((big - (box[2] - box[0])) / 2 - box[0], (big - (box[3] - box[1])) / 2 - box[1]),
               text, fill="white", font=fnt)
        out = _circle(base, size, ring)
    _cache[key] = out
    return out


def ctk_avatar(engine, student: dict, size: int = 40, ring: str = None) -> ctk.CTkImage:
    img = pil_avatar(engine, student, size, ring)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


def tk_avatar(engine, student: dict, size: int = 30) -> ImageTk.PhotoImage:
    """For ttk.Treeview rows (needs a classic PhotoImage). Keep a reference!"""
    img = pil_avatar(engine, student, size)
    bg = Image.new("RGBA", img.size, T.c("surface"))
    bg.alpha_composite(img)
    return ImageTk.PhotoImage(bg)


def forget(student_id=None) -> None:
    """Drop cached avatars (after a new face capture)."""
    for k in list(_cache):
        if student_id is None or k[0] == student_id:
            del _cache[k]
