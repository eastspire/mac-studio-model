#!/usr/bin/env python3
"""Gate on the render's framing before anyone reads a number off it.

A beauty render is not a measuring instrument. Auto-framing that fits a
bounding SPHERE rather than the object produced a rear view whose object ran
off the right edge and read 1.52 aspect against the true 2.07 - and a band
table computed off it looked like a catastrophic model failure when the model
was fine and the camera was wrong.

Two assertions, both cheap:
  * the chassis aspect, which is the canary for every other measurement;
  * the margin, which must be positive on all four sides (nothing touching
    the edge) and not absurd (the object must fill a useful share of frame).
"""
import os
import sys
from typing import NamedTuple

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
RENDERS = os.path.join(ROOT, "renders")
W_MM, H_MM = 197.0, 95.0
WANT_ASPECT = W_MM / H_MM
TOL_ASPECT = 0.06          # dead-level elevations only; 3/4 views differ
MIN_MARGIN = 0.004         # fraction of frame; must be > 0
MAX_MARGIN = 0.30          # object should not be a speck
# Views that are deliberately framed off-centre or macro, so their aspect is
# not the chassis aspect and the canary does not apply.
NOT_ELEVATION = {"04_hero", "05_top", "06_bottom", "09_grille_band",
                 "10_grille_macro", "11_grille_front"}


class Box(NamedTuple):
    x0: int
    x1: int
    y0: int
    y1: int
    fw: int
    fh: int


def object_box(path):
    a = np.asarray(Image.open(path).convert("L"), dtype=np.float64) / 255.0
    border = np.concatenate([a[0, :], a[-1, :], a[:, 0], a[:, -1]])
    bg = float(np.median(border))
    mask = np.abs(a - bg) > 0.02
    if not mask.any():
        return None
    ys, xs = np.nonzero(mask)
    fh, fw = a.shape
    return Box(int(xs[0]), int(xs[-1]), int(ys[0]), int(ys[-1]), fw, fh)


def main():
    names = sys.argv[1:] or sorted(
        f[:-4] for f in os.listdir(RENDERS) if f.endswith(".png"))
    bad = 0
    print("%-18s %-12s %8s %8s %8s %s"
          % ("view", "aspect", "want", "delta", "margin", "verdict"))
    for n in names:
        p = os.path.join(RENDERS, n + ".png")
        if not os.path.exists(p):
            continue
        b = object_box(p)
        if b is None:
            print("%-18s EMPTY FRAME" % n)
            bad += 1
            continue
        w = b.x1 - b.x0 + 1
        h = b.y1 - b.y0 + 1
        aspect = w / float(h)
        fw, fh = b.fw, b.fh
        margin = min(b.x0, b.y0, fw - 1 - b.x1, fh - 1 - b.y1) / float(fw)
        touches = b.x0 <= 0 or b.y0 <= 0 or b.x1 >= fw - 1 or b.y1 >= fh - 1
        if n in NOT_ELEVATION:
            ok = margin >= MIN_MARGIN and margin <= MAX_MARGIN
            print("%-18s %-12s %8s %8s %7.1f%% %s"
                  % (n, "n/a", "-", "-", margin * 100,
                     "ok" if ok else "FAIL (framing)"))
        else:
            ok = (abs(aspect - WANT_ASPECT) <= TOL_ASPECT
                  and not touches and margin <= MAX_MARGIN)
            print("%-18s %-12s %8.3f %+8.3f %7.1f%% %s"
                  % (n, "%.3f" % aspect, WANT_ASPECT, aspect - WANT_ASPECT,
                     margin * 100,
                     "ok" if ok else ("FAIL (clipped)" if touches
                                     else "FAIL (aspect/framing)")))
        bad += 0 if ok else 1
    print("\n%s" % ("FRAMING OK" if bad == 0 else "FRAMING FAILED on %d view(s)" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
