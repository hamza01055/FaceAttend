"""Application-wide paths and default settings."""
import os
import sys

APP_NAME = "FaceAttend"
APP_TITLE = "Desktop Attendance System using Face Recognition"
APP_VERSION = "1.2.0"


def _base_dir() -> str:
    """Folder next to main.py (or next to the .exe when frozen)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resource_dir() -> str:
    """Folder that holds bundled read-only assets."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _writable(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_test")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _data_dir() -> str:
    if os.environ.get("FACEATTEND_DATA_DIR"):
        return os.environ["FACEATTEND_DATA_DIR"]
    local = os.path.join(_base_dir(), "data")
    if _writable(local):
        return local
    # e.g. installed under C:\Program Files -> use the user's AppData instead
    appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, APP_NAME, "data")


BASE_DIR = _base_dir()
RESOURCE_DIR = _resource_dir()

DATA_DIR = _data_dir()
DB_PATH = os.path.join(DATA_DIR, "attendance.db")
FACES_DIR = os.path.join(DATA_DIR, "face_samples")      # aligned 112x112 crops per student
MODEL_DIR = os.path.join(DATA_DIR, "model")
MODEL_PATH = os.path.join(MODEL_DIR, "embeddings.npz")  # enrolled face embeddings
EXPORT_DIR = os.path.join(DATA_DIR, "exports")

MODELS_DIR = os.path.join(RESOURCE_DIR, "assets", "models")
DETECTOR_MODEL = os.path.join(MODELS_DIR, "face_detection_yunet_640.onnx")
RECOGNIZER_MODEL = os.path.join(MODELS_DIR, "face_recognition_arcface_mbf.onnx")

# Default first-run administrator account.
DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"

# Values stored in the settings table (all kept as strings).
DEFAULT_SETTINGS = {
    "camera_index": "0",            # webcam number (0 = built-in)
    "match_threshold": "0.40",      # cosine similarity 0..1; higher = stricter
    "samples_per_student": "20",    # face images captured on enrolment
    "confirm_frames": "3",          # consecutive matches before marking
    "late_after": "",               # HH:MM; empty disables "Late" status
    "institution_name": "Islamia University of Bahawalpur",
    "appearance": "Light",          # Light | Dark | System
}

THRESHOLD_MIN, THRESHOLD_MAX = 0.25, 0.70


def ensure_dirs() -> None:
    for d in (DATA_DIR, FACES_DIR, MODEL_DIR, EXPORT_DIR):
        os.makedirs(d, exist_ok=True)
