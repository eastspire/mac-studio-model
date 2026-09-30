#!/usr/bin/env python3
"""Measure the base band's BRIGHT web, which has no shadow ambiguity.

Hole size in a photograph is ambiguous: the dark region around an opening is
the opening plus the shadow the 1.3 mm recess throws around it, so "how wide is
the hole" depends on where the threshold is put, and a model with hard edges
and a photograph with soft ones do not share a bias. Two earlier attempts gave
two answers for the same hole.

The web between holes is metal catching the light, not a shadow, so its width
is a far more stable thing to measure. With the pitch known from the
autocorrelation, the hole width follows as pitch minus web, and the vertical
web is the same story. Both images are measured with the same rule at the
photograph's own resolution.
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from compare_render import otsu, autocorr_peak, OUT  # noqa: E402
from verify_spec import load  # noqa: E402

W_MM, H_MM = 197.0, 95.0


def runs(mask, axis):
    out = []
    arr = mask if axis == 1 else mask.T
    for line in arr:
        d = np.diff(np.concatenate(([0], line.view(np.int8), [0])))
        s_, e_ = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
        out.extend((e_ - s_).tolist())
    return np.array(out) if out else np.array([0])


def report(g, sx, label, lo=88.5, hi=93.5, x_lo=40.0, x_hi=160.0):
    h, w = g.shape
    a = int(round(lo / sx))
    b = min(h, int(round(hi / sx)))
    p = int(round(x_lo / sx))
    q = min(w, int(round(x_hi / sx)))
    blk = g[a:b, p:q]
    t, _ = otsu(blk)
    dark = blk < t
    bright = ~dark
    dx = runs(bright, 1)
    dz = runs(bright, 0)
    print("\n%s  %d x %d px at %.5f mm/px, otsu %.3f"
          % (label, blk.shape[1], blk.shape[0], sx, t))
    print("   bright web   x median %.2f px = %.3f mm  (n=%d, p25 %.2f p75 %.2f)"
          % (np.median(dx), np.median(dx) * sx, len(dx),
             np.percentile(dx, 25), np.percentile(dx, 75)))
    print("   bright web   z median %.2f px = %.3f mm  (n=%d, p25 %.2f p75 %.2f)"
          % (np.median(dz), np.median(dz) * sx, len(dz),
             np.percentile(dz, 25), np.percentile(dz, 75)))
    hx = runs(dark, 1)
    hz = runs(dark, 0)
    print("   dark  hole   x median %.2f px = %.3f mm"
          % (np.median(hx), np.median(hx) * sx))
    print("   dark  hole   z median %.2f px = %.3f mm"
          % (np.median(hz), np.median(hz) * sx))
    px_ = autocorr_peak(dark, axis=1) * sx
    pz_ = autocorr_peak(dark.mean(axis=1), axis=0) * sx
    print("   pitch x %.3f mm, z %.3f mm" % (px_, pz_))
    print("   => web + hole across: %.3f + %.3f = %.3f mm (pitch %.3f)"
          % (np.median(dx) * sx, np.median(hx) * sx,
             (np.median(dx) + np.median(hx)) * sx, px_))
    return np.median(dx) * sx, np.median(dz) * sx


def main():
    s = load("rear")
    gr = s["g"].astype(np.float64) / 255.0
    sx = s["sx"]
    w = s["width_px"]
    h = int(round(w * H_MM / W_MM))
    im = Image.open(os.path.join(OUT, "rear_model.png")).convert("L")
    gm = np.asarray(im.resize((w, h), Image.LANCZOS), dtype=np.float64) / 255.0

    rx, rz = report(gr, sx, "APPLE  rear")
    mx, mz = report(gm, sx, "MODEL  rear")
    print("\ndifference in web width: %.3f mm across, %.3f mm up"
          % (rx - mx, rz - mz))


if __name__ == "__main__":
    main()
