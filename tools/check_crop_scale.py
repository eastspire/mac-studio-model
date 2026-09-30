#!/usr/bin/env python3
"""How far is the comparison's reference crop from a true 197:95 chassis box?

compare_render crops the Apple photo with a vertical span taken from
`g < 244`, which includes the contact shadow under the machine. The model side
is cropped from a synthetic render, where the silhouette ends exactly at the
chassis. If those two boxes have different aspect ratios then every row in the
region report is a different physical millimetre in the two images, and no
amount of per-region thresholding fixes it.
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from compare_render import chassis_box, REF  # noqa: E402

W_MM, H_MM = 197.0, 95.0
SHOTS = {"front": "apple_static_front.jpg", "rear": "apple_hw_back.jpg"}


def main():
    for kind, fn in SHOTS.items():
        g = np.asarray(Image.open(os.path.join(REF, fn)).convert("L"),
                       dtype=np.float32)
        x0, y0, x1, y1 = chassis_box(g)
        w, h = x1 - x0 + 1, y1 - y0 + 1
        sx = W_MM / w
        print("\n=== %s (%s) ===" % (kind, fn))
        print("  crop %dx%d px, aspect %.4f, true 197:95 = %.4f"
              % (w, h, w / float(h), W_MM / H_MM))
        print("  at width-derived scale %.5f mm/px the crop is %.2f mm tall,"
              " not %.1f" % (sx, h * sx, H_MM))
        print("  vertical error: %+.2f mm (%.2f%%)"
              % (h * sx - H_MM, (h * sx / H_MM - 1.0) * 100.0))

        # where do the two disagree about the bottom edge?
        sxk = W_MM / s if False else None
        # bottom edge by silhouette: machine vs clean white ground
        col = g[:, (x0 + x1) // 2]
        prof = col.astype(np.float32)
        d = np.gradient(prof)
        cand = [(i, d[i]) for i in range(y0, y1 + 1) if abs(d[i]) > 0.02]
        print("  strong vertical edges below mid-panel (row, gradient, "
              "mm from top):")
        for i, dv in cand[:14]:
            print("     row %4d  grad %+7.2f  %6.2f mm"
                  % (i, dv, (i - y0) * sx))

        # the same from verify_spec's own calibration, which is width+aspect
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from verify_spec import load
        s = load(kind)
        print("  verify_spec calibration: x0=%d y0=%d width=%d  (%.2f x %.2f mm)"
              % (s["x0"], s["y0"], s["width_px"],
                 s["width_px"] * s["sx"],
                 s["width_px"] * s["sx"] * H_MM / W_MM))


if __name__ == "__main__":
    main()
