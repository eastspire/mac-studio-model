#!/usr/bin/env python3
"""Per-row diagnostic for the bottom of the panel.

compare_render reports a huge |delta| in the row profile at 89% of the chassis
height on BOTH panels, while the per-region Otsu numbers for the same rows are
within a few percent. Those two answers cannot both be right, so this prints the
raw quantities - row mean, row Otsu threshold, row dark share - for both images
side by side and lets the image decide which number is wrong.
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from compare_render import otsu, normalise_ref, REF, OUT  # noqa: E402

REFS = {"rear": "apple_hw_back.jpg", "front": "apple_static_front.jpg"}
OUT_H = 460


def profile(img_or_path, lo, hi):
    g = np.asarray((img_or_path if isinstance(img_or_path, Image.Image)
                    else Image.open(img_or_path)).convert("L"),
                   dtype=np.float32) / 255.0
    h = g.shape[0]
    step = max(2, int(round(0.5 / 95.0 * h)))
    rows = []
    for mm in np.arange(lo, hi, 0.5):
        y = int(round(mm / 95.0 * h))
        y = min(max(y, 0), h - step)
        strip = g[y:y + step]
        t, eta = otsu(strip)
        rows.append((mm, float(strip.mean()), t,
                     float((strip < t).mean()), float(strip.min()),
                     float(strip.max()), eta))
    return rows


def main():
    for view in ("rear", "front"):
        refp = normalise_ref(os.path.join(REF, REFS[view]), OUT_H)
        modp = os.path.join(OUT, "%s_model.png" % view)
        if not os.path.exists(modp):
            print("missing %s" % modp)
            continue
        print("\n=== %s : rows 78..95 mm from the top (crop %s) ==="
              % (view, refp.size))
        rr = profile(refp, 78.0, 95.0)
        mm_ = profile(modp, 78.0, 95.0)
        print("   mm   ref:mean  thr  dark%   eta   min   max  | model:mean  thr  dark%   eta   min   max")
        for (a, b) in zip(rr, mm_):
            print("  %5.1f    %.3f %.3f %5.1f  %.2f  %.3f %.3f  |   %.3f %.3f %5.1f  %.2f  %.3f %.3f"
                  % (a[0], a[1], a[2], a[3] * 100, a[6], a[4], a[5],
                     b[1], b[2], b[3] * 100, b[6], b[4], b[5]))


if __name__ == "__main__":
    main()
