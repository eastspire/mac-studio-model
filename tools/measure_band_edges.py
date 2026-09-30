#!/usr/bin/env python3
"""Measure the base band's top edge, bottom edge and horizontal run.

The band is not a rectangle: its top edge is straight, its lower edge follows
the chassis corner radius, and at each end it curves back up to meet the top.
A single top/bottom pair would average that curvature away, so this reports the
per-column edges and then the straight part separately from the two rounded
ends, which is the form the model actually has to reproduce.
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))

import mac_studio_spec as S      # noqa: E402
from compare_render import otsu, largest_blob_fraction  # noqa: E402
from verify_spec import load    # noqa: E402

W_MM, H_MM = 197.0, 95.0


def main():
    s = load("rear")
    g, sx, x0, y0 = s["g"], s["sx"], s["x0"], s["y0"]
    W = s["width_px"]
    gn = g / 255.0
    print("rear %s  %dx%d  sx=%.5f mm/px  chassis x0=%d y0=%d"
          % (s["file"], g.shape[1], g.shape[0], sx, x0, y0))

    # panel level just above the band, for a threshold that separates bare
    # aluminium from the band's shadowed web
    pa = int(round(84.0 / sx))
    pb = int(round(87.0 / sx))
    panel = float(np.percentile(gn[y0 + pa:y0 + pb, x0 + int(2 / sx):
                                        x0 + W - int(2 / sx)], 60))
    print("panel grey above the band: %.3f" % panel)

    # threshold: halfway between panel and the band's own dark mode
    ya = y0 + int(round(88.5 / sx))
    yb = y0 + int(round(93.5 / sx))
    inner = gn[ya:yb, x0 + int(40 / sx):x0 + W - int(40 / sx)]
    t_band, eta = otsu(inner)
    lf = largest_blob_fraction(inner < t_band)
    print("band interior: otsu %.3f eta %.2f largest blob %.2f%% -> %s"
          % (t_band, eta, lf * 100,
             "holes" if lf < 0.10 else "NOT holes, refusing"))
    if lf >= 0.10:
        return
    thr = min(t_band, panel - 0.06)
    print("using threshold %.3f (panel %.3f)" % (thr, panel))

    tops, bots = [], []
    # scan only the lower strip. The whole column also contains the upper
    # perforated field at 4.5-6 mm, and "first dark row in the column" picks
    # that up instead of the band - the first version of this reported a band
    # top of 5 mm and a height of 89 mm, which is the field, not the band.
    r_lo = y0 + int(round(85.0 / sx))
    r_hi = y0 + int(round(H_MM / sx))
    for c in range(x0 + 1, x0 + W - 1):
        col = gn[r_lo:r_hi, c]
        ys = np.nonzero(col < thr)[0]
        if not len(ys):
            continue
        tops.append(((c - x0 + 0.5) * sx, (ys[0] + r_lo - y0) * sx))
        bots.append(((c - x0 + 0.5) * sx, (ys[-1] + 1 + r_lo - y0) * sx))
    tops = np.array(tops)
    bots = np.array(bots)
    print("\nband top edge:  min %.2f  max %.2f  mean %.2f mm from top"
          % (tops[:, 1].min(), tops[:, 1].max(), tops[:, 1].mean()))
    print("band bottom:    min %.2f  max %.2f  mean %.2f mm from top"
          % (bots[:, 1].min(), bots[:, 1].max(), bots[:, 1].mean()))

    mid = (tops[:, 0] > 30) & (tops[:, 0] < 167)
    print("centre columns (30-167 mm): top %.2f mm, bottom %.2f mm, "
          "height %.2f mm"
          % (tops[mid, 1].mean(), bots[mid, 1].mean(),
             (bots[mid, 1] - tops[mid, 1]).mean()))

    print("\n  x_mm   top_mm  bot_mm  height_mm")
    for t in range(2, 198, 6):
        i = int(np.argmin(np.abs(tops[:, 0] - t)))
        if abs(tops[i, 0] - t) < 3.0:
            print("  %5.1f   %6.2f  %6.2f  %6.2f"
                  % (tops[i, 0], tops[i, 1], bots[i, 1],
                     bots[i, 1] - tops[i, 1]))

    # where does the band's top edge start to curve up at each end?
    tt = tops[mid, 1].mean()
    for side, sel in (("left", tops[:, 0] < 98.5), ("right", tops[:, 0] > 98.5)):
        xs = tops[sel, 0]
        ys = tops[sel, 1]
        rise = np.nonzero(ys < tt - 0.30)[0]
        if len(rise):
            print("\n  %s end: top edge is %.2f mm above centre level from "
                  "x=%.1f mm inward" % (side, tt - ys[rise].max(),
                                        xs[rise].max()))
    print("\nspec: GRILLE_BAND_Z0=%.2f Z1=%.2f cm  -> %.1f..%.1f mm from top"
          % (S.GRILLE_BAND_Z0, S.GRILLE_BAND_Z1,
             H_MM - S.GRILLE_BAND_Z1 * 10, H_MM - S.GRILLE_BAND_Z0 * 10))
    print("  as z from the bottom: %.2f..%.2f cm" % (S.GRILLE_BAND_Z0,
                                                     S.GRILLE_BAND_Z1))


if __name__ == "__main__":
    main()
