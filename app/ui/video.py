"""Drawing on camera frames and showing them in the UI."""
import tkinter as tk

import cv2
import customtkinter as ctk
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk

from . import fonts
from . import theme as T


def _bgr(hex_color):
    h = hex_color.lstrip("#")
    return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))


# status colours from the palette (light values read well on video)
GREEN = _bgr("#2BB38A")
AMBER = _bgr("#F0B53D")
RED = _bgr("#F0768A")
BLUE = _bgr("#7EA6F2")
WHITE = (255, 255, 255)
_font_cache = {}


def _font(px):
    if px not in _font_cache:
        try:
            _font_cache[px] = ImageFont.truetype(f"{fonts.FONT_DIR}/PlusJakartaSans-Bold.ttf", px)
        except OSError:
            _font_cache[px] = ImageFont.load_default()
    return _font_cache[px]


def draw_box(frame, box, label: str, color) -> None:
    """Face-scan corner marks + a rounded name tag (the app's visual motif)."""
    x, y, w, h = box
    L = max(12, int(min(w, h) * 0.22))
    t = 3
    for (px, py, dx, dy) in ((x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
        cv2.line(frame, (px, py), (px + dx * L, py), color, t, cv2.LINE_AA)
        cv2.line(frame, (px, py), (px, py + dy * L), color, t, cv2.LINE_AA)
    if not label:
        return
    # text with Pillow so it uses the app font (OpenCV fonts look dated)
    fnt = _font(15)
    tmp = Image.new("RGB", (1, 1))
    tw = int(ImageDraw.Draw(tmp).textlength(label, font=fnt))
    pad, th = 10, 26
    bx0 = max(0, min(x + w // 2 - (tw + 2 * pad) // 2, frame.shape[1] - tw - 2 * pad))
    by0 = max(0, y - th - 8)
    roi = frame[by0:by0 + th, bx0:bx0 + tw + 2 * pad]
    if roi.size == 0:
        return
    tag = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(tag)
    rgb = (color[2], color[1], color[0])
    d.rounded_rectangle((0, 0, tag.width - 1, tag.height - 1), radius=th // 2, fill=rgb)
    d.text((pad, 4), label, font=fnt, fill=(15, 42, 34))
    frame[by0:by0 + th, bx0:bx0 + tw + 2 * pad] = cv2.cvtColor(
        np.array(tag), cv2.COLOR_RGB2BGR)


def make_view(parent, width: int, height: int, text: str = ""):
    """Rounded dark panel (CTkFrame) holding a Tk label for fast frame updates."""
    outer = ctk.CTkFrame(parent, width=width + 12, height=height + 12, corner_radius=T.R_HERO,
                         fg_color=T.PALETTE["video_bg"])
    outer.pack_propagate(False)
    label = tk.Label(outer, bg=T.c("video_bg"), fg="#9DB5AB", text=text,
                     font=T.tkfont(11), justify="center", bd=0, highlightthickness=0)
    label.pack(fill="both", expand=True, padx=6, pady=6)
    T.on_mode_change(lambda: label.configure(bg=T.c("video_bg")))
    return outer, label


def to_photo(frame_bgr, max_w: int, max_h: int) -> ImageTk.PhotoImage:
    h, w = frame_bgr.shape[:2]
    scale = min(max_w / w, max_h / h)
    if abs(scale - 1.0) > 0.01:
        frame_bgr = cv2.resize(frame_bgr, (int(w * scale), int(h * scale)),
                               interpolation=cv2.INTER_AREA)
    return ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)))
