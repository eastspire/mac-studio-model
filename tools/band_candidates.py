#!/usr/bin/env python3
"""Draw candidate lattices straight onto the base band and look at which fits.

The numeric stagger estimate disagreed with what the zoomed photo appeared to
show, so this settles it by overlay rather than by argument: each candidate
lattice is drawn as a thin outline over the same patch of the photograph, and
the one whose outlines sit on the holes is the one the model should use.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))

from verify_spec import load  # noqa: E402

OUT = os.path.join(ROOT, "renders", "compare")
ZOOM = 14
W_MM, H_MM = 197.0, 95.0

CANDIDATES = [
    # (label, pitch_x_mm, pitch_z_mm, stagger, rx_mm, rz_mm)
    ("stagger0.00", 1.962, 0.906, 0.00, 0.75, 0.28),
    ("stagger0.50", 1.962, 0.906, 0.50, 0.75, 0.28),
    ("stagger0.50_z0.45", 1.962, 0.453, 0.50, 0.75, 0.20),
    ("stagger0.00_z0.45", 1.962, 0.453, 0.00, 0.75, 0.20),
]


def draw_candidate(view, cx_mm, cy_mm, label, px, pz, stagger, rx, rz,
                   span_mm=7.0):
    s = load(view)
    g, sx, x0, y0 = s["g"], s["sx"], s["x0"], s["y0"]
    n = int(span_mm / sx)
    cx = x0 + int(round(cx_mm / sx))
    cy = y0 + int(round(cy_mm / sx))
    a, b = max(0, cy - n // 2), min(g.shape[0], cy + n // 2)
    c, d = max(0, cx - n // 2), min(g.shape[1], cx + n // 2)
    crop = Image.fromarray(g[a:b, c:d].astype(np.uint8))
    big = crop.resize((crop.size[0] * ZOOM, crop.size[1] * ZOOM),
                      Image.NEAREST).convert("RGB")
    dr = ImageDraw.Draw(big)

    # hole outlines, placed on the photo's own millimetre grid
    k0 = int(np.floor((c - x0) * sx / px)) - 1
    k1 = int(np.ceil((d - x0) * sx / px)) + 1
    r0 = int(np.floor((a - y0) * sx / pz)) - 1
    r1 = int(np.ceil((b - y0) * sx / pz)) + 1
    for r in range(r0, r1 + 1):
        zc = (r + 0.5) * pz
        off = (r % 2) * stagger * px
        for k in range(k0, k1 + 1):
            xc = k * px + off
            # to patch-local pixels, then to the zoomed image
            px_ = (xc - (c - x0) * sx) / sx * ZOOM
            py_ = (zc - (a - y0) * sx) / sx * ZOOM
            rx_ = rx / sx * ZOOM
            ry_ = rz / sx * ZOOM
            if px_ < -rx_ or px_ > big.size[0] + rx_:
                continue
            if py_ < -ry_ or py_ > big.size[1] + ry_:
                continue
            dr.ellipse([px_ - rx_, py_ - ry_, px_ + rx_, py_ + ry_],
                       outline=(255, 40, 40), width=1)

    p = os.path.join(OUT, "cand_%s_%s.png" % (view, label))
    big.save(p)
    return p, big.size


def main():
    for label, px, pz, stag, rx, rz in CANDIDATES:
        p, size = draw_candidate("rear", 98.5, 91.0, label, px, pz, stag, rx, rz)
        print("wrote %-34s %s  (x %.3f  z %.3f  stagger %.2f  hole %.2fx%.2f mm)"
              % (os.path.basename(p), size, px, pz, stag, 2 * rx, 2 * rz))


if __name__ == "__main__":
    main()
