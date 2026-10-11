# FaceAttend: Audit Report (v1.0 → v1.1)

**Date:** 12 October 2026
**Scope:** full code review of every module, a computer-vision model check on real faces, and an end-to-end test of every feature through the actual user interface.

## Summary

| Area | v1.0 result | v1.1 result |
|---|---|---|
| Face recognition model | ❌ **Accepted 100% of strangers** as enrolled students | ✅ 100% correct, 0% strangers accepted |
| Code review | 13 bugs and weaknesses found | ✅ All fixed |
| Unit tests | 11 passing (but blind to the model flaw) | ✅ 17 passing, including stranger rejection |
| Feature test through the UI | not available | ✅ **66 / 66 checks passed** |

The most important finding: **the original model did not work properly.** It ran without errors and recognised enrolled students, but it could not tell an unknown person apart from an enrolled one. In real use it would have marked strangers or absent students as present. It has been replaced.

---

## 1. Computer-vision model check

### Method
- **Data:** 25 real labelled photos of 9 different people (from the open-source DeepFace project's test set). They span different years, lighting, angles and expressions, which is harder than a classroom.
- **Identification test:** each photo is treated as a "student at the camera" and compared against everyone else's photos (leave-one-out).
- **Stranger test:** the person's own photos are removed from the enrolled set, so they are a stranger. The model must refuse to match them to anyone.
- **Score separation:** similarity or distance is measured for every same-person pair (38) and different-person pair (262).

### v1.0: Haar cascade + LBPH (rejected)
| Threshold (LBPH distance) | Correct person accepted | Stranger wrongly accepted |
|---|---|---|
| 50 | 27% | 0% |
| 60 | 82% | 55% |
| **70 (default)** | 100% | **100%** ❌ |

Same-person distances (39–63) and stranger distances (50–67) **overlapped**, so no threshold works: either real students are missed or strangers are accepted. The earlier unit test missed this because it used a single real face and random noise as the "other person".

### v1.1: YuNet detector + ArcFace embeddings (adopted)
| Threshold (similarity) | Correct person accepted | Stranger wrongly accepted |
|---|---|---|
| 0.35 | 100% | 0% |
| **0.40 (default)** | **100%** | **0%** |
| 0.45 | 97.4% | 0% |

- Same-person similarity: 0.43 – 0.97 (mean 0.70). Different-person similarity: at most 0.20 (mean 0.02). There is a **clear gap**, so the threshold sits safely between the two groups.
- Leave-one-out identification: **25/25 correct**. Stranger test: **25/25 rejected**.
- Detection: 64/64 photos. Real faces score 0.93 or higher; a cat photo scored 0.75, so the detector cutoff was set to 0.80.
- Speed: about 50–65 ms per frame on CPU, around 15 frames per second.
- No new library is needed. Both models are small ONNX files (14 MB total) run by OpenCV, and they are bundled in `assets/models/`.

**Caveat:** this is a small test set. Nida should rerun `tests/evaluate_model.py` on photos of her own classmates (folder per person) and report those numbers in the thesis.

---

## 2. Code review findings (all fixed)

| # | Severity | Problem | Fix |
|---|---|---|---|
| 1 | 🔴 Critical | LBPH model accepted strangers (see §1) | New YuNet + ArcFace engine; threshold plus runner-up margin |
| 2 | 🟠 High | Two "retrain" jobs could run together and corrupt the model file | Training lock, plus an atomic save (write to a temp file, then rename) |
| 3 | 🟠 High | The same student could be credited to two faces in one frame | Each student is matched to at most one face per frame |
| 4 | 🟠 High | No check for enrolling the same face under two names | Warns when captured face already matches another student |
| 5 | 🟡 Medium | Camera left running past midnight kept yesterday's list, so students weren't marked for the new day | Day change detected and the list refreshed |
| 6 | 🟡 Medium | Student report counted absences from before a student was registered, and for other classes' sessions | Working days counted per class, from the registration date |
| 7 | 🟡 Medium | Daily sheet showed newly registered students as absent on earlier dates | Students who weren't registered yet are hidden |
| 8 | 🟡 Medium | Manually marking a past date judged "Late" using today's clock; future dates were allowed | Past corrections are saved as Present; future dates are blocked |
| 9 | 🟡 Medium | Closing the face-capture window during training crashed the app | Window can't be closed while saving |
| 10 | 🟡 Medium | A background job finishing after logout raised a Tk error | Job checks that its screen still exists |
| 11 | 🟡 Medium | Unlimited password guessing | 30-second lockout after 5 failures |
| 12 | 🟢 Low | Camera could be released while a frame was still being read | Reader thread finishes before the device is freed |
| 13 | 🟢 Low | Installing under `C:\Program Files` would fail (folder not writable) | Falls back to `%LOCALAPPDATA%\FaceAttend` |

Also added: "Come closer" guidance for small faces, a clear message when there's nothing to export, and a check that a deleted student can't be marked.

**Checked and fine:** all SQL uses parameters (no SQL injection); passwords are salted PBKDF2-SHA256 hashes; role checks hide or disable admin actions for teachers; deleting a student removes their attendance (cascade), face samples and model entries; CSV export is UTF-8 with a BOM, so Excel shows non-English characters correctly.

---

## 3. Feature test (66 / 66 passed)

`tests/gui_feature_test.py` opens the real app and uses every screen. Videos of test photos stand in for the webcam, and each result is checked in the database and on disk. The full list is in `docs/feature_test_results.csv`.

| Feature | Checks |
|---|---|
| Login & security | wrong password rejected · lockout after 5 tries · admin login · default-password warning · logout |
| Roles | admin sees 6 screens · teacher sees 4 · teacher can't add/edit/delete/capture students or remove marks |
| Students | add · duplicate roll no rejected · edit · search · class filter · delete removes samples and model entry |
| Face capture | webcam enrolment saves samples · model updates · duplicate-face warning · photo import (rejects photos with no face) |
| Take attendance | **stranger NOT marked** · enrolled student marked with date/time/score · marked once only · class filter respected · second student not confused with first · manual mark · empty camera handled · deleted student no longer marked |
| Records | daily sheet · date navigation · invalid date rejected · remove/add mark · future date blocked · student report % · CSV export (both) · invalid range rejected |
| Dashboard | totals · today's check-ins |
| Users | add teacher · duplicate rejected · reset password · can't delete self · delete user |
| Settings | invalid time rejected · save · threshold applied · database backup opens |
| Account | change password (wrong current password rejected) |
| Persistence | model reloads after restart |

**Not testable here:** a physical webcam and running on Windows. The camera code uses the standard Windows (DirectShow) path with a fallback. Please do one real run on the target laptop before the demo.

---

## 4. Remaining limitations (for the thesis "Limitations" section)
1. **No liveness detection:** a clear photo or phone screen of a student could mark them. Mitigation: a teacher supervises the camera. Future work: blink or head-movement check, or an anti-spoofing model.
2. Designed for one student at a time about 0.5–1.5 m from the camera, not whole-class recognition from a distance.
3. Very poor lighting or strong backlight lowers detection. Front lighting is recommended.
4. The ArcFace weights (InsightFace) are licensed for non-commercial research use. That is fine for this FYP, but a commercial product would need another model.
