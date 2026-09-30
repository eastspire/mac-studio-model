#!/usr/bin/env python3
"""Hole diameter from the dark area fraction of the field and the band.

With the pitch known from tools/fit_lattice.py, the only remaining unknown is
the hole size. Area fraction is the robust route: a hole is 3-4 px across, so
measuring one hole measures the JPEG ringing around it, but the *fraction* of
a 100 x 300 px patch that is hole is stable and the cell area is known.

    dark fraction = pi (d/2)^2 / (pitch_x * row_y)
"""
import os

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REF = os.path.join(ROOT, "reference")

MMPP = 197.0 / 1305.0
X0, TOP_ROW = 4, 6

# from fit_lattice.py
FIELD = (1.86, 1.57)
BAND = (0.93, 1.02)


def diameter(patch, pitch, row, label):
    lo = np.percentile(patch, 2.0)
    hi = np.percentile(patch, 98.0)
    mid = 0.5 * (lo + hi)
    frac = float((patch < mid).mean())
    d = np.sqrt(frac * pitch * row * 4.0 / np.pi)
    print("  %-14s dark fraction %.3f  ->  hole diameter %.2f mm  "
          "(%.0f%% of pitch, open area %.1f%%)"
          % (label, frac, d, 100.0 * d / pitch, 100.0 * frac))
    return d


def main():
    g = np.asarray(Image.open(os.path.join(REF, "apple_hw_back.jpg"))
                   .convert("L"), dtype=np.float32)
    row = lambda mm: TOP_ROW + int(mm / MMPP)   # noqa: E731
    print("REAR FIELD  pitch %.2f x row %.2f mm" % FIELD)
    for a, b in ((8, 30), (24, 48), (10, 44)):
        diameter(g[row(a):row(b), X0 + 150:X0 + 450], FIELD[0], FIELD[1],
                 "rows %d-%d mm" % (a, b))
    print("BASE BAND   pitch %.2f x row %.2f mm" % BAND)
    for a, b in ((88.8, 94.2),):
        diameter(g[row(a):row(b), X0 + 250:X0 + 550], BAND[0], BAND[1],
                 "rows %.1f-%.1f mm" % (a, b))


if __name__ == "__main__":
    main()
