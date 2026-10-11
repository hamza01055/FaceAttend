"""Threaded webcam reader so the GUI never blocks on cv2.VideoCapture.read()."""
import os
import threading
import time
from typing import Optional, Union

import cv2


class CameraError(RuntimeError):
    pass


class Camera:
    """Continuously grabs frames in a background thread.

    `source` is a webcam index (0, 1, …) or a path to a video file (handy for
    demos without a webcam; the video loops).
    """

    def __init__(self, source: Union[int, str] = 0, width: int = 640, height: int = 480):
        self.source = source
        self.width, self.height = width, height
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._is_file = isinstance(source, str) and not str(source).isdigit()

    def open(self) -> "Camera":
        src = self.source
        if not self._is_file:
            idx = int(src)
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(idx)
            if not cap.isOpened() and os.name == "nt":
                cap = cv2.VideoCapture(idx)  # fall back to default backend
        else:
            cap = cv2.VideoCapture(str(src))
        if not cap.isOpened():
            raise CameraError(
                f"Could not open camera {src}.\n\n"
                "• Check that a webcam is connected and not used by another app.\n"
                "• Try a different camera number in Settings.")
        if not self._is_file:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        ok, frame = cap.read()
        if not ok or frame is None:
            cap.release()
            raise CameraError(f"Camera {src} opened but returned no image.")
        self._cap = cap
        self._frame = frame
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _loop(self) -> None:
        fps = self._cap.get(cv2.CAP_PROP_FPS) if self._is_file else 0
        delay = 1.0 / fps if fps and fps > 0 else 0.0
        cap = self._cap
        while self._running and cap is not None:
            ok, frame = cap.read()
            if not ok:
                if self._is_file:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                time.sleep(0.05)
                continue
            if not self._is_file:
                frame = cv2.flip(frame, 1)  # mirror view feels natural
            with self._lock:
                self._frame = frame
            if delay:
                time.sleep(delay)
        if cap is not None and self._cap is None:
            cap.release()  # release() timed out waiting for us; free the device here

    def read(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    @property
    def is_open(self) -> bool:
        return self._running

    def release(self) -> None:
        self._running = False
        thread, self._thread = self._thread, None
        if thread is not None:
            # wait for the reader to leave cap.read() before releasing the device
            thread.join(timeout=3.0)
        if self._cap is not None and (thread is None or not thread.is_alive()):
            self._cap.release()
        self._cap = None
        with self._lock:
            self._frame = None
