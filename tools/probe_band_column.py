#!/usr/bin/env python3
"""Grey levels down one column through the base band, and the same in the model.

Prints the actual numbers so the threshold used to find the band's edges can be
chosen from evidence rather than from a guess that happened to work.
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from compare_render import normalise_ref, otsu, largest_blob_fraction, REF, OUT  # noqa

W_MM, H_MM = 197.0, 95.0


def column(name, g, sx, frac_x, lo, hi):
    h, w = g.shape
    c = int(round(frac_x / W_MM * w))
    print("\n--- %s : column at %.0f mm (px %d of %d) ---" % (name, frac_x, c, w))
    y0 = int(round(lo / sx))
    y1 = min(h, int(round(hi / sx)))
    col = g[y0:y1, c]
    print("  grey (x10) by mm from top:")
    for i in range(0, len(col), 2):
        mm = (y0 + i) * sx
        bar = "#" * int(col[i] * 30)
        print("   %5.1f  %4d  %s" % (mm, round(col[i] * 1000), bar))
    # local bimodality on the band rows only
    band = g[int(round(88.0 / sx)):int(round(94.0 / sx)), c]
    t, eta = otsu(band)
    print("  band rows 88-94 mm at this column: min %.3f max %.3f "
          "otsu %.3f eta %.2f" % (band.min(), band.max(), t, eta))
    return col


def main():
    img = normalise_ref(os.path.join(REF, "apple_hw_back.jpg"), 460)
    gr = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
    sx = W_MM / gr.shape[1]
    column("REFERENCE", gr, sx, 98.5, 78.0, 95.0)

    p = os.path.join(OUT, "rear_model.png")
    if os.path.exists(p):
        gm = np.asarray(Image.open(p).convert("L"), dtype=np.float32) / 255.0
        sxm = W_MM / gm.shape[1]
        column("MODEL", gm, sxm, 98.5, 78.0, 95.0)

    # and a zoomed view of the band in both
    zooms = [("ref", gr, sx)]
    if os.path.exists(p):
        gm2 = np.asarray(Image.open(p).convert("L"), dtype=np.float32) / 255.0
        zooms.append(("model", gm2, W_MM / gm2.shape[1]))
    for tag, arr, sc in zooms:
        h, w = arr.shape
        y0 = int(round(85.0 / sc))
        y1 = min(h, int(round(95.0 / sc)))
        strip = arr[y0:y1, int(0.25 * w):int(0.75 * w)]
        img2 = Image.fromarray((np.clip(strip, 0, 1) * 255).astype(np.uint8))
        img2 = img2.resize((img2.size[0] * 3, img2.size[1] * 3), Image.NEAREST)
        q = os.path.join(OUT, "bandzoom_%s.png" % tag)
        img2.save(q)
        print("\nwrote %s %s (85-95 mm, middle half of width, 3x)" % (q, img2.size))


if __name__ == "__main__":
    main()
