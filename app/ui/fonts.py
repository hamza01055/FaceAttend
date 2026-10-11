"""Load the bundled Plus Jakarta Sans font so the app looks the same on every PC.

Windows: fonts are registered privately for this process (nothing is installed).
Linux/macOS: fonts are copied to the user font folder on first run.
Falls back to the system UI font if anything fails.
"""
import glob
import os
import shutil
import subprocess
import sys

from .. import config

FONT_DIR = os.path.join(config.RESOURCE_DIR, "assets", "fonts")
FAMILY = "Plus Jakarta Sans"
_loaded = False


def _register_windows(paths) -> bool:
    try:
        import ctypes
        FR_PRIVATE = 0x10
        ok = 0
        for p in paths:
            ok += ctypes.windll.gdi32.AddFontResourceExW(p, FR_PRIVATE, 0)
        return ok > 0
    except Exception:  # noqa: BLE001
        return False


def _register_unix(paths) -> bool:
    target = os.path.join(os.path.expanduser("~"), ".local", "share", "fonts", "FaceAttend")
    try:
        os.makedirs(target, exist_ok=True)
        new = False
        for p in paths:
            dst = os.path.join(target, os.path.basename(p))
            if not os.path.exists(dst):
                shutil.copyfile(p, dst)
                new = True
        if new and shutil.which("fc-cache"):
            subprocess.run(["fc-cache", "-f", target], capture_output=True, timeout=30)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def load_fonts() -> None:
    """Call once before creating the Tk root."""
    global _loaded
    if _loaded:
        return
    paths = sorted(glob.glob(os.path.join(FONT_DIR, "*.ttf")))
    if paths:
        (_register_windows if sys.platform.startswith("win") else _register_unix)(paths)
    _loaded = True


def resolve(root) -> dict:
    """Return the family names Tk actually sees for each weight."""
    from tkinter import font as tkfont
    fams = set(tkfont.families(root))
    fallback = "Segoe UI" if sys.platform.startswith("win") else "DejaVu Sans"
    if FAMILY not in fams:
        return {"regular": fallback, "medium": fallback, "semibold": fallback, "bold": fallback,
                "extrabold": fallback, "bundled": False}

    def pick(name):
        return name if name in fams else FAMILY
    return {
        "regular": FAMILY,
        "medium": pick(f"{FAMILY} Medium"),
        "semibold": pick(f"{FAMILY} SemiBold"),
        "bold": FAMILY,              # used with weight="bold"
        "extrabold": pick(f"{FAMILY} ExtraBold"),
        "bundled": True,
    }
