#!/usr/bin/env python3
"""Isolate the rear port row and measure each connector.

The first pass (measure_detail.py) ran the column histogram over a 60..84 mm
window, which also caught the engraved icons printed ABOVE the connectors and
the perforated base band below. That merged neighbours into one blob and
invented features ("TB5-3", a 22 mm "USB-A1") that are not there.

This version finds the port band first (rows whose dark share spikes), then
measures columns inside that band only, and splits any run wider than the
widest real connector using the local minimum of the dark share.
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "..", "reference")


def load(p):
    return np.asarray(Image.open(p).convert("L"), dtype=np.float32)


def box_of(g, thr=238.0):
    def span(mask, axis):
        prof = mask.sum(axis=axis)
        idx = np.nonzero(prof > 0.02 * prof.max())[0]
        return int(idx[0]), int(idx[-1])
    x0, x1 = span(g < thr, 0)
    y0, y1 = span(g < 244.0, 1)
    return x0, y0, x1, y1


def runs(mask, minlen=1):
    out, s = [], None
    for i, v in enumerate(mask):
        if v and s is None:
            s = i
        elif not v and s is not None:
            if i - s >= minlen:
                out.append((s, i - 1))
            s = None
    if s is not None:
        out.append((s, len(mask) - 1))
    return out


def refine_edges(prof, a, b, floor):
    """Walk in from both ends of a run until the dark share drops to `floor`.

    The outer few columns of a connector are the bright chamfer, not the
    opening, so a bare `prof > t` threshold reports every port a pixel or two
    too wide and, worse, lets the two chamfers of a narrow gap merge.
    """
    while a < b and prof[a] < floor:
        a += 1
    while b > a and prof[b] < floor:
        b -= 1
    return a, b


def split_on_min(prof, a, b, max_w, thresh):
    """Cut an over-wide run at its darkest interior minimum, recursively."""
    if b - a + 1 <= max_w:
        return [(a, b)]
    seg = prof[a:b + 1]
    # ignore the shoulders; find the global min strictly inside
    lo, hi = 4, max(5, len(seg) - 4)
    k = int(np.argmin(seg[lo:hi])) + lo
    if seg[k] > thresh * 0.35:          # no real valley -> keep as one
        return [(a, b)]
    return split_on_min(prof, a, a + k - 1, max_w, thresh) + \
           split_on_min(prof, a + k, b, max_w, thresh)


def rear():
    p = os.path.join(REF, "apple_hw_back.jpg")
    g = load(p)
    x0, y0, x1, y1 = box_of(g)
    sx = 197.0 / (x1 - x0 + 1)
    H = y1 - y0 + 1
    print("REAR port row   scale %.4f mm/px   chassis %d x %d px" % (sx, x1 - x0 + 1, H))

    inner_x0 = x0 + int(6 / sx)
    inner_x1 = x1 - int(6 / sx)

    # 1. locate the port band: the tallest contiguous run of rows with a
    #    meaningful dark share, below the perforated field.
    dark = g < 108.0
    rowf = dark[:, inner_x0:inner_x1].mean(axis=1)
    cands = [(a, b) for a, b in runs(rowf > 0.035, 3) if b > H * 0.5]
    if not cands:
        print("no port band found")
        return
    a, b = max(cands, key=lambda t: t[1] - t[0])
    band_top_mm, band_bot_mm = a * sx, (b + 1) * sx
    print("port band rows %d..%d  ->  %.2f .. %.2f mm from chassis top"
          % (a, b, band_top_mm, band_bot_mm))
    print("                   centre %.2f mm from top = %.2f mm from bottom"
          % ((a + b) / 2.0 * sx, 95.0 - (a + b) / 2.0 * sx))

    band = dark[a:b + 1, inner_x0:inner_x1]
    colf = band.mean(axis=0)

    # 2. column features inside the band only
    feats = runs(colf > 0.55, 2)
    # 3. split anything wider than the widest real connector (the USB-A at
    #    ~12.4 mm is the widest; the cloverleaf power inlet is ~12 mm)
    MAXW = int(14.0 / sx)
    split = []
    for fa, fb in feats:
        split.extend(split_on_min(colf, fa, fb, MAXW, 1.0))

    names = ["USBC1", "USBC2", "USBC3", "USBC4", "RJ45", "PWR",
             "USBA1", "USBA2", "HDMI", "PHONE", "PWRBTN"]
    print("\n  #  name     x0(mm)   x1(mm)   w(mm)  centre(mm)   h(mm)  y0(mm)  y1(mm)")
    for i, (fa, fb) in enumerate(split):
        sub = band[:, fa:fb + 1]
        rows = np.nonzero(sub.any(axis=1))[0]
        nm = names[i] if i < len(names) else "?%d" % i
        print("  %2d %-7s %7.2f %7.2f %6.2f %9.2f %7.2f %7.2f %7.2f"
              % (i, nm, fa * sx, (fb + 1) * sx, (fb - fa + 1) * sx,
                 (fa + fb + 1) / 2.0 * sx, (rows[-1] - rows[0] + 1) * sx,
                 (a + rows[0]) * sx, (a + rows[-1] + 1) * sx))
    print("\n  gaps between centres (mm):",
          ["%.2f" % ((split[i + 1][0] + split[i + 1][1] - split[i][0] - split[i][1]) / 2.0 * sx)
           for i in range(len(split) - 1)])

    # 4. the perforated field, measured on a column that is pure field
    fx0, fx1 = inner_x0, inner_x1
    fmask = g < 130
    colband = fmask[0:int(52 / sx), fx0:fx1].mean(axis=1)
    on = np.nonzero(colband > 0.30)[0]
    if len(on):
        print("\n  field: top %.2f mm, bottom %.2f mm, height %.2f mm"
              % (on[0] * sx, (on[-1] + 1) * sx, (on[-1] - on[0] + 1) * sx))
        colf2 = fmask[on[0]:on[-1] + 1, fx0:fx1].mean(axis=0)
        fr = runs(colf2 > 0.30, 2)
        if fr:
            print("  field: left %.2f mm, right %.2f mm, width %.2f mm"
                  % (fr[0][0] * sx, (fr[-1][1] + 1) * sx, (fr[-1][1] - fr[0][0] + 1) * sx))


if __name__ == "__main__":
    rear()
