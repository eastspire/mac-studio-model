#!/usr/bin/env python3
"""Measure vertical feature boundaries in the Apple photos, in millimetres.

Two things this gets right that a naive profile does not:

* the scale comes from the chassis WIDTH (197 mm across N pixels), not from the
  height — deriving mm/px from the height assumes the aspect ratio is already
  known, which is the thing being measured;
* the chassis top and bottom are found from the strongest horizontal gradient
  near each end, not from "first row that is not white". The bottom of a
  product shot is a soft contact shadow, and a brightness cut swallows it and
  then reports a base band several millimetres taller than the real part.
"""
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REF = os.path.join(ROOT, "reference")

# name -> (file, chassis pixel width, solid-panel row range as a fraction of the
#          chassis height, measured from the top)
SHOTS = {
    "front": ("apple_static_front.jpg", 1393, (0.20, 0.45)),
    "rear": ("apple_hw_back.jpg", 1306, (0.60, 0.66)),
}
WIDTH_MM = 197.0
HEIGHT_MM = 95.0


def load(name):
    fn, wpx, solid = SHOTS[name]
    g = np.asarray(Image.open(os.path.join(REF, fn)).convert("L"),
                   dtype=np.float32) / 255.0
    return fn, g, WIDTH_MM / wpx, solid


def edges(g, mmpp):
    """Chassis top and bottom file rows, from the strongest gradients."""
    h, w = g.shape
    prof = g[:, int(w * 0.35):int(w * 0.65)].mean(axis=1)
    d = np.gradient(prof)
    top = int(np.argmax(d[: h // 3]))                  # bright ground -> body
    bot = int(np.argmin(d[-h // 3:]) + h - h // 3)     # body -> shadow/ground
    return top, bot, prof


def report(name):
    fn, g, mmpp, solid = load(name)
    top, bot, prof = edges(g, mmpp)
    hpx = bot - top
    print("\n== %s  %s   %.5f mm/px" % (name, fn, mmpp))
    print("   chassis file rows %d..%d  = %d px = %.1f mm (expect %.0f)"
          % (top, bot, hpx, hpx * mmpp, HEIGHT_MM))
    print("   edge sharpness: top %+.3f  bottom %+.3f" % (np.gradient(prof)[top],
                                                         np.gradient(prof)[bot]))
    a, b = solid
    panel = float(np.median(prof[top + int(a * hpx):top + int(b * hpx)]))
    print("   solid panel median %.3f" % panel)

    body = prof[top:bot + 1]
    thr = panel * 0.88
    print("   thr %.3f" % thr)
    for pct in (100, 97, 94, 91, 88, 85, 82, 79, 76, 73, 70, 66, 62, 58, 54, 50):
        i = int(round(pct / 100.0 * hpx))
        y = top + min(i, hpx)
        mark = "  <-- band" if body[min(i, hpx - 1)] < thr else ""
        print("     %5.1f%%  %6.1f mm from top  %5.1f mm from bottom  %.3f%s"
              % (pct, i * mmpp, (hpx - i) * mmpp, body[min(i, hpx - 1)], mark))

    lo = int(hpx * 0.70)
    dark = np.nonzero(body[lo:] < thr)[0]
    if dark.size:
        i0 = dark[0] + lo
        j = i0
        while j + 1 < hpx and body[j + 1] < thr:
            j += 1
        print("   BAND %.1f .. %.1f mm from top   ->  z %.2f .. %.2f cm"
              % (i0 * mmpp, j * mmpp, (HEIGHT_MM - j * mmpp) / 10.0,
                 (HEIGHT_MM - i0 * mmpp) / 10.0))
        print("        height %.1f mm,  %.1f mm above the foot plane"
              % ((j - i0) * mmpp, (hpx - j) * mmpp))


if __name__ == "__main__":
    for n in (sys.argv[1:] or ["front", "rear"]):
        report(n)
