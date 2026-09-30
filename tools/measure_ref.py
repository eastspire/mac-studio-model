#!/usr/bin/env python3
"""Measure the real Mac Studio from Apple's product photos, in millimetres.

Why this exists
---------------
The model was being tuned by eye against renders, which cannot resolve the
things that are actually wrong: hole pitch, grille-field extents, port widths
and their spacing. Those are all *pixel* measurements in a flat product shot,
and the chassis is a known 197 mm, so a pixel-to-mm scale follows from the
chassis bounding box alone.

Method: Apple shoots these orthographically on a white sweep, so the chassis is
a bright metal region against white. Find it by thresholding, take the largest
connected bright column/row span, and call that the chassis box. Every other
measurement is then expressed as a fraction of that box, which is immune to
whatever resolution the photo happens to be.

Usage:
    python3 measure_ref.py rear  reference/apple_hw_back.jpg
    python3 measure_ref.py front reference/apple_static_front.jpg
    python3 measure_ref.py all
"""
import sys
import os

import numpy as np
from PIL import Image

CHASSIS_MM = 197.0        # width = depth = 197 mm
HEIGHT_MM = 95.0          # incl. feet

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "..", "reference")


# --------------------------------------------------------------------- helpers
def load(path):
    im = Image.open(path).convert("L")
    return np.asarray(im, dtype=np.float32), im.size


def chassis_box(gray):
    """Bounding box of the metal chassis in a white-background product shot.

    The body is a mid-to-light grey (roughly 150-215 in these shots); the sweep
    behind it is ~250+. The lower edge is interrupted by the perforated base
    band, which reads much darker, so a pure "bright" test clips the bottom of
    the chassis. Instead take the bright mask for the horizontal extent and, for
    the vertical extent, the union of bright and "not white" -- the body plus
    its own dark grille is still far from the sweep.
    """
    bright = gray < 238.0
    notwhite = gray < 244.0

    def span(mask, axis):
        prof = mask.sum(axis=axis)
        idx = np.nonzero(prof > 0.02 * prof.max())[0]
        return (int(idx[0]), int(idx[-1])) if len(idx) else (0, mask.shape[0] - 1)

    x0, x1 = span(bright, 0)          # columns
    y0, y1 = span(notwhite, 1)        # rows
    return x0, y0, x1, y1


def col_profile(gray, box, dark=118.0):
    """Fraction of dark pixels per column inside the chassis, top to bottom."""
    x0, y0, x1, y1 = box
    sub = gray[y0:y1 + 1, x0:x1 + 1]
    return (sub < dark).mean(axis=0)


def row_profile(gray, box, dark=118.0):
    x0, y0, x1, y1 = box
    sub = gray[y0:y1 + 1, x0:x1 + 1]
    return (sub < dark).mean(axis=1)


def runs(mask):
    """[(start, end_inclusive, length), ...] for every True run."""
    out, s = [], None
    for i, v in enumerate(mask):
        if v and s is None:
            s = i
        elif not v and s is not None:
            out.append((s, i - 1, i - s))
            s = None
    if s is not None:
        out.append((s, len(mask) - 1, len(mask) - s))
    return out


def peaks(prof, thresh, min_len):
    """Runs above `thresh`, i.e. the perforated fields and the port band."""
    return [(a, b, n) for a, b, n in runs(prof > thresh) if n >= min_len]


def mm_per_px(box, axis_len_mm=CHASSIS_MM):
    x0, y0, x1, y1 = box
    return axis_len_mm / float(x1 - x0 + 1)


# ---------------------------------------------------------------------- rear
def measure_rear(path):
    gray, size = load(path)
    box = chassis_box(gray)
    x0, y0, x1, y1 = box
    h_px = y1 - y0 + 1
    sx = mm_per_px(box)
    print("=" * 72)
    print("REAR  %s  %dx%d" % (os.path.basename(path), size[0], size[1]))
    print("chassis box  x %d..%d  y %d..%d   %d x %d px" % (x0, x1, y0, y1, x1 - x0 + 1, h_px))
    print("scale        %.4f mm/px" % sx)
    # sanity: the chassis should be about 197 x 95 mm
    print("implied size %.1f x %.1f mm   (expect ~197 x ~95)"
          % ((x1 - x0 + 1) * sx, h_px * sx))

    # The rear face is only the flat part; the photo also shows the underside
    # band below it. Find the flat rear panel's vertical extent by looking for
    # the strong horizontal dark bands (grille fields + port row).
    rp = row_profile(gray, box, dark=125.0)
    bands = peaks(rp, 0.30, 3)
    print("\nrow bands (y px -> mm from chassis top):")
    for a, b, n in bands:
        print("   y %4d..%-4d  h=%-3d  %6.1f .. %6.1f mm"
              % (y0 + a, y0 + b, n, a * sx, (b + 1) * sx))

    cp = col_profile(gray, box, dark=125.0)
    cols = peaks(cp, 0.22, 3)
    print("\ncolumn features (x px -> mm from chassis left):")
    for a, b, n in cols:
        print("   x %4d..%-4d  w=%-3d  %6.1f .. %6.1f mm"
              % (x0 + a, x0 + b, n, a * sx, (b + 1) * sx))
    return gray, box, sx


# --------------------------------------------------------------------- front
def measure_front(path):
    gray, size = load(path)
    box = chassis_box(gray)
    x0, y0, x1, y1 = box
    sx = mm_per_px(box)
    print("=" * 72)
    print("FRONT  %s  %dx%d" % (os.path.basename(path), size[0], size[1]))
    print("chassis box  x %d..%d  y %d..%d   %d x %d px" % (x0, x1, y0, y1, x1 - x0 + 1, y1 - y0 + 1))
    print("scale        %.4f mm/px" % sx)
    print("implied size %.1f x %.1f mm" % ((x1 - x0 + 1) * sx, (y1 - y0 + 1) * sx))

    # ports are the only dark features on the front; isolate them by restricting
    # to the smooth front panel (exclude the base band at the bottom)
    sub = gray[y0:y1 + 1, x0:x1 + 1]
    h = sub.shape[0]
    panel = sub[: int(h * 0.88), :]
    dark = panel < 110.0
    cp = dark.mean(axis=0)
    feats = [(a, b, n) for a, b, n in runs(cp > 0.02) if n >= 2]
    print("\nfront features (x mm from chassis left, y mm from chassis top):")
    # for each column run, find its vertical extent
    for a, b, n in feats:
        colmask = dark[:, a:b + 1]
        rows = np.nonzero(colmask.any(axis=1))[0]
        print("   x %4d..%-4d w=%-3d  %6.1f .. %6.1f mm   y %6.1f .. %6.1f mm"
              % (a, b, n, a * sx, (b + 1) * sx,
                 rows[0] * sx, (rows[-1] + 1) * sx))
    return gray, box, sx


# ------------------------------------------------------------------ bottom
def measure_bottom(path):
    gray, size = load(path)
    box = chassis_box(gray)
    x0, y0, x1, y1 = box
    print("=" * 72)
    print("BOTTOM  %s  %dx%d  box x %d..%d y %d..%d"
          % (os.path.basename(path), size[0], size[1], x0, x1, y0, y1))
    return gray, box


TARGETS = {
    "rear": measure_rear,
    "front": measure_front,
    "bottom": measure_bottom,
}

DEFAULT = {
    "rear": os.path.join(REF, "apple_hw_back.jpg"),
    "front": os.path.join(REF, "apple_static_front.jpg"),
    "bottom": os.path.join(REF, "apple_foot.jpg"),
}


def main():
    args = sys.argv[1:]
    if not args or args[0] not in TARGETS and args[0] != "all":
        print(__doc__)
        print("targets:", ", ".join(sorted(TARGETS)))
        return 1
    if args[0] == "all":
        for k in DEFAULT:
            p = DEFAULT[k]
            if os.path.exists(p):
                TARGETS[k](p)
            else:
                print("skip %s (missing %s)" % (k, p))
        return 0
    kind = args[0]
    p = args[1] if len(args) > 1 else DEFAULT[kind]
    TARGETS[kind](p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
