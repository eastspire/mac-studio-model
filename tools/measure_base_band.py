#!/usr/bin/env python3
"""Measure the base band's four edges in Apple's rear photograph.

Two traps this has to avoid.

1. The first attempt took "dark pixels" in the bottom strip as the band. It ran
   to 96.2 mm - past the bottom of the machine - because the contact shadow
   under the chassis is dark too. The band has to be found as machine against a
   WHITE background, not as anything darker than the strip's median.

2. The band's lower edge is not straight. It follows the chassis corner radius,
   so at the far left and right it curves up to meet the top edge while in the
   middle it reaches the bottom of the machine. Reporting one height would
   average those two behaviours into a number that describes neither, so the
   per-column top and bottom are both reported.
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from compare_render import (normalise_ref, otsu, largest_blob_fraction,  # noqa: E402
                            REF)

W_MM, H_MM = 197.0, 95.0
OUT_H = 460
WHITE = 0.93          # the product ground is a clean white sweep


def main():
    img = normalise_ref(os.path.join(REF, "apple_hw_back.jpg"), OUT_H)
    g = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
    h, w = g.shape
    sx = W_MM / w
    print("rear reference crop %dx%d, %.4f mm/px" % (w, h, sx))

    # --- 1. silhouette: where does the machine stop and the white ground start
    machine = g < WHITE
    print("ground white above %.2f; panel max %.3f" % (WHITE, g[:int(h * 0.5)].max()))

    sil_bot = []
    for c in range(w):
        ys = np.nonzero(machine[:, c])[0]
        sil_bot.append(ys[-1] if len(ys) else -1)
    sil_bot = np.array(sil_bot)
    ok = sil_bot > 0
    print("\nsilhouette bottom: min %.2f  max %.2f mm (cols with machine: %d/%d)"
          % (sil_bot[ok].min() * sx, sil_bot[ok].max() * sx, ok.sum(), w))

    # --- 2. the perforated band
    # A fixed cut against "white" is not enough: the plain panel just above the
    # band sits at 0.75-0.77 grey, so a threshold of 0.77 swallows the whole
    # lower panel and every column then reports the same top and bottom. The
    # band has to be split on its own two modes, and the split has to be
    # accepted only if the dark class is made of many small blobs - which is
    # what distinguishes it from the lighting gradient of bare metal.
    #
    # The window is the band's interior only, in the middle 60% of the width.
    # Taking the whole 82-95 mm strip mixes bare panel above the band and the
    # contact shadow below it into the same histogram, and the dark class then
    # contains one big connected region, which is exactly what the blob test
    # below is there to catch.
    y_lo = int(round(87.5 / sx))
    y_hi = int(round(94.0 / sx))
    cx_a, cx_b = int(w * 0.20), int(w * 0.80)
    win = g[y_lo:y_hi, cx_a:cx_b]
    thr, eta = otsu(win)
    lf = largest_blob_fraction(win < thr)
    print("\nband interior %.1f..%.1f mm, middle 60%% of width: Otsu %.3f, "
          "eta %.2f, largest dark blob %.1f%%"
          % (87.5, 94.0, thr, eta, lf * 100.0))
    if lf > 0.10:
        print("  dark class is one contiguous region, not perforation - "
              "the split is a lighting gradient, refusing to measure")
        return
    thr_r, _ = otsu(g[y_lo:y_hi, :])
    print("  threshold for the full-width pass: %.3f" % thr_r)

    band = np.zeros_like(machine)
    for c in range(w):
        if sil_bot[c] <= y_lo:
            continue
        band[y_lo:sil_bot[c] + 1, c] = g[y_lo:sil_bot[c] + 1, c] < thr_r

    colsum = band.sum(axis=0)
    cols = np.nonzero(colsum > 2)[0]
    if not len(cols):
        print("no band found")
        return
    cx0, cx1 = int(cols[0]), int(cols[-1])
    print("\nband columns %d..%d -> %.2f..%.2f mm from left; inset %.2f / %.2f mm;"
          " width %.2f mm"
          % (cx0, cx1, cx0 * sx, (cx1 + 1) * sx, cx0 * sx,
             W_MM - (cx1 + 1) * sx, (cx1 + 1 - cx0) * sx))

    rows = []
    for c in range(cx0, cx1 + 1):
        ys = np.nonzero(band[:, c])[0]
        if not len(ys):
            continue
        rows.append(((c + 0.5) * sx, (ys[0]) * sx, (ys[-1] + 1) * sx,
                     (ys[-1] + 1 - ys[0]) * sx))
    rows = np.array(rows)
    centre = rows[(rows[:, 0] > 40) & (rows[:, 0] < 157)]
    print("band top    : min %.2f  max %.2f mm   (centre columns: %.2f mm)"
          % (rows[:, 1].min(), rows[:, 1].max(), centre[:, 1].mean()))
    print("band bottom : min %.2f  max %.2f mm   (centre columns: %.2f mm)"
          % (rows[:, 2].min(), rows[:, 2].max(), centre[:, 2].mean()))
    print("band height : min %.2f  max %.2f mm   (centre columns: %.2f mm)"
          % (rows[:, 3].min(), rows[:, 3].max(), centre[:, 3].mean()))

    print("\n  x_mm   top_mm  bot_mm  height_mm")
    for target in range(4, 198, 8):
        i = int(np.argmin(np.abs(rows[:, 0] - target)))
        if abs(rows[i, 0] - target) < 4.5:
            print("  %5.1f   %6.2f  %6.2f  %6.2f" % tuple(rows[i]))

    # the band closes (height -> 0) at each end; that is the corner radius
    hgt = rows[:, 3]
    left = rows[hgt < 1.0]
    right = rows[hgt < 1.0]
    if len(hgt):
        print("\nband spans x=%.1f..%.1f mm, so %.1f mm of the %.0f mm width"
              % (rows[0, 0], rows[-1, 0], rows[-1, 0] - rows[0, 0], W_MM))


if __name__ == "__main__":
    main()
