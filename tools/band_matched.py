#!/usr/bin/env python3
"""Band comparison at MATCHED resolution - the photograph's native 0.15096 mm/px.

Comparing a 1305 px-wide photograph against a 460 px-tall resample of a
synthetic render measures the resampler as much as the geometry: the band is
0.9 mm per row of holes, and a 2x downsample aliases it badly enough that whole
hole rows vanish. Both sides are therefore put on the photograph's own pixel
grid before anything is measured.
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from compare_render import otsu, largest_blob_fraction, REF, OUT  # noqa: E402
from verify_spec import load  # noqa: E402

W_MM, H_MM = 197.0, 95.0


def runs(mask, axis):
    out = []
    arr = mask if axis == 1 else mask.T
    for line in arr:
        d = np.diff(np.concatenate(([0], line.view(np.int8), [0])))
        s_, e_ = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
        out.extend((e_ - s_).tolist())
    return np.array(out) if out else np.array([0])


def analyse(g, sx, label, x_mm=98.5, half=20.0, lo=87.0, hi=95.0):
    h, w = g.shape
    a = int(round(lo / sx))
    b = min(h, int(round(hi / sx)))
    c = int(round(x_mm / sx))
    p = max(0, c - int(round(half / sx)))
    q = min(w, c + int(round(half / sx)))
    blk = g[a:b, p:q]
    t, eta = otsu(blk)
    m = blk < t
    print("\n%s  %d x %d px at %.5f mm/px  (%.2f..%.2f mm)"
          % (label, blk.shape[1], blk.shape[0], sx, lo, hi))
    print("   otsu %.3f  eta %.2f  open %5.1f%%  largest blob %5.1f%%"
          % (t, eta, m.mean() * 100, largest_blob_fraction(m) * 100))
    share = m.mean(axis=1)
    print("   dark share per row (every row):")
    for i, v in enumerate(share):
        print("     %6.2f mm  %5.1f  %s"
              % (lo + i * sx, v * 100, "#" * int(v * 40)))
    rx, rz = runs(m, 1), runs(m, 0)
    print("   hole run  x median %.2f px = %.3f mm   max %.2f px = %.3f mm"
          % (np.median(rx), np.median(rx) * sx, rx.max(), rx.max() * sx))
    print("   hole run  z median %.2f px = %.3f mm   max %.2f px = %.3f mm"
          % (np.median(rz), np.median(rz) * sx, rz.max(), rz.max() * sx))
    # rows with no opening at all - the gap the downsampled comparison hid
    gaps = [lo + i * sx for i, v in enumerate(share) if v < 0.02]
    print("   rows with under 2%% dark: %d %s"
          % (len(gaps), " ".join("%.2f" % v for v in gaps[:20])))
    return share


def main():
    s = load("rear")
    gr = s["g"].astype(np.float64) / 255.0
    sx = s["sx"]
    W = s["width_px"]
    mh = int(round(W * H_MM / W_MM))
    print("photograph: %d x %d px at %.5f mm/px" % (W, mh, sx))

    mp = os.path.join(OUT, "rear_model.png")
    mi = Image.open(mp).convert("L")
    # resample the model's chassis crop onto the photograph's pixel grid
    target = (W, mh)
    mi = mi.resize(target, Image.LANCZOS)
    gm = np.asarray(mi, dtype=np.float64) / 255.0
    print("model:     resampled %s -> %s at %.5f mm/px" % (mp, target, sx))

    analyse(gr, sx, "APPLE  rear")
    analyse(gm, sx, "MODEL  rear")


if __name__ == "__main__":
    main()
