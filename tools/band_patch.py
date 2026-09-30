#!/usr/bin/env python3
"""Blow up a small patch of the base band so the hole shape can be judged.

A round hole in a 197 mm panel is about 22 px across in the full-resolution
photograph, which is not enough to tell a circle from a flattened oval by eye at
1:1. This crops a patch at 12x nearest-neighbour and draws the fitted pitch grid
on top, so the shape of the holes and the lattice they sit on can be checked
together against what the spec claims.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))

import mac_studio_spec as S      # noqa: E402
from verify_spec import load    # noqa: E402

OUT = os.path.join(ROOT, "renders", "compare")
ZOOM = 12

# Fitted from tools/fit_band_lattice.py against apple_hw_back.jpg, in
# millimetres. They are written in mm here because that is the unit sx is in;
# an earlier version held the centimetre values from the spec and drew a grid
# ten times too dense, which made the overlay useless for checking the fit.
FIT_X_MM = 1.962
FIT_Z_MM = 0.906


def patch(view, cx_mm, cy_mm, span_mm=12.0, tag="rear"):
    s = load(view)
    g, sx, x0, y0 = s["g"], s["sx"], s["x0"], s["y0"]
    n = int(span_mm / sx)
    cx = x0 + int(round(cx_mm / sx))
    cy = y0 + int(round(cy_mm / sx))
    a, b = max(0, cy - n // 2), min(g.shape[0], cy + n // 2)
    c, d = max(0, cx - n // 2), min(g.shape[1], cx + n // 2)
    print("   sx=%.5f  window %d px, crop rows %d..%d cols %d..%d of %s"
          % (sx, n, a, b, c, d, g.shape))
    crop = Image.fromarray(g[a:b, c:d].astype(np.uint8))
    big = crop.resize((crop.size[0] * ZOOM, crop.size[1] * ZOOM),
                      Image.NEAREST).convert("RGB")
    dr = ImageDraw.Draw(big)

    # lattice overlay. Alternating rows are offset by half a pitch, which is
    # what separates a hexagonal band from a square one - if the overlay looks
    # right on the photo, the fit is right.
    step_x = FIT_X_MM / sx
    step_z = FIT_Z_MM / sx
    ox = (cx - c) % step_x
    oz = (cy - a) % step_z
    k = 0
    while True:
        xx = (ox + k * step_x) * ZOOM
        if xx > big.size[0]:
            break
        dr.line([(xx, 0), (xx, big.size[1])], fill=(255, 0, 0))
        k += 1
    k = 0
    while True:
        yy = (oz + k * step_z) * ZOOM
        if yy > big.size[1]:
            break
        dr.line([(0, yy), (big.size[0], yy)], fill=(0, 160, 255))
        k += 1

    p = os.path.join(OUT, "bandpatch_%s_%s.png" % (view, tag))
    big.save(p)
    print("wrote %s  %s  (%.0f mm window, %dx zoom, centre %.1f/%.1f mm)"
          % (p, big.size, span_mm, ZOOM, cx_mm, cy_mm))
    print("   red = fitted x pitch %.3f mm, blue = fitted z pitch %.3f mm"
          % (FIT_X_MM, FIT_Z_MM))
    print("   spec claims %.3f / %.3f mm"
          % (S.GRILLE_PITCH_X * 10.0, S.GRILLE_PITCH_Z * 10.0))


def main():
    patch("rear", 98.5, 91.0, 12.0, "mid")
    patch("rear", 40.0, 91.0, 12.0, "left")
    patch("rear", 160.0, 91.0, 12.0, "right")


if __name__ == "__main__":
    main()
