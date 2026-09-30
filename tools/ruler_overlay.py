#!/usr/bin/env python3
"""Overlay a millimetre ruler on a crop so a measured column can be eyeballed.

Numbers from a connected-component pass are only as good as the origin they
were measured from, and a 7.9 mm origin error is invisible in a table and
obvious on a picture. This draws the chassis left edge, the 98.5 mm centre,
and a tick every 10 mm of model x, so the openings can be checked against the
ruler rather than against a remembered number.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REF = os.path.join(ROOT, "reference")
OUT = os.path.join(ROOT, "renders", "compare")

# file, chassis left column, chassis width in px, model-x mapping sign
SHOTS = {
    "front": ("apple_static_front.jpg", 4, 1392, +1),
    "rear": ("apple_hw_back.jpg", 4, 1304, -1),
}
HALF = 98.5
HALFI = 98
OUT_TICKS = os.path.join(OUT, "ruler_%s.png")


def col_of_mm(mm, x0, sx, sign):
    """Pixel column of a given model x, given the chassis left column."""
    return x0 + (HALF - sign * mm) / sx


def ruler(name, y0, y1, scale=2):
    fn, x0, wpx, sign = SHOTS[name]
    sx = 197.0 / wpx
    im = Image.open(os.path.join(REF, fn)).convert("RGB").crop((0, y0, wpx + 8, y1))
    im = im.resize((im.width * scale, im.height * scale), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    for mm in range(-HALFI, HALFI + 1, 10):
        col = col_of_mm(mm, x0, sx, sign)
        c = int(round(col * scale))
        if not (0 <= c < im.width):
            continue
        big = (mm % 50 == 0)
        d.line([(c, 0), (c, im.height if big else 14)], fill=(255, 0, 0), width=1)
        if big:
            d.text((c + 2, 1), "%d" % mm, fill=(255, 0, 0))
    c = int(round((x0 + HALF / sx) * scale))
    d.line([(c, 0), (c, im.height)], fill=(0, 110, 255), width=2)
    d.text((c + 3, im.height - 14), "model x=0", fill=(0, 110, 255))
    out = os.path.join(OUT, "ruler_%s.png" % name)
    im.save(out)
    print("%s  crop rows %d..%d  ->  %s  (%dx%d)  scale %.4f mm/px"
          % (name, y0, y1, out, im.width, im.height, sx))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    ruler("front", 455, 545)
    ruler("rear", 395, 545)
