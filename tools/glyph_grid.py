#usr/bin/env python3
"""The five engraved glyphs at 20x, on a millimetre grid, straight from the photo.

Threshold statistics said the Ethernet mark was 1.66 mm across; the picture says
3.69 mm, because its strokes are faint enough that any cut bright enough to
survive JPEG ringing also clips the arms. So the geometry is read off the image
against a grid rather than off a mask, and the grid is the crop's own scale:
0.15096 mm/px on the rear photo, one minor tick every 0.5 mm.

Nothing here is fitted. This is the measuring instrument; the polygons that go
into the model are drawn to match what this shows and then checked back against
it by tools/glyph_sheet.py.
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
from verify_spec import load     # noqa: E402

OUT = os.path.join(ROOT, "renders", "compare")
W_MM, H_MM = 197.0, 95.0
ZOOM = 20
HALF_MM = 3.0                    # crop half-width -> a 6.0 mm window

GLYPHS = [
    ("thunderbolt", "ICON_TB_X"),
    ("ethernet", "ICON_ETH_X"),
    ("usb", "ICON_USB_X"),
    ("hdmi", "ICON_HDMI_X"),
    ("headphone", "ICON_HP_X"),
]


def stretch(a, lo_p=0.5, hi_p=99.5):
    lo, hi = np.percentile(a, lo_p), np.percentile(a, hi_p)
    if hi - lo < 1e-6:
        return np.zeros_like(a)
    return np.clip((a - lo) / (hi - lo), 0.0, 1.0)


def one(name, attr, g, sx, x0, y0, width_px):
    cx_mm = 98.5 - getattr(S, attr) * 10
    cy_mm = H_MM - S.ICON_Z * 10
    ix0 = max(x0, x0 + int(round((cx_mm - HALF_MM) / sx)))
    ix1 = min(x0 + width_px - 1, x0 + int(round((cx_mm + HALF_MM) / sx)))
    iy0 = y0 + int(round((cy_mm - HALF_MM) / sx))
    iy1 = y0 + int(round((cy_mm + HALF_MM) / sx))
    patch = stretch(g[iy0:iy1 + 1, ix0:ix1 + 1])

    im = Image.fromarray((patch * 255).astype(np.uint8)).convert("RGB")
    w, h = im.width * ZOOM, im.height * ZOOM
    im = im.resize((w, h), Image.LANCZOS)
    d = ImageDraw.Draw(im)

    # 0.5 mm grid; the crop is HALF_MM each way, so ticks land on halves.
    n = int(round(HALF_MM / 0.5))
    for k in range(-n, n + 1):
        x = int(round((HALF_MM + k * 0.5) / sx * ZOOM))
        col = (200, 40, 40) if k == 0 else (120, 170, 255)
        d.line([(x, 0), (x, h)], fill=col, width=2 if k == 0 else 1)
        d.text((x + 3, 3), "%+.1f" % (k * 0.5), fill=col)
    for k in range(-n, n + 1):
        y = int(round((HALF_MM + k * 0.5) / sx * ZOOM))
        col = (200, 40, 40) if k == 0 else (120, 170, 255)
        d.line([(0, y), (w, y)], fill=col, width=2 if k == 0 else 1)
        d.text((3, y + 3), "%+.1f" % (-k * 0.5), fill=col)

    p = os.path.join(OUT, "grid_%s.png" % name)
    im.save(p)
    return p, w, h


def main():
    only = sys.argv[1:] or [g[0] for g in GLYPHS]
    s = load("rear")
    g, sx, x0, y0, width_px = s["g"], s["sx"], s["x0"], s["y0"], s["width_px"]
    print("rear %.5f mm/px, window +/-%.1f mm about (spec x, ICON_Z)" % (sx, HALF_MM))
    print("x ticks run right-to-left, because a rear view mirrors the model.\n")
    for name, attr in GLYPHS:
        if name not in only:
            continue
        p, w, h = one(name, attr, g, sx, x0, y0, width_px)
        print("%-13s %s  %dx%d" % (name, p, w, h))


if __name__ == "__main__":
    main()
