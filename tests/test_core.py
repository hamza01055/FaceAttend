"""Unit tests for the database, auth and face-recognition pipeline.

Run:  python -m unittest discover tests -v

Fixtures are public-domain sample photos bundled with scikit-image:
  face_sample.jpg  - "astronaut" (NASA photo)  -> the enrolled student
  face_other.jpg   - "cameraman"               -> a different, unenrolled person
"""
import datetime as dt
import os
import shutil
import sys
import tempfile
import unittest

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import auth, config  # noqa: E402
from app.database import Database, DuplicateError  # noqa: E402
from app.face_engine import FaceEngine  # noqa: E402
from app.reports import export_csv  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
FACE_PHOTO = os.path.join(FIX, "face_sample.jpg")
OTHER_PHOTO = os.path.join(FIX, "face_other.jpg")
THRESHOLD = float(config.DEFAULT_SETTINGS["match_threshold"])


def variations(img):
    """Lighting / rotation variants of one photo (simulates webcam frames)."""
    h, w = img.shape[:2]
    out = []
    for alpha, beta in ((1.0, 0), (0.75, -25), (1.25, 20), (0.9, 35), (1.1, -15)):
        for angle in (-10, -5, 0, 5, 10):
            m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
            v = cv2.warpAffine(img, m, (w, h), borderMode=cv2.BORDER_REFLECT)
            out.append(cv2.convertScaleAbs(v, alpha=alpha, beta=beta))
    return out


class AuthTests(unittest.TestCase):
    def test_hash_and_verify(self):
        h = auth.hash_password("secret")
        self.assertNotIn("secret", h)
        self.assertTrue(auth.verify_password("secret", h))
        self.assertFalse(auth.verify_password("wrong", h))
        self.assertFalse(auth.verify_password("secret", "garbage"))
        self.assertNotEqual(h, auth.hash_password("secret"))  # salted


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = Database(os.path.join(self.tmp, "t.db"))

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _backdate(self, sid, date_s):
        self.db._exec("UPDATE students SET created_at = ? WHERE id = ?", (date_s + "T08:00:00", sid))

    def test_default_admin_and_users(self):
        admin = self.db.authenticate("admin", config.DEFAULT_ADMIN_PASSWORD)
        self.assertEqual(admin["role"], "admin")
        self.assertIsNone(self.db.authenticate("admin", "nope"))
        uid = self.db.add_user("teacher1", "pass1", "Ms Teacher", "teacher")
        self.assertEqual(self.db.authenticate("TEACHER1", "pass1")["id"], uid)
        with self.assertRaises(DuplicateError):
            self.db.add_user("teacher1", "x", "", "teacher")
        with self.assertRaises(ValueError):
            self.db.delete_user(admin["id"])  # last admin
        self.db.set_password(uid, "newpass")
        self.assertIsNotNone(self.db.authenticate("teacher1", "newpass"))
        self.db.delete_user(uid)
        self.assertIsNone(self.db.authenticate("teacher1", "newpass"))

    def test_students_crud(self):
        a = self.db.add_student("BSIT-01", "Ali", "BSIT-7A")
        self.db.add_student("BSIT-02", "Sara", "BSIT-7B")
        with self.assertRaises(DuplicateError):
            self.db.add_student("bsit-01", "Dup", "")
        with self.assertRaises(ValueError):
            self.db.add_student("", "No roll", "")
        self.assertEqual(self.db.list_classes(), ["BSIT-7A", "BSIT-7B"])
        self.assertEqual(len(self.db.list_students(search="sar")), 1)
        self.assertEqual(len(self.db.list_students(class_name="BSIT-7A")), 1)
        self.db.update_student(a, "BSIT-01", "Ali Khan", "BSIT-7A")
        self.assertEqual(self.db.get_student(a)["name"], "Ali Khan")
        self.db.delete_student(a)
        self.assertEqual(self.db.count_students(), 1)

    def test_attendance_once_per_day_late_and_cascade(self):
        a = self.db.add_student("1", "Ali", "A")
        b = self.db.add_student("2", "Sara", "A")
        self._backdate(a, "2026-10-01")
        self._backdate(b, "2026-10-01")
        d1 = dt.datetime(2026, 10, 5, 8, 15)
        created, rec = self.db.mark_attendance(a, when=d1, confidence=0.71)
        self.assertTrue(created)
        self.assertEqual((rec["date"], rec["time"], rec["status"]),
                         ("2026-10-05", "08:15:00", "Present"))
        created, _ = self.db.mark_attendance(a, when=d1 + dt.timedelta(hours=2))
        self.assertFalse(created)  # no duplicate for same day
        sheet = {r["roll_no"]: r["status"] for r in self.db.daily_sheet("2026-10-05")}
        self.assertEqual(sheet, {"1": "Present", "2": "Absent"})

        self.db.set_setting("late_after", "08:30")
        _, rec = self.db.mark_attendance(b, when=dt.datetime(2026, 10, 5, 8, 45))
        self.assertEqual(rec["status"], "Late")
        # explicit status overrides the clock (manual correction of a past day)
        _, rec = self.db.mark_attendance(b, when=dt.datetime(2026, 10, 7, 11, 0), status="Present")
        self.assertEqual(rec["status"], "Present")
        self.db.mark_attendance(a, when=dt.datetime(2026, 10, 6, 8, 0))

        summary = {r["roll_no"]: r for r in self.db.student_summary("2026-10-01", "2026-10-31")}
        self.assertEqual(summary["1"]["working_days"], 3)          # 5th, 6th, 7th
        self.assertEqual((summary["1"]["present"], summary["1"]["absent"]), (2, 1))
        self.assertEqual((summary["2"]["present"], summary["2"]["late"], summary["2"]["absent"]),
                         (1, 1, 1))
        self.assertAlmostEqual(summary["2"]["percentage"], 66.7)

        self.db.delete_student(a)
        self.assertEqual(len(self.db.attendance_on("2026-10-06")), 0)
        with self.assertRaises(ValueError):
            self.db.mark_attendance(a)      # deleted student can't be marked

    def test_new_student_not_absent_before_registration(self):
        old = self.db.add_student("1", "Old", "A")
        self._backdate(old, "2026-09-01")
        for day in (1, 2, 3):
            self.db.mark_attendance(old, when=dt.datetime(2026, 10, day, 8, 0))
        new = self.db.add_student("2", "New", "A")
        self._backdate(new, "2026-10-03")
        self.db.mark_attendance(new, when=dt.datetime(2026, 10, 3, 8, 0))
        s = {r["roll_no"]: r for r in self.db.student_summary("2026-10-01", "2026-10-31")}
        self.assertEqual((s["2"]["working_days"], s["2"]["absent"], s["2"]["percentage"]),
                         (1, 0, 100.0))
        self.assertNotIn("2", [r["roll_no"] for r in self.db.daily_sheet("2026-10-01")])

    def test_classes_have_separate_sessions(self):
        a = self.db.add_student("1", "Ali", "A")
        b = self.db.add_student("2", "Bilal", "B")
        self._backdate(a, "2026-10-01")
        self._backdate(b, "2026-10-01")
        self.db.mark_attendance(a, when=dt.datetime(2026, 10, 2, 8, 0))   # only class A met
        s = {r["roll_no"]: r for r in self.db.student_summary("2026-10-01", "2026-10-31")}
        self.assertEqual(s["2"]["absent"], 0)   # class B had no session that day

    def test_today_stats_and_counts(self):
        a = self.db.add_student("1", "Ali", "A")
        self.db.add_student("2", "Sara", "A")
        self.db.mark_attendance(a)
        s = self.db.today_stats()
        self.assertEqual((s["total"], s["present"], s["absent"], s["rate"]), (2, 1, 1, 50.0))
        days = self.db.counts_by_day(7)
        self.assertEqual(len(days), 7)
        self.assertEqual(days[-1], (dt.date.today().isoformat(), 1))

    def test_settings(self):
        self.assertEqual(self.db.get_int_setting("camera_index", 9), 0)
        self.db.set_setting("camera_index", 2)
        self.assertEqual(self.db.get_int_setting("camera_index", 0), 2)
        self.assertAlmostEqual(self.db.get_float_setting("match_threshold", 0), 0.40)
        self.db.set_setting("match_threshold", "abc")
        self.assertEqual(self.db.get_float_setting("match_threshold", 0.4), 0.4)

    def test_export_csv(self):
        path = os.path.join(self.tmp, "x.csv")
        n = export_csv(path, ["A", "B"], [(1, None), ("ü", 2)])
        self.assertEqual(n, 2)
        with open(path, encoding="utf-8-sig") as fh:
            self.assertEqual(fh.read().splitlines(), ["A,B", "1,", "ü,2"])


class FaceEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.photo = cv2.imread(FACE_PHOTO)
        cls.other = cv2.imread(OTHER_PHOTO)

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.engine = FaceEngine(model_path=os.path.join(self.tmp, "model", "m.npz"),
                                 faces_dir=os.path.join(self.tmp, "faces"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _enrol(self, sid, img):
        faces = []
        for v in variations(img)[::2]:
            f = self.engine.largest(self.engine.detect(v))
            if f:
                faces.append(self.engine.align(v, f))
        self.engine.save_samples(sid, faces)
        return len(faces)

    def test_detects_face_with_landmarks(self):
        faces = self.engine.detect(self.photo)
        self.assertEqual(len(faces), 1)
        self.assertEqual(faces[0].landmarks.shape, (5, 2))
        self.assertEqual(self.engine.align(self.photo, faces[0]).shape, (112, 112, 3))

    def test_no_face_in_blank_or_noise(self):
        self.assertEqual(self.engine.detect(np.full((480, 640, 3), 127, np.uint8)), [])
        noise = np.random.default_rng(0).integers(0, 255, (480, 640, 3), dtype=np.uint8)
        self.assertEqual(self.engine.detect(noise), [])
        self.assertEqual(self.engine.detect(None), [])

    def test_embeddings_separate_people(self):
        a = self.engine.embed(self.engine.align(self.photo, self.engine.detect(self.photo)[0]))
        rot = variations(self.photo)[3]
        a2 = self.engine.embed(self.engine.align(rot, self.engine.detect(rot)[0]))
        b = self.engine.embed(self.engine.align(self.other, self.engine.detect(self.other)[0]))
        self.assertAlmostEqual(float(np.linalg.norm(a)), 1.0, places=4)
        self.assertGreater(float(a @ a2), 0.6)          # same person
        self.assertLess(float(a @ b), 0.25)             # different people

    def test_enrol_recognise_and_reject_stranger(self):
        self.assertFalse(self.engine.is_trained)
        self.assertGreater(self._enrol(7, self.photo), 8)
        stats = self.engine.train(valid_ids={7})
        self.assertEqual(stats["students"], 1)
        self.assertTrue(self.engine.is_trained)

        hits = probes = 0
        for v in variations(self.photo)[1::2]:
            f = self.engine.largest(self.engine.detect(v))
            if f:
                probes += 1
                sid, sim = self.engine.recognize(self.engine.align(v, f), THRESHOLD)
                hits += sid == 7
        self.assertEqual(hits, probes)

        # an unenrolled person must NOT be accepted as student 7
        for v in variations(self.other)[::3]:
            f = self.engine.largest(self.engine.detect(v))
            if f:
                sid, sim = self.engine.recognize(self.engine.align(v, f), THRESHOLD)
                self.assertIsNone(sid, f"stranger accepted with similarity {sim:.2f}")

    def test_two_students_and_persistence(self):
        self._enrol(1, self.photo)
        self._enrol(2, self.other)
        self.engine.train()
        f = self.engine.detect(self.other)[0]
        sid, sim = self.engine.recognize(self.engine.align(self.other, f), THRESHOLD)
        self.assertEqual(sid, 2)

        reloaded = FaceEngine(model_path=self.engine.model_path, faces_dir=self.engine.faces_dir)
        self.assertEqual(reloaded.enrolled_ids, {1, 2})

        # deleted students drop out of the model (valid_ids filter)
        self.assertEqual(self.engine.train(valid_ids={1})["students"], 1)
        sid, _ = self.engine.recognize(self.engine.align(self.other, f), THRESHOLD)
        self.assertIsNone(sid)

        self.engine.delete_samples(1)
        self.engine.delete_samples(2)
        self.assertEqual(self.engine.train()["students"], 0)
        self.assertFalse(self.engine.is_trained)

    def test_save_samples_append_does_not_overwrite(self):
        crop = np.zeros((112, 112, 3), np.uint8)
        self.engine.save_samples(5, [crop, crop])
        self.engine.save_samples(5, [crop], replace=False)
        self.assertEqual(self.engine.sample_count(5), 3)
        self.engine.save_samples(5, [crop], replace=True)
        self.assertEqual(self.engine.sample_count(5), 1)

    def test_corrupt_model_file_is_ignored(self):
        with open(self.engine.model_path, "wb") as fh:
            fh.write(b"not a model")
        self.assertFalse(self.engine.load_model())

    def test_import_from_photo(self):
        self.assertEqual(len(self.engine.faces_from_photo(FACE_PHOTO)), 1)
        self.assertEqual(self.engine.faces_from_photo(os.path.join(self.tmp, "missing.jpg")), [])


if __name__ == "__main__":
    unittest.main()
