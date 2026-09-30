#!/usr/bin/env python3
"""One glyph, photo over model, at the same scale.

Reading an 11x16 px glyph out of a character map is guesswork, so each glyph
gets an image instead: Apple's photograph on top, the model's own geometry
rasterised from S.ICON_GLYPHS below it, same crop, same scale, same pixel
grid. A rear view mirrors the model, so the model side is drawn at -x; that is
why the two halves line up and why the bolt leans the way it does.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))

import mac_studio_spec as S                                # noqa: E402
from compare_render import glyph_mask                      # noqa: E402
from verify_spec import load                               # noqa: E402

OUT = os.path.join(ROOT, "renders", "compare")
W_MM, H_MM = 197.0, 95.0
ZOOM = 18
HALF_MM = 3.4

GLYPHS = ["thunderbolt", "ethernet", "usb", "hdmi", "headphone"]


def stretch(a, lo_p=0.5, hi_p=99.5):
    lo, hi = np.percentile(a, lo_p), np.percentile(a, hi_p)
    if hi - lo < 1e-6:
        return np.zeros_like(a)
    return np.clip((a - lo) / (hi - lo), 0.0, 1.0)


def main():
    only = sys.argv[1:] or GLYPHS
    s = load("rear")
    g, sx, x0, y0 = s["g"], s["sx"], s["x0"], s["y0"]

    for name in only:
        cx_cm = S.ICON_GLYPH_X[name]
        cx_mm = 98.5 - cx_cm * 10
        cy_mm = H_MM - S.ICON_Z * 10
        ix0 = x0 + int(round((cx_mm - HALF_MM) / sx))
        ix1 = x0 + int(round((cx_mm + HALF_MM) / sx))
        iy0 = y0 + int(round((cy_mm - HALF_MM) / sx))
        iy1 = y0 + int(round((cy_mm + HALF_MM) / sx))
        photo = stretch(g[iy0:iy1 + 1, ix0:ix1 + 1])

        # the model's marks on the SAME grid, mirrored because a rear view is
        # a mirror: an image column c is model x = cx_mm - (c - col_centre)*mm
        cols = np.arange(ix0, ix1 + 1) - x0
        rows = np.arange(iy0, iy1 + 1) - y0
        mcol, mrow = np.meshgrid(cols, rows)
        mx = 9.85 - mcol * sx / 10.0
        mz = (H_MM - mrow * sx) / 10.0
        model = glyph_mask(mx, mz, name=name)

        h, w = photo.shape
        sheet = Image.new("RGB", (w * ZOOM, 2 * h * ZOOM + 10), (255, 255, 255))
        top = Image.fromarray((photo * 255).astype(np.uint8)).convert("RGB")
        bot = Image.fromarray(((~model) * 255).astype(np.uint8)).convert("RGB")
        sheet.paste(top.resize((w * ZOOM, h * ZOOM), Image.LANCZOS), (0, 0))
        sheet.paste(bot.resize((w * ZOOM, h * ZOOM), Image.NEAREST), (0, h * ZOOM + 10))
        d = ImageDraw.Draw(sheet)
        d.rectangle([0, 0, w * ZOOM - 1, h * ZOOM - 1], outline=(30, 30, 30))
        d.rectangle([0, h * ZOOM + 10, w * ZOOM - 1, 2 * h * ZOOM + 9],
                    outline=(30, 30, 30))
        d.text((6, 6), "apple_hw_back.jpg  x%g" % ZOOM, fill=(20, 20, 120))
        d.text((6, h * ZOOM + 16), "model ICON_GLYPHS  x%g" % ZOOM, fill=(120, 20, 20))

        p = os.path.join(OUT, "glyph_%s.png" % name)
        sheet.save(p)
        print("%-13s %s  %dx%d  crop %.1f mm" % (name, p, w * ZOOM,
                                                 2 * h * ZOOM + 10, w * sx))


if __name__ == "__main__":
    main()
