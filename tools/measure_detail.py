#!/usr/bin/env python3
"""Precise sub-feature measurement of the Apple reference photos.

`measure_ref.py` finds the chassis and the gross bands. This one drills into
each feature and reports it in millimetres, which is the only form the model can
be parameterised from:

  * the perforated field's true top/bottom edge and hole pitch (autocorrelated,
    not guessed from a row histogram)
  * each rear connector's centre, width and height
  * the front connector row
  * the corner radius, from the curvature of the silhouette

Usage: python3 measure_detail.py rear|front|corner
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "..", "reference")


def load(p):
    return np.asarray(Image.open(p).convert("L"), dtype=np.float32)


def box_of(gray, thr=238.0):
    bright = gray < thr
    notwhite = gray < 244.0

    def span(mask, axis):
        prof = mask.sum(axis=axis)
        idx = np.nonzero(prof > 0.02 * prof.max())[0]
        return int(idx[0]), int(idx[-1])
    x0, x1 = span(bright, 0)
    y0, y1 = span(notwhite, 1)
    return x0, y0, x1, y1


def autocorr_pitch(sig, lo=3, hi=60):
    """Dominant period in a 1-D signal, by autocorrelation of its mean-removed copy."""
    s = sig - sig.mean()
    ac = np.correlate(s, s, mode="full")[len(s) - 1:]
    ac /= (ac[0] or 1.0)
    seg = ac[lo:hi]
    if not len(seg):
        return None
    k = int(np.argmax(seg)) + lo
    return k


def runs(mask, minlen=1):
    out, s = [], None
    for i, v in enumerate(mask):
        if v and s is None:
            s = i
        elif not v and s is not None:
            if i - s >= minlen:
                out.append((s, i - 1))
            s = None
    if s is not None and len(mask) - s >= minlen:
        out.append((s, len(mask) - 1))
    return out


# --------------------------------------------------------------------- rear
def rear():
    p = os.path.join(REF, "apple_hw_back.jpg")
    g = load(p)
    x0, y0, x1, y1 = box_of(g)
    sx = 197.0 / (x1 - x0 + 1)
    print("REAR detail  scale %.4f mm/px   chassis %dx%d px" % (sx, x1 - x0 + 1, y1 - y0 + 1))

    # Isolate the perforated field: it is a dense dark texture in a big
    # rectangle. Restrict to the flat rear panel (inset from the silhouette so
    # the rounded corners and the bottom band do not pollute the histogram).
    fx0, fx1 = x0 + int(4 / sx), x1 - int(4 / sx)
    fy0, fy1 = y0, y0 + int(56 / sx)
    field = g[fy0:fy1, fx0:fx1]

    rowfrac = (field < 120).mean(axis=1)
    on = rowfrac > 0.25
    rr = runs(on, 2)
    if rr:
        a, b = rr[0]
        # refine with the raw threshold, not the coarse 0.25 gate
        raw = (g[fy0:fy1, fx0:fx1] < 150).mean(axis=1)
        idx = np.nonzero(raw > 0.15)[0]
        top_mm = (fy0 + idx[0] - y0) * sx
        bot_mm = (fy0 + idx[-1] - y0) * sx
        print("\nperforated field (rear):")
        print("   top    %6.2f mm from chassis top" % top_mm)
        print("   bottom %6.2f mm" % bot_mm)
        print("   height %6.2f mm   (%.1f%% of the 95 mm body)"
              % (bot_mm - top_mm, 100 * (bot_mm - top_mm) / 95.0))

        # hole pitch: take a horizontal scanline through the middle of the field
        mid = fy0 + (idx[0] + idx[-1]) // 2
        line = g[mid, fx0:fx1]
        kx = autocorr_pitch((line < 150).astype(np.float32), lo=3, hi=70)
        colline = g[fy0:fy1, fx0 + (fx1 - fx0) // 2]
        ky = autocorr_pitch((colline < 150).astype(np.float32), lo=3, hi=70)
        print("   hole pitch  x %.2f mm (period %d px)   y %.2f mm (period %d px)"
              % (kx * sx, kx or 0, ky * sx, ky or 0))
        print("   holes across %d  x  down %d"
              % (round((fx1 - fx0) / (kx or 1)), round((idx[-1] - idx[0]) / (ky or 1))))

        # field horizontal extent
        colfrac = (g[idx[0] + fy0 - fy0: idx[-1] + fy0 - fy0, fx0:fx1] < 120).mean(axis=0)
        cr = runs(colfrac > 0.25, 2)
        if cr:
            print("   left  %6.2f mm   right %6.2f mm   width %6.2f mm"
                  % (cr[0][0] * sx, (cr[-1][1] + 1) * sx, (cr[-1][1] - cr[0][0] + 1) * sx))

    # port row: find it between the field bottom and the bottom band
    prow0 = y0 + int(60 / sx)
    prow1 = y0 + int(84 / sx)
    band = g[prow0:prow1, fx0:fx1]
    dark = band < 105
    colf = dark.mean(axis=0)
    print("\nrear port row (y window %0.1f..%0.1f mm):" % (60, 84))
    names = ["TB5-1", "TB5-2", "TB5-3", "TB5-4", "RJ45", "PWR", "USB-A1", "USB-A2",
             "HDMI", "PHONES", "TOUCHID"]
    feats = runs(colf > 0.05, 2)
    for i, (a, b) in enumerate(feats):
        sub = dark[:, a:b + 1]
        rows = np.nonzero(sub.any(axis=1))[0]
        nm = names[i] if i < len(names) else "?"
        print("   %-8s x %6.2f .. %6.2f  (w %5.2f)  centre %6.2f   y %5.1f .. %5.1f"
              % (nm, a * sx, (b + 1) * sx, (b - a + 1) * sx, (a + b + 1) / 2.0 * sx,
                 (prow0 + rows[0] - y0) * sx, (prow0 + rows[-1] - y0) * sx))


# -------------------------------------------------------------------- front
def front():
    p = os.path.join(REF, "apple_static_front.jpg")
    g = load(p)
    x0, y0, x1, y1 = box_of(g)
    sx = 197.0 / (x1 - x0 + 1)
    print("\nFRONT detail  scale %.4f mm/px" % sx)
    h = y1 - y0 + 1
    sub = g[y0:y0 + int(h * 0.9), x0:x1 + 1]
    dark = sub < 105
    colf = dark.mean(axis=0)
    names = ["USB-C1", "USB-C2", "SDXC"]
    print("front ports:")
    for i, (a, b) in enumerate(runs(colf > 0.04, 2)):
        d = dark[:, a:b + 1]
        rows = np.nonzero(d.any(axis=1))[0]
        nm = names[i] if i < len(names) else "?"
        print("   %-8s x %6.2f .. %6.2f  (w %5.2f)  centre %6.2f   y %5.2f .. %5.2f  (h %4.2f)"
              % (nm, a * sx, (b + 1) * sx, (b - a + 1) * sx, (a + b + 1) / 2.0 * sx,
                 rows[0] * sx, (rows[-1] + 1) * sx, (rows[-1] - rows[0] + 1) * sx))
    # status LED: small, faint, low and to the right
    right = dark[:, int(0.60 * dark.shape[1]):]
    rf = right.mean(axis=0)
    for a, b in runs(rf > 0.02, 1):
        d = right[:, a:b + 1]
        rows = np.nonzero(d.any(axis=1))[0]
        off = int(0.60 * dark.shape[1]) + a
        print("   LED      x %6.2f .. %6.2f  centre %6.2f   y %5.2f .. %5.2f"
              % (off * sx, (off + b - a + 1) * sx, (off + (b - a) / 2.0) * sx,
                 rows[0] * sx, (rows[-1] + 1) * sx))


# ------------------------------------------------------------------- corner
def corner():
    """Vertical corner radius, from where the silhouette starts to turn."""
    p = os.path.join(REF, "apple_static_front.jpg")
    g = load(p)
    x0, y0, x1, y1 = box_of(g)
    h = y1 - y0 + 1
    w = x1 - x0 + 1
    # A circle of radius r tangent to the left edge and to the straight top
    # edge: at the top row the silhouette is inset by r - sqrt(r^2 - (r-dy)^2).
    # Fit r by matching the measured inset profile on the top-left corner.
    mid = y0 + int(h * 0.5)          # a row well below the top fillet: straight
    print("CORNER detail")
    # top fillet: per-row horizontal inset of the bright body
    for r in range(0, int(h * 0.16)):
        row = g[y0 + r, x0:x1 + 1]
        bright = np.nonzero(row < 238)[0]
        if not len(bright):
            continue
        inset = bright[0]
        print("   row %2d  inset %3d px" % (r, inset), end="\r")
    print()

    # Fit: assume a circular fillet of radius R (in px) at the top edge.
    # The silhouette x(r) = R - sqrt(R^2 - (R - r)^2) for r < R.
    xs = []
    for r in range(0, min(int(h * 0.2), 80)):
        row = g[y0 + r, x0:x1 + 1]
        bright = np.nonzero(row < 240)[0]
        if len(bright):
            xs.append((r, int(bright[0])))
    best = None
    for R2 in range(4, 90):
        err = 0.0
        for r, xin in xs:
            if r < R2:
                pred = R2 - np.sqrt(max(0.0, R2 * R2 - (R2 - r) ** 2))
            else:
                pred = 0.0
            err += (pred - xin) ** 2
        if best is None or err < best[1]:
            best = (R2, err)
    print("   fitted top/bottom edge fillet radius ~ %d px" % best[0])
    print("   (residual %.1f, %d sample rows)" % (best[1], len(xs)))


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "rear"
    if what in ("rear", "all"):
        rear()
    if what in ("front", "all"):
        front()
    if what in ("corner", "all"):
        corner()
