#!/usr/bin/env python3
"""Settle the front panel's x origin: which chassis edge is column 0?

The rear ports agree with the spec to a tenth of a millimetre, but the front
ones came out 7.9 mm off - a CONSTANT offset, so the layout is right and only
the origin is in question. A constant offset can only come from the box, so
this prints the silhouette edges and the absolute pixel columns of the front
openings, and cross-checks the same quantity on the rear where the spec is
known to be correct.
"""
import os

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REF = os.path.join(ROOT, "reference")

for fn in ("apple_static_front.jpg", "apple_hw_back.jpg"):
    g = np.asarray(Image.open(os.path.join(REF, fn)).convert("L"),
                   dtype=np.float32) / 255.0
    h, w = g.shape
    print("\n== %s   %d x %d" % (fn, w, h))
    for frac in (0.30, 0.45, 0.50, 0.62, 0.75):
        y = int(h * frac)
        row = g[y]
        idx = np.nonzero(row < 238.0 / 255.0)[0]
        print("   row %4d (%.0f%% down): body cols %s .. %s   width %d"
              % (y, frac * 100, idx[0] if idx.size else "-",
                 idx[-1] if idx.size else "-", idx.size))

    # background estimate from the extreme columns
    bg = np.median(np.concatenate([g[:, :6].ravel(), g[:, -6:].ravel()]))
    print("   edge background median %.1f   centre-column background %.1f"
          % (bg, np.median(g[:, w // 2])))
    diff = np.abs(g - bg)
    for thr in (4.0, 6.0, 8.0):
        cnt = (diff > thr).sum(axis=1)
        full = np.nonzero(cnt >= 0.99 * cnt.max())[0]
        print("   thr %4.1f: max width %4d px, full-width rows %d..%d"
              % (thr, cnt.max(), full[0], full[-1]))
