#!/usr/bin/env python3
"""Validate the x origin independently of the connectors.

Every connector number inherits the chassis-box origin, so if that origin is
off, all of them are off together and the layout still looks plausible. The
perforated field is an independent check: it is a rectangle centred on the
machine, so measuring its two edges gives both its width and - crucially - its
centre, which must land on the chassis centre. A half-millimetre there means
the origin is good to half a millimetre, whatever the connectors say.
"""
import os

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REF = os.path.join(ROOT, "reference")

FN = "apple_hw_back.jpg"
X0, WIDTH_PX = 4, 1304
SX = 197.0 / WIDTH_PX
TOP_ROW = 6
ROW_MMPP = SX


def main():
    g = np.asarray(Image.open(os.path.join(REF, FN)).convert("L"),
                   dtype=np.float32)
    h, w = g.shape

    # rows well inside the field, avoiding the rounded top/bottom corners
    y0, y1 = TOP_ROW + int(18 / ROW_MMPP), TOP_ROW + int(45 / ROW_MMPP)
    strip = g[y0:y1, :]

    # background = the bare panel brightness, sampled from the solid strip
    # between the field bottom and the port row
    s0, s1 = TOP_ROW + int(58 / ROW_MMPP), TOP_ROW + int(64 / ROW_MMPP)
    panel = float(np.median(g[s0:s1, int(w * 0.40):int(w * 0.60)]))
    thr = panel * 0.72
    print("panel median %.1f   field threshold %.1f" % (panel, thr))

    dark = strip < thr
    frac = dark.mean(axis=0)
    on = np.nonzero(frac > 0.5)[0]
    x0, x1 = int(on[0]), int(on[-1])
    cx = (x0 + x1 + 1) / 2.0
    print("field edges at image cols %d .. %d  (%.2f .. %.2f mm from chassis left)"
          % (x0, x1, (x0 - X0) * SX, (x1 + 1 - X0) * SX))
    print("field width %.2f mm   centre col %.1f = %.2f mm from chassis left"
          % ((x1 + 1 - x0) * SX, cx, (cx - X0) * SX))
    print("chassis centre should be at %.2f mm  ->  origin error %+.2f mm"
          % (98.5, (cx - X0) * SX - 98.5))

    # the field's own symmetry is a second, internal check
    left_gap = (cx - x0) * SX
    right_gap = (x1 + 1 - cx) * SX
    print("symmetry: %.2f mm left of centre, %.2f mm right -> skew %+.2f mm"
          % (left_gap, right_gap, left_gap - right_gap))

    # vertical extent on the same threshold, for completeness
    colmean = g[:, x0 + 20:x1 - 20].mean(axis=1)
    onv = np.nonzero(colmean < thr)[0]
    vt = onv[onv > TOP_ROW + 5][0] if (onv > TOP_ROW + 5).any() else None
    print("field top row %s = %.1f mm from chassis top"
          % (vt, (vt - TOP_ROW) * ROW_MMPP if vt else -1))
    # the band below the ports is the same feature seen on the front, and it is
    # also full width, so it gives the same origin check from the other end
    tail = g[int(TOP_ROW + 85 / ROW_MMPP):int(TOP_ROW + 94 / ROW_MMPP), :]
    onb = np.nonzero((tail < thr).mean(axis=0) > 0.5)[0]
    if onb.size:
        bcx = (onb[0] + onb[-1] + 1) / 2.0
        print("base band spans cols %d..%d, centre %.1f = %.2f mm from left"
              % (onb[0], onb[-1], bcx, (bcx - X0) * SX))


if __name__ == "__main__":
    main()
