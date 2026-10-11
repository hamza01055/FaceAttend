"""Feather line icons, tinted to theme colours (MIT licence, see assets/icons)."""
import os
from functools import lru_cache

import customtkinter as ctk
from PIL import Image

from .. import config
from . import theme as T

ICON_DIR = os.path.join(config.RESOURCE_DIR, "assets", "icons")


@lru_cache(maxsize=None)
def _mask(name: str) -> Image.Image:
    path = os.path.join(ICON_DIR, f"{name}.png")
    img = Image.open(path).convert("RGBA")
    return img.getchannel("A")


@lru_cache(maxsize=None)
def _tinted(name: str, hex_color: str) -> Image.Image:
    alpha = _mask(name)
    solid = Image.new("RGBA", alpha.size, hex_color)
    solid.putalpha(alpha)
    return solid


def icon(name: str, size: int = 18, color: str = "text") -> ctk.CTkImage:
    """CTkImage that follows light/dark mode. `color` is a theme token or hex."""
    if color.startswith("#"):
        light = dark = color
    else:
        light, dark = T.PALETTE[color]
    return _cached(name, size, light, dark)


@lru_cache(maxsize=None)
def _cached(name, size, light, dark):
    return ctk.CTkImage(light_image=_tinted(name, light), dark_image=_tinted(name, dark),
                        size=(size, size))
