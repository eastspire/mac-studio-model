#!/usr/bin/env python3
"""Print the row-brightness curve near the bottom of each Apple photo.

The sampled version of this hid the answer: a 3% step is 2.9 mm, which is the
same order as the feature being located. Every row is printed here, in mm from
the top of the chassis, so the top and bottom of the base band can be read off
directly instead of inferred from a threshold.
"""
import os

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REF = os.path.join(ROOT, "reference")

# The front photo has unambiguous edges: the body's left/right silhouette gives
# the scale from the known 197 mm width, and the strong bottom gradient gives
# the foot plane. It is used as the vertical datum for both shots.
SHOT = {
    "front": ("apple_static_front.jpg", 1393, 6, 679),
    "rear": ("apple_hw_back.jpg", 1306, 6, 636),
}
WIDTH_MM, HEIGHT_MM = 197.0, 95.0


def run(name, lo_mm=70.0, hi_mm=96.0):
    fn, wpx, top, bot = SHOT[name]
    mmpp = WIDTH_MM / wpx
    g = np.asarray(Image.open(os.path.join(REF, fn)).convert("L"),
                   dtype=np.float32) / 255.0
    h, w = g.shape
    prof = g[:, int(w * 0.30):int(w * 0.70)].mean(axis=1)
    print("\n== %s  %s  %.5f mm/px  chassis file rows %d..%d (%.1f mm)"
          % (name, fn, mmpp, top, bot, (bot - top) * mmpp))
    print("    mm_top  file_y   mean   (columns 30-70%%)")
    prev = None
    for y in range(top, bot + 1):
        mm = y * mmpp
        if not (lo_mm <= mm <= hi_mm):
            continue
        v = prof[y]
        d = "" if prev is None else "%+6.3f" % (v - prev)
        bar = "#" * int(round(max(v, 0) * 40))
        print("   %6.2f  %5d  %.3f %s  %s" % (mm, y, v, d, bar))
        prev = v


if __name__ == "__main__":
    for n in ("front", "rear"):
        run(n)
