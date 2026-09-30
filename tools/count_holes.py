#!/usr/bin/env python3
"""Count holes along one full row of the rear field, and print the profile.

Peak counting over a short patch is sensitive to the threshold and to where
the patch starts; counting every dark run across the full 171 mm of the field
is not. If the row is picked through the middle of a hole row, the number of
runs is the number of holes, and the field width is known to 0.1 mm, so the
pitch falls out with no fitting.
"""
import os

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REF = os.path.join(ROOT, "reference")

MMPP = 197.0 / 1305.0
X0, TOP_ROW = 4, 6
FW_MM = 171.5          # field width from check_field_symmetry.py


def runs(mask):
    out, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(mask) - 1))
    return out


def main():
    g = np.asarray(Image.open(os.path.join(REF, "apple_hw_back.jpg"))
                   .convert("L"), dtype=np.float32)
    row = lambda mm: TOP_ROW + int(mm / MMPP)   # noqa: E731

    # find the row band with the most dark pixels: that is a hole row, seen
    # edge-on through the middle of the holes
    prof = np.zeros(60)
    for i in range(60):
        y = row(12) + i
        prof[i] = (g[y, X0 + 100:X0 + 1100] < 128).mean()
    best = int(np.argmax(prof))
    y = row(12) + best
    print("densest hole row at %.2f mm from the top (%.0f%% dark)"
          % ((y - TOP_ROW) * MMPP, 100 * prof[best]))

    strip = g[y, X0 + 90:X0 + 1110].astype(np.float64)
    thr = 0.5 * (np.median(strip) + strip.min())
    r = runs(strip < thr)
    # merge runs separated by a single bright pixel (antialiasing bridges)
    merged = []
    for s, e in r:
        if merged and s - merged[-1][1] <= 2:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    widths = np.array([e - s + 1 for s, e in merged], dtype=float)
    print("  %d holes across %d px = %.2f mm"
          % (len(merged), strip.size, strip.size * MMPP))
    print("  run width  mean %.2f px = %.3f mm   min %d  max %d"
          % (widths.mean(), widths.mean() * MMPP, widths.min(), widths.max()))
    pitches = np.diff([s for s, _ in merged])
    print("  start-to-start  mean %.2f px = %.3f mm   sd %.2f px"
          % (pitches.mean(), pitches.mean() * MMPP, pitches.std()))

    # vertical: count dark runs down a column through the middle of a hole
    col = g[row(8):row(50), X0 + 90 + merged[0][0] + 1].astype(np.float64)
    cthr = 0.5 * (np.median(col) + col.min())
    cr = runs(col < cthr)
    cm = []
    for s, e in cr:
        if cm and s - cm[-1][1] <= 2:
            cm[-1] = (cm[-1][0], e)
        else:
            cm.append((s, e))
    print("  vertical: %d holes over %d px = %.2f mm, pitch %.3f mm"
          % (len(cm), col.size, col.size * MMPP,
             (col.size / max(len(cm), 1)) * MMPP))

    # and the base band, same method
    for lo, hi, tag in ((89.0, 94.5, "band"),):
        yb = row(lo)
        strip = g[yb:yb + int((hi - lo) / MMPP), X0 + 300:X0 + 600].astype(float)
        dark = (strip < 0.5 * (np.median(strip) + strip.min())).mean(axis=0)
        colsum = dark
        r = runs(colsum > 0.35)
        merged2 = []
        for s, e in r:
            if merged2 and s - merged2[-1][1] <= 2:
                merged2[-1] = (merged2[-1][0], e)
            else:
                merged2.append((s, e))
        print("  %s: %d columns over %d px = %.2f mm, pitch %.3f mm"
              % (tag, len(merged2), strip.shape[1], strip.shape[1] * MMPP,
                 (strip.shape[1] / max(len(merged2), 1)) * MMPP))


if __name__ == "__main__":
    main()
