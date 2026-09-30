#usr/bin/env python3
"""Apple's own cutaway renders, on a millimetre grid anchored to the chassis.

The exterior was measured off flat product photography, where the chassis box
is unambiguous. These are X-ray views: semi-transparent, on a grey field, with
the case itself barely visible. The same anchor still works - the case outline
runs the full width of the frame - so the box is taken from the strongest
vertical edges and the height follows from 197:95, exactly as everywhere else.

The grid exists so the layers can be read off rather than guessed: the blower
block, the finned heatsink, the copper pipe plane, the board and the supply.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
REF = os.path.join(ROOT, "reference", "hk")
OUT = os.path.join(ROOT, "renders", "compare")

W_MM, H_MM = 197.0, 95.0
ZOOM = 2

SHOTS = [
    "hw_elements_fans_xray.jpg",
    "hw_elements_case_xray.jpg",
    "hw_elements_foot_xray.jpg",
    "hw_elements_chip_xray.jpg",
]


def chassis_box(g):
    """The case silhouette, as a bounding box in pixels.

    Two rules, and the second is the one that matters here. The LEFT and RIGHT
    edges come from the vertical silhouette and are reliable: the case is the
    only thing spanning the frame. The TOP does not come from a threshold on
    its own. In hw_elements_fans_xray.jpg a threshold puts the top at row 31
    and in hw_elements_case_xray.jpg at row 55, for the same case in the same
    pose, because the second image opens with a black slab that reads as
    background. So the height is DERIVED from the width at 197:95, as
    everywhere else in this project, and anchored on the BOTTOM edge, which
    both images agree on. Whatever that leaves at the top is reported as a
    residual rather than quietly trimmed.
    """
    col = g.mean(axis=0)
    row = g.mean(axis=1)
    lo, hi = np.percentile(col, 5), np.percentile(col, 95)
    dark = col < lo + 0.30 * (hi - lo)
    runs, start = [], None
    for i, v in enumerate(dark):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start > 20:
                runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(dark) - 1))
    if not runs:
        raise SystemExit("no case edges found")
    x0, x1 = runs[0][0], runs[-1][1]
    bot = len(row) - 1 - int(np.argmax(row[::-1] < lo + 0.25 * (hi - lo)))
    w = x1 - x0 + 1
    h = int(round(w * H_MM / W_MM))
    return x0, bot - h + 1, x1, bot, h


def main():
    for name in (sys.argv[1:] or SHOTS):
        path = os.path.join(REF, name)
        im = Image.open(path).convert("RGB")
        g = np.asarray(im.convert("L"), dtype=np.float64) / 255.0
        x0, y0, x1, y1, h = chassis_box(g)
        w = x1 - x0 + 1
        # how much of the detected silhouette is left above the derived top
        rlo, rhi = np.percentile(g.mean(axis=1), 5), np.percentile(g.mean(axis=1), 95)
        darkrow = g.mean(axis=1) < rlo + 0.25 * (rhi - rlo)
        top_det = int(np.argmax(darkrow))
        print("%-32s image %-12s box=(%d,%d,%d,%d) %d px = %.3f mm/px"
              % (name, "%dx%d" % im.size, x0, y0, x1, y1, w, W_MM / w))
        print("   %-28s derived top row %d, silhouette starts at %d "
              "(%.1f mm of headroom trimmed)"
              % ("", y0, top_det, (y0 - top_det) * W_MM / w))

        crop = im.crop((x0, y0, x0 + w, y0 + h))
        cw, ch = crop.width * ZOOM, crop.height * ZOOM
        big = crop.resize((cw, ch), Image.LANCZOS)
        d = ImageDraw.Draw(big)
        mm_per_px = W_MM / w
        for k in range(0, 101, 5):
            x = int(round(k * mm_per_px * ZOOM))
            col = (220, 40, 40) if k in (0, 50, 100) else (110, 165, 255)
            d.line([(x, 0), (x, ch)], fill=col, width=1)
            if k % 10 == 0:
                d.text((x + 2, 2), "%d" % k, fill=col)
        for k in range(0, 100, 5):
            y = int(round(k * mm_per_px * ZOOM))
            col = (220, 40, 40) if k in (0, 50, 95) else (110, 165, 255)
            d.line([(0, y), (cw, y)], fill=col, width=1)
            d.text((2, y + 2), "%d" % k, fill=col)
        p = os.path.join(OUT, "xray_%s" % name.replace(".jpg", ".png"))
        big.save(p)
        print("   ticks are mm from the top-left of the case; -> %s" % p)


if __name__ == "__main__":
    main()
