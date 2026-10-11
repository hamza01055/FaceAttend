"""Desktop-Based Attendance System using Face Recognition — entry point.

Run:  python main.py
"""
import sys
import traceback


def main() -> int:
    try:
        from app import config
        from app.database import Database
        from app.face_engine import FaceEngine
    except ImportError as exc:
        _fatal("Missing library", f"{exc}\n\nInstall the requirements first:\n"
               "    pip install -r requirements.txt")
        return 1

    config.ensure_dirs()
    try:
        db = Database(config.DB_PATH)
        engine = FaceEngine()
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        _fatal("Startup error", str(exc))
        return 1

    from app.ui.main_window import App
    App(db, engine).mainloop()
    return 0


def _fatal(title: str, message: str) -> None:
    print(f"{title}: {message}", file=sys.stderr)
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    sys.exit(main())
