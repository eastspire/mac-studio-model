#!/usr/bin/env python3
"""Enlarge the engraved icon row out of apple_hw_back.jpg, glyph by glyph.

The icon row is about 3 mm tall in a 644 px-tall photograph, so on screen it is
a smudge. Each glyph is cut at full resolution, contrast-stretched and scaled
up with nearest-neighbour so the pixels stay honest, then the spec's own x for
that glyph is drawn as a vertical rule through it. That answers two questions
at once: what the glyph actually looks like, and whether it sits on the
connector it labels.
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))

import mac_studio_spec as S      # noqa: E402
from verify_spec import load     # noqa: E402

OUT = os.path.join(ROOT, "renders", "compare")
W_MM, H_MM = 197.0, 95.0
ZOOM = 6

# (label, measured blob centre in cm, half-width of the crop in cm)
GLYPHS = [
    ("thunderbolt", S.ICON_TB_X, 0.62),
    ("ethernet", S.ICON_ETH_X, 0.62),
    ("usb", S.ICON_USB_X, 0.62),
    ("hdmi", S.ICON_HDMI_X, 0.62),
    ("headphone", S.ICON_HP_X, 0.62),
]


def stretch(a, lo_p=1.0, hi_p=99.0):
    lo, hi = np.percentile(a, lo_p), np.percentile(a, hi_p)
    if hi - lo < 1e-6:
        return np.zeros_like(a)
    return np.clip((a - lo) / (hi - lo), 0.0, 1.0)


def main():
    s = load("rear")
    g, sx, x0, y0, width_px = s["g"], s["sx"], s["x0"], s["y0"], s["width_px"]

    # the whole row first, so the spacing of the five glyphs is visible at once
    top_mm = H_MM - (S.ICON_Z + 0.30) * 10
    bot_mm = H_MM - (S.ICON_Z - 0.30) * 10
    rx0, rx1 = x0 + int(round(2.0 / sx)), x0 + width_px - int(round(2.0 / sx))
    ry0 = y0 + int(round(top_mm / sx))
    ry1 = y0 + int(round(bot_mm / sx))
    row = stretch(g[ry0:ry1 + 1, rx0:rx1 + 1])
    im = Image.fromarray((row * 255).astype(np.uint8))
    im = im.resize((im.width * ZOOM, im.height * ZOOM), Image.NEAREST)
    im.save(os.path.join(OUT, "iconrow_ref.png"))
    print("icon row  %.1f..%.1f mm from the top -> renders/compare/iconrow_ref.png"
          % (top_mm, bot_mm))

    tiles = []
    for name, cx_cm, half_cm in GLYPHS:
        cx_mm = 98.5 - cx_cm * 10          # rear view: model -x is to the right
        cy_mm = H_MM - S.ICON_Z * 10
        ix0 = x0 + int(round((cx_mm - half_cm * 10) / sx))
        ix1 = x0 + int(round((cx_mm + half_cm * 10) / sx))
        iy0 = y0 + int(round((cy_mm - half_cm * 10) / sx))
        iy1 = y0 + int(round((cy_mm + half_cm * 10) / sx))
        ix0, ix1 = max(ix0, x0), min(ix1, x0 + width_px - 1)
        patch = stretch(g[iy0:iy1 + 1, ix0:ix1 + 1])
        t = Image.fromarray((patch * 255).astype(np.uint8))
        t = t.resize((t.width * ZOOM, t.height * ZOOM), Image.NEAREST)
        tiles.append((name, t, (cx_mm - (cx_mm - half_cm * 10)) / sx * ZOOM))

    th = max(t.height for _, t, _ in tiles)
    sheet = Image.new("L", (sum(t.width + 8 for _, t, _ in tiles), th), 255)
    ox = 0
    for _, t, _ in tiles:
        sheet.paste(t, (ox, 0))
        ox += t.width + 8
    p = os.path.join(OUT, "icons_ref_zoom.png")
    sheet.save(p)
    print("glyphs    %s" % " ".join(n for n, _, _ in tiles))
    print("          -> %s  (%dx%d, nearest x%d)" % (p, sheet.width, sheet.height, ZOOM))


if __name__ == "__main__":
    main()
