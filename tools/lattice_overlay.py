#!/usr/bin/env python3
"""Draw the fitted hole lattice over the real photograph to confirm it.

`fit_lattice.py` produces (pitch, row spacing, stagger) by correlation. A
correlation score is not a picture, and this project's whole lesson so far is
that a self-consistent number can be wrong in a way no self-check catches — so
the fitted lattice is drawn straight onto the magnified photograph. If the
dots land in the holes, the number is right; if they drift, it is not.
"""
import os

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REF = os.path.join(ROOT, "reference")
OUT = os.path.join(ROOT, "renders", "compare")

MMPP = 197.0 / 1305.0
X0, TOP_ROW = 4, 6

# (pitch_mm, row_spacing_mm, stagger_fraction, colour) — from tools/fit_lattice.py
FIELD_FIT = (1.86, 1.44, 0.25, (255, 40, 40))
BAND_FIT = (0.92, 1.04, 0.00, (40, 200, 60))


def overlay(g, x0_mm, x1_mm, y0_mm, y1_mm, fits, scale, out, r=7):
    c0 = X0 + int(x0_mm / MMPP)
    c1 = X0 + int(x1_mm / MMPP)
    r0 = TOP_ROW + int(y0_mm / MMPP)
    r1 = TOP_ROW + int(y1_mm / MMPP)
    base = Image.fromarray(g[r0:r1, c0:c1].astype(np.uint8)).convert("RGB")
    base = base.resize((base.width * scale, base.height * scale), Image.LANCZOS)
    print("%s  %.1f..%.1f mm x, %.1f..%.1f mm y -> %s"
          % (out, x0_mm, x1_mm, y0_mm, y1_mm, out))
    for p, row_mm, stag, colour in fits:
        # The canvas must be RGBA or Pillow drops the alpha fill and the
        # overlay comes out invisible.
        im = base.convert("RGBA")
        d = ImageDraw.Draw(im, "RGBA")
        step = p / MMPP * scale
        ystep = row_mm / MMPP * scale
        # Phase is taken in MILLIMETRES. Taking it against the pixel step
        # pushes the first row off the canvas, every while-loop is skipped,
        # and the tool silently writes a picture with no overlay on it.
        xs = (x0_mm % p) / MMPP * scale
        ys = (y0_mm % row_mm) / MMPP * scale
        yy, i = ys, 0
        while yy < im.height:
            xx = xs + (stag * step if i % 2 else 0.0)
            while xx < im.width:
                d.ellipse([xx - r, yy - r, xx + r, yy + r], fill=colour + (130,))
                xx += step
            yy += ystep
            i += 1
        d.rectangle([0, 0, 230, 20], fill=colour + (255,))
        d.text((4, 4), "p=%.2f  row=%.2f  stag=%.2f" % (p, row_mm, stag),
               fill=(0, 0, 0, 255))
        im.convert("RGB").save(os.path.join(OUT, out))
    base.save(os.path.join(OUT, out.replace(".png", "_plain.png")))


def main():
    os.makedirs(OUT, exist_ok=True)
    g = np.asarray(Image.open(os.path.join(REF, "apple_hw_back.jpg"))
                   .convert("L"), dtype=np.float32)
    overlay(g, 14.0, 32.0, 10.0, 20.0, [FIELD_FIT], 8, "lattice_field_fit.png")
    overlay(g, 46.0, 64.0, 88.6, 94.4, [BAND_FIT], 8, "lattice_band_fit.png")


if __name__ == "__main__":
    main()
