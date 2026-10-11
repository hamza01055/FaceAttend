"""Measure face-recognition accuracy on your own labelled photos.

Usage:
    python tests/evaluate_model.py <dataset_folder> [--threshold 0.40]

<dataset_folder> may be either:
  * one sub-folder per person:   dataset/Ali/1.jpg, dataset/Ali/2.jpg, dataset/Sara/…
  * a flat folder with master.csv listing pairs (file_x,file_y,Decision=Yes/No)

Reports:
  - detection rate
  - same-person / different-person similarity ranges
  - accept / false-accept rates at several thresholds
  - leave-one-out identification accuracy (like taking attendance)
  - stranger test: each person removed from the gallery must be rejected
"""
import argparse
import collections
import csv
import glob
import os
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.face_engine import FaceEngine, imread_unicode  # noqa: E402

IMG_EXT = (".jpg", ".jpeg", ".png", ".bmp")


def load_labels(folder):
    master = os.path.join(folder, "master.csv")
    if os.path.exists(master):
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for row in csv.DictReader(open(master, encoding="utf-8")):
            a, b = find(row["file_x"]), find(row["file_y"])
            if row["Decision"].strip().lower() == "yes":
                parent[a] = b
        return {os.path.join(folder, x): find(x) for x in parent}
    labels = {}
    for person in sorted(os.listdir(folder)):
        pdir = os.path.join(folder, person)
        if os.path.isdir(pdir):
            for p in glob.glob(os.path.join(pdir, "*")):
                if p.lower().endswith(IMG_EXT):
                    labels[p] = person
    return labels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--threshold", type=float, default=0.40)
    args = ap.parse_args()

    labels = load_labels(args.dataset)
    people = collections.Counter(labels.values())
    print(f"Images: {len(labels)}   People: {len(people)}   "
          f"Images per person: {sorted(people.values(), reverse=True)}")

    tmp = tempfile.mkdtemp()
    engine = FaceEngine(model_path=os.path.join(tmp, "m.npz"), faces_dir=os.path.join(tmp, "f"))
    emb, missed = {}, []
    t0 = time.time()
    for path in labels:
        img = imread_unicode(path)
        face = engine.largest(engine.detect(img)) if img is not None else None
        if face is None:
            missed.append(os.path.basename(path))
            continue
        emb[path] = engine.embed(engine.align(img, face))
    per_img = (time.time() - t0) / max(len(labels), 1) * 1000
    print(f"\nDetection: {len(emb)}/{len(labels)} images ({len(emb) / len(labels):.1%})"
          + (f"   missed: {missed}" if missed else ""))
    print(f"Average time per image (detect + align + embed): {per_img:.0f} ms")

    keys = list(emb)
    same, diff = [], []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            s = float(emb[keys[i]] @ emb[keys[j]])
            (same if labels[keys[i]] == labels[keys[j]] else diff).append(s)
    same, diff = np.array(same), np.array(diff)
    if len(same) and len(diff):
        print(f"\nSame-person similarity:      mean {same.mean():.2f}  lowest  {same.min():.2f}"
              f"  ({len(same)} pairs)")
        print(f"Different-person similarity: mean {diff.mean():.2f}  highest {diff.max():.2f}"
              f"  ({len(diff)} pairs)")
        print("\nThreshold | same person accepted | different person wrongly accepted")
        for th in (0.30, 0.35, 0.40, 0.45, 0.50, 0.55):
            mark = "  <- current" if abs(th - args.threshold) < 1e-9 else ""
            print(f"   {th:.2f}   |       {np.mean(same >= th):6.1%}         |"
                  f"        {np.mean(diff >= th):6.1%}{mark}")

    # attendance-style test: each image vs. everyone else's enrolled images
    correct = total = false_accept = rejected_unknown = strangers = 0
    for k in keys:
        best = {}
        for o in keys:
            if o != k:
                best[labels[o]] = max(best.get(labels[o], -1.0), float(emb[k] @ emb[o]))
        ranked = sorted(best.items(), key=lambda kv: -kv[1])
        if any(labels[o] == labels[k] for o in keys if o != k):
            total += 1
            top, sim = ranked[0]
            runner = ranked[1][1] if len(ranked) > 1 else -1
            accepted = sim >= args.threshold and sim - runner >= 0.05
            correct += accepted and top == labels[k]
        others = [kv for kv in ranked if kv[0] != labels[k]]
        if others:
            strangers += 1
            if others[0][1] >= args.threshold:
                false_accept += 1
            else:
                rejected_unknown += 1
    print(f"\nAttendance test (threshold {args.threshold:.2f}):")
    if total:
        print(f"  Enrolled person correctly marked: {correct}/{total} = {correct / total:.1%}")
    print(f"  Stranger correctly rejected:      {rejected_unknown}/{strangers} = "
          f"{rejected_unknown / max(strangers, 1):.1%}")
    print(f"  Stranger wrongly marked:          {false_accept}/{strangers} = "
          f"{false_accept / max(strangers, 1):.1%}")


if __name__ == "__main__":
    main()
