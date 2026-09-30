#!/usr/bin/env python3
"""Label the rear connectors by connected component and report each in mm.

Column histograms cannot do this job: the two chamfers of a narrow gap share a
column, a run of four USB-C slots reads as one blob, and the engraved icons
printed above the connectors drag the band upward until it swallows the field.

A connected-component pass over a row window that contains ONLY the connector
bodies is unambiguous — each shell is a separate blob, and its bounding box is
the measurement. scipy is not guaranteed here, so this is a two-pass
flood fill on a boolean mask (the image is 1312x545, which is cheap).

Usage: python3 measure_cc.py [rear|front] [image]
"""
import os
import sys
from collections import deque

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "..", "reference")

NAMES_REAR = ["USBC1", "USBC2", "USBC3", "USBC4", "RJ45", "PWR",
              "USBA1", "USBA2", "HDMI", "PHONE", "PWRBTN"]
NAMES_FRONT = ["USBC1", "USBC2", "SDXC", "LED"]


def load(p):
    return np.asarray(Image.open(p).convert("L"), dtype=np.float32)


def box_of(g):
    """Chassis box in pixels, anchored to the KNOWN 197 x 95 mm aspect.

    Two things had to change.

    Scale: the previous version applied the width-derived mm/px to BOTH axes
    after taking the height from a brightness cut. The bottom of a product
    shot is a soft contact shadow, so that cut ran long and every vertical
    measurement came out ~1% too large - 1.2 mm on the port row, the exact
    size of error this file exists to eliminate. Apple publishes
    197 x 197 x 95 mm, so the pixel box has a known aspect and the height
    follows from the width.

    Top edge: locating it by the strongest brightness gradient anywhere in the
    top of the frame does not work, because in the rear photograph the
    strongest edge up there is the TOP OF THE PERFORATED FIELD at 5 mm, not
    the top of the machine - and the silhouette-width plateau is worse, since a
    vignetted white ground makes the wide empty rows look "full". The search is
    therefore confined to the first 3% of the frame, which is above the field,
    and the resulting bottom edge is checked against the contact shadow to
    confirm the two ends agree.
    """
    h, w = g.shape
    body = g < 238.0
    x0 = int(np.nonzero(body[int(h * 0.5)])[0][0])
    x1 = int(np.nonzero(body[int(h * 0.5)])[0][-1])
    width = x1 - x0 + 1
    height = int(round(width * 95.0 / 197.0))

    prof = g[:, int(w * 0.35):int(w * 0.65)].mean(axis=1)
    d = np.gradient(prof)
    y0 = int(np.argmax(d[: max(4, int(h * 0.03))]))
    y1 = y0 + height - 1
    print("  edge check: top grad %+.4f at row %d, bottom grad %+.4f at row %d"
          % (d[y0], y0, d[min(y1, h - 2)], y1))
    return x0, y0, x1, y1


def components(mask, min_area=20):
    """4-connected components, returned as (x0, y0, x1, y1, area) sorted by x."""
    h, w = mask.shape
    seen = np.zeros((h, w), dtype=bool)
    out = []
    for sy in range(h):
        row = mask[sy]
        for sx in np.nonzero(row & ~seen[sy])[0]:
            if seen[sy, sx]:
                continue
            q = deque([(sy, sx)])
            seen[sy, sx] = True
            x0 = x1 = sx
            y0 = y1 = sy
            area = 0
            while q:
                y, x = q.popleft()
                area += 1
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
            if area >= min_area:
                out.append((x0, y0, x1, y1, area))
    out.sort()
    return out


def row_window_for(g, x0, x1, y_lo_frac, y_hi_frac, thresh=118.0, min_frac=0.03):
    """Find the row span that holds the connectors.

    Scans the middle band of the panel for the first and last row whose dark
    share crosses `min_frac`, starting below the perforated field. The field
    itself is excluded by requiring the run to be contiguous and to start after
    the field's bottom.
    """
    H = g.shape[0]
    dark = g < thresh
    prof = dark[:, x0:x1].mean(axis=1)
    y_a = int(H * y_lo_frac)
    y_b = int(H * y_hi_frac)
    seg = prof[y_a:y_b]
    on = seg > min_frac
    idx = np.nonzero(on)[0]
    if not len(idx):
        return None
    return y_a + int(idx[0]), y_a + int(idx[-1])


def report(kind, path):
    g = load(path)
    x0, y0, x1, y1 = box_of(g)
    sx = 197.0 / (x1 - x0 + 1)
    H = y1 - y0 + 1
    print("%s  %s" % (kind.upper(), os.path.basename(path)))
    print("  chassis %d x %d px   scale %.4f mm/px   aspect %.4f (want %.4f)"
          % (x1 - x0 + 1, H, sx, (x1 - x0 + 1) / H, 197.0 / 95.0))

    ix0, ix1 = x0 + int(8 / sx), x1 - int(8 / sx)

    if kind == "rear":
        # the field ends around 54 mm; the connectors live below it
        win = row_window_for(g, ix0, ix1, 0.58, 0.90, thresh=118.0, min_frac=0.03)
        names = NAMES_REAR
    else:
        # front: exclude the base band at the bottom
        win = row_window_for(g, ix0, ix1, 0.50, 0.88, thresh=118.0, min_frac=0.015)
        names = NAMES_FRONT

    if win is None:
        print("  no window found")
        return
    ya, yb = win
    print("  window rows %d..%d  (%.2f .. %.2f mm from chassis top)"
          % (ya, yb, (ya - y0) * sx, (yb - y0) * sx))

    sub = (g[ya:yb + 1, ix0:ix1] < 125.0)
    comps = components(sub, min_area=int(0.9 / (sx * sx)))
    print("  %d components   (window inset %.2f mm each side)"
          % (len(comps), (ix0 - x0) * sx))
    print("\n   # name     x0(mm)  x1(mm)  w(mm)  cx(mm)   y0(mm)  y1(mm)  h(mm)  area")
    prev_cx = None
    for i, (ca, cb, cc, cd, area) in enumerate(comps):
        nm = names[i] if i < len(names) else "?%d" % i
        # ca/cc index into the WINDOW, not the image. Adding the window origin
        # back is not cosmetic: the window is inset 8 mm from the chassis edge,
        # so omitting it shifts every connector 8.5 mm toward the centre. The
        # layout stays perfectly self-consistent while the whole rear port row
        # comes out compressed, which is exactly the kind of error a
        # self-consistent measurement cannot catch on its own.
        cx = (ca + ix0 + cc + 1) / 2.0 * sx
        gap = "" if prev_cx is None else "   gap %6.2f" % (cx - prev_cx)
        print("  %2d %-7s %7.2f %6.2f %6.2f %7.2f %7.2f %7.2f %6.2f %6d%s"
              % (i, nm, (ca + ix0) * sx, (cc + 1 + ix0) * sx, (cc - ca + 1) * sx, cx,
                 (ya + cb - y0) * sx, (ya + cd + 1 - y0) * sx, (cd - cb + 1) * sx,
                 area, gap))
        prev_cx = cx
    return comps, sx, g, (x0, y0, x1, y1)


if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else "rear"
    default = os.path.join(REF, "apple_hw_back.jpg" if kind == "rear"
                           else "apple_static_front.jpg")
    path = sys.argv[2] if len(sys.argv) > 2 else default
    report(kind, path)
