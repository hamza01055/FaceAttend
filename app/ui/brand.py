"""Logo mark and login artwork, drawn with Pillow (no image files needed).

Motif: the four corner brackets a face scanner draws around a face.
"""
import random

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFilter


SS = 4


def _corners(d, x, y, w, h, L, width, color):
    for (px, py, dx, dy) in ((x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1),
                             (x + w, y + h, -1, -1)):
        d.line((px, py, px + dx * L, py), fill=color, width=width)
        d.line((px, py, px, py + dy * L), fill=color, width=width)
        r = width / 2
        for cx, cy in ((px, py), (px + dx * L, py), (px, py + dy * L)):
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)


def logo(size=36, bg="#0F7B5F", fg="#FFFFFF") -> ctk.CTkImage:
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.28), fill=bg)
    m = s * 0.22
    _corners(d, m, m, s - 2 * m, s - 2 * m, s * 0.17, int(s * 0.075), fg)
    # simple head + shoulders
    cx = s / 2
    hr = s * 0.11
    d.ellipse((cx - hr, s * 0.34 - hr, cx + hr, s * 0.34 + hr), fill=fg)
    d.pieslice((cx - s * 0.19, s * 0.52, cx + s * 0.19, s * 0.86), 180, 360, fill=fg)
    img = img.resize((size, size), Image.LANCZOS)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


def login_art(width, height) -> ctk.CTkImage:
    """Pine panel scattered with scan-corner frames; one frame 'locked' in green."""
    rnd = random.Random(7)
    imgs = {}
    for mode, (bg, line, accent) in {"Light": ("#0F2A22", "#1C4B3D", "#2BB38A"),
                                     "Dark": ("#08130F", "#14332A", "#2BB38A")}.items():
        W, H = width * 2, height * 2
        img = Image.new("RGB", (W, H), bg)
        d = ImageDraw.Draw(img)
        cell = 150
        for gy in range(-1, H // cell + 2):
            for gx in range(-1, W // cell + 2):
                if rnd.random() < 0.55:
                    continue
                size = rnd.choice([54, 70, 90])
                x = gx * cell + (cell - size) / 2 + rnd.randint(-18, 18) + (gy % 2) * cell / 2
                y = gy * cell + (cell - size) / 2 + rnd.randint(-18, 18)
                _corners(d, x, y, size, size * 1.15, size * 0.22, 4, line)
        # the recognised one
        fx, fy, fs = W * 0.56, H * 0.17, 150
        glow = Image.new("RGB", (W, H), (0, 0, 0))
        _corners(ImageDraw.Draw(glow), fx, fy, fs, fs * 1.15, fs * 0.24, 10, accent)
        glow = glow.filter(ImageFilter.GaussianBlur(18))
        img = Image.blend(img, Image.composite(glow, img, glow.convert("L")), 0.5)
        d = ImageDraw.Draw(img)
        _corners(d, fx, fy, fs, fs * 1.15, fs * 0.24, 7, accent)
        imgs[mode] = img.resize((width, height), Image.LANCZOS)
    return ctk.CTkImage(light_image=imgs["Light"], dark_image=imgs["Dark"], size=(width, height))
