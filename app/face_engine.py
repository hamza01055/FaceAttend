"""Face detection (YuNet) and recognition (ArcFace embeddings) with OpenCV DNN.

Pipeline (matches the SRS system flow):
    capture image -> detect face + 5 landmarks (YuNet)
    -> align & crop to 112x112 using the eye/nose/mouth points
    -> extract a 512-number face embedding (ArcFace MobileFaceNet)
    -> compare with every enrolled student's embeddings (cosine similarity)
    -> accept the best student only if similarity >= threshold and it is
       clearly better than the runner-up.

Both networks run on the CPU through cv2.dnn; no internet or GPU needed.

Why not LBPH/Haar? On a test of real photos of different people, LBPH
distances for the same person and for strangers overlapped almost
completely, so strangers were accepted as enrolled students. ArcFace
separates them cleanly (see AUDIT_REPORT.md).
"""
import glob
import os
import shutil
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import cv2
import numpy as np

from . import config

# Standard ArcFace 112x112 positions of: right eye, left eye, nose, mouth R, mouth L
ARCFACE_REF = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
                        [41.5493, 92.3655], [70.7299, 92.2041]], dtype=np.float32)
DET_SIZE = 640          # the bundled YuNet model has a fixed 640x640 input
CROP_SIZE = 112


def imread_unicode(path: str, flags: int = cv2.IMREAD_COLOR):
    """cv2.imread that also works with non-ASCII Windows paths."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, flags)


def imwrite_unicode(path: str, image) -> bool:
    ext = os.path.splitext(path)[1] or ".png"
    ok, buf = cv2.imencode(ext, image)
    if ok:
        buf.tofile(path)
    return ok


@dataclass
class Face:
    box: Tuple[int, int, int, int]      # x, y, w, h in frame pixels
    landmarks: np.ndarray               # (5, 2) float32
    score: float                        # detector confidence 0..1


class FaceEngine:
    def __init__(self, detector_path: str = config.DETECTOR_MODEL,
                 recognizer_path: str = config.RECOGNIZER_MODEL,
                 model_path: str = config.MODEL_PATH,
                 faces_dir: str = config.FACES_DIR,
                 det_threshold: float = 0.8):
        for p in (detector_path, recognizer_path):
            if not os.path.exists(p):
                raise RuntimeError(f"Model file missing:\n{p}\n\nRe-extract the project zip.")
        try:
            self._detector = cv2.FaceDetectorYN.create(
                detector_path, "", (DET_SIZE, DET_SIZE), det_threshold, 0.3, 5000)
            self._recognizer = cv2.dnn.readNetFromONNX(recognizer_path)
        except (cv2.error, AttributeError) as exc:
            raise RuntimeError(
                "Could not load the face models. Install OpenCV 4.10:\n"
                "    pip install opencv-python==4.10.0.84\n\n" + str(exc)) from exc
        self.model_path = model_path
        self.faces_dir = faces_dir
        self._det_lock = threading.Lock()       # cv2.dnn nets are not thread-safe
        self._rec_lock = threading.Lock()
        self._train_lock = threading.Lock()     # one training run at a time
        self._gallery_lock = threading.Lock()
        self._labels = np.zeros((0,), np.int32)
        self._embeddings = np.zeros((0, 512), np.float32)
        os.makedirs(faces_dir, exist_ok=True)
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        self.load_model()

    # ------------------------------------------------------------ detection
    def detect(self, frame_bgr) -> List[Face]:
        """Find faces. Frames of any size are letter-boxed to 640x640."""
        if frame_bgr is None or frame_bgr.size == 0:
            return []
        if frame_bgr.ndim == 2:
            frame_bgr = cv2.cvtColor(frame_bgr, cv2.COLOR_GRAY2BGR)
        h, w = frame_bgr.shape[:2]
        s = DET_SIZE / max(h, w)
        nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
        canvas = np.zeros((DET_SIZE, DET_SIZE, 3), np.uint8)
        canvas[:nh, :nw] = cv2.resize(frame_bgr, (nw, nh),
                                      interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        with self._det_lock:
            _, out = self._detector.detect(canvas)
        if out is None:
            return []
        faces = []
        for row in out:
            x, y, bw, bh = (row[:4] / s).tolist()
            x0, y0 = max(int(x), 0), max(int(y), 0)
            x1, y1 = min(int(x + bw), w), min(int(y + bh), h)
            if x1 - x0 < 20 or y1 - y0 < 20:
                continue
            faces.append(Face((x0, y0, x1 - x0, y1 - y0),
                              (row[4:14] / s).reshape(5, 2).astype(np.float32), float(row[14])))
        return faces

    @staticmethod
    def largest(faces: List[Face]) -> Optional[Face]:
        return max(faces, key=lambda f: f.box[2] * f.box[3]) if faces else None

    def align(self, frame_bgr, face: Face) -> np.ndarray:
        """Rotate/scale so eyes, nose and mouth land on fixed positions (112x112)."""
        m, _ = cv2.estimateAffinePartial2D(face.landmarks, ARCFACE_REF, method=cv2.LMEDS)
        if m is None:  # degenerate landmarks: fall back to a plain crop
            x, y, w, h = face.box
            return cv2.resize(frame_bgr[y:y + h, x:x + w], (CROP_SIZE, CROP_SIZE))
        return cv2.warpAffine(frame_bgr, m, (CROP_SIZE, CROP_SIZE), borderValue=0)

    # backwards-compatible name used by the UI
    preprocess = align

    # ---------------------------------------------------------- recognition
    def embed(self, aligned_bgr) -> np.ndarray:
        if aligned_bgr.shape[:2] != (CROP_SIZE, CROP_SIZE):
            aligned_bgr = cv2.resize(aligned_bgr, (CROP_SIZE, CROP_SIZE))
        blob = cv2.dnn.blobFromImage(aligned_bgr, 1.0 / 127.5, (CROP_SIZE, CROP_SIZE),
                                     (127.5, 127.5, 127.5), swapRB=True)
        with self._rec_lock:
            self._recognizer.setInput(blob)
            vec = self._recognizer.forward().reshape(-1).astype(np.float32)
        n = np.linalg.norm(vec)
        return vec / n if n > 0 else vec

    @property
    def is_trained(self) -> bool:
        return len(self._labels) > 0

    @property
    def enrolled_ids(self) -> set:
        return set(int(x) for x in np.unique(self._labels))

    def match(self, aligned_bgr) -> List[Tuple[int, float]]:
        """All enrolled students ranked by best similarity (high = same person)."""
        with self._gallery_lock:
            labels, gallery = self._labels, self._embeddings
        if len(labels) == 0:
            return []
        sims = gallery @ self.embed(aligned_bgr)
        best = {}
        for lab, sim in zip(labels.tolist(), sims.tolist()):
            if sim > best.get(lab, -2.0):
                best[lab] = sim
        return sorted(best.items(), key=lambda kv: -kv[1])

    def recognize(self, aligned_bgr, threshold: float,
                  margin: float = 0.05) -> Tuple[Optional[int], Optional[float]]:
        """Return (student_id, similarity) or (None, best_similarity) if unsure.

        Accepted only when the best match reaches `threshold` AND beats the
        second-best student by `margin` (avoids confusing look-alikes).
        """
        ranked = self.match(aligned_bgr)
        if not ranked:
            return None, None
        sid, sim = ranked[0]
        runner_up = ranked[1][1] if len(ranked) > 1 else -1.0
        if sim < threshold or sim - runner_up < margin:
            return None, sim
        return int(sid), float(sim)

    # ------------------------------------------------------------- training
    def load_model(self) -> bool:
        try:
            data = np.load(self.model_path)
            labels, emb = data["labels"].astype(np.int32), data["embeddings"].astype(np.float32)
            if emb.ndim != 2 or len(labels) != len(emb):
                raise ValueError("corrupt model")
        except (OSError, KeyError, ValueError):
            labels, emb = np.zeros((0,), np.int32), np.zeros((0, 512), np.float32)
        with self._gallery_lock:
            self._labels, self._embeddings = labels, emb
        return len(labels) > 0

    def dataset(self, valid_ids: Optional[set] = None) -> Tuple[List[np.ndarray], List[int]]:
        images, labels = [], []
        for folder in sorted(glob.glob(os.path.join(self.faces_dir, "*"))):
            name = os.path.basename(folder)
            if not (os.path.isdir(folder) and name.isdigit()):
                continue
            if valid_ids is not None and int(name) not in valid_ids:
                continue
            for img_path in sorted(glob.glob(os.path.join(folder, "*.png"))):
                img = imread_unicode(img_path)
                if img is not None and img.shape[:2] == (CROP_SIZE, CROP_SIZE):
                    images.append(img)
                    labels.append(int(name))
        return images, labels

    def train(self, valid_ids: Optional[set] = None,
              progress: Optional[Callable[[str], None]] = None) -> dict:
        """Compute embeddings for every enrolled student and save them."""
        with self._train_lock:
            images, labels = self.dataset(valid_ids)
            if progress:
                progress(f"Computing embeddings for {len(images)} images…")
            if images:
                emb = np.stack([self.embed(im) for im in images]).astype(np.float32)
                lab = np.array(labels, np.int32)
            else:
                emb, lab = np.zeros((0, 512), np.float32), np.zeros((0,), np.int32)
            tmp = self.model_path + ".tmp.npz"
            np.savez(tmp, labels=lab, embeddings=emb)
            os.replace(tmp, self.model_path)       # atomic: never a half-written model
            with self._gallery_lock:
                self._labels, self._embeddings = lab, emb
            return {"students": int(len(set(labels))), "images": int(len(images))}

    # ------------------------------------------------------- sample storage
    def student_dir(self, student_id: int) -> str:
        return os.path.join(self.faces_dir, str(int(student_id)))

    def sample_count(self, student_id: int) -> int:
        return len(glob.glob(os.path.join(self.student_dir(student_id), "*.png")))

    def save_samples(self, student_id: int, faces: List[np.ndarray], replace: bool = True) -> int:
        folder = self.student_dir(student_id)
        with self._train_lock:
            if replace and os.path.isdir(folder):
                shutil.rmtree(folder)
            os.makedirs(folder, exist_ok=True)
            existing = {os.path.basename(p) for p in glob.glob(os.path.join(folder, "*.png"))}
            i = 0
            for face in faces:
                while True:
                    i += 1
                    name = f"{i:03d}.png"
                    if name not in existing:
                        break
                imwrite_unicode(os.path.join(folder, name), face)
        return self.sample_count(student_id)

    def delete_samples(self, student_id: int) -> None:
        with self._train_lock:
            shutil.rmtree(self.student_dir(student_id), ignore_errors=True)

    def faces_from_photo(self, path: str) -> List[np.ndarray]:
        """Detect the largest face in an image file and return it aligned."""
        img = imread_unicode(path)
        if img is None:
            return []
        face = self.largest(self.detect(img))
        return [self.align(img, face)] if face else []
