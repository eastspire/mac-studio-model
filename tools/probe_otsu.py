#!/usr/bin/env python3
"""Why is Otsu returning a threshold of 0.002 for the base-band window?

Prints the histogram the split is actually being taken from, so the answer is
visible rather than guessed at.
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from compare_render import normalise_ref, otsu, largest_blob_fraction, REF  # noqa

W_MM = 197.0


def dump(tag, win):
    v = np.asarray(win, dtype=np.float64).ravel()
    thr, eta = otsu(v)
    print("\n%s  n=%d  min=%.4f  p1=%.4f  p25=%.4f  med=%.4f  "
          "p75=%.4f  p99=%.4f  max=%.4f"
          % (tag, v.size, v.min(), np.percentile(v, 1), np.percentile(v, 25),
             np.median(v), np.percentile(v, 75), np.percentile(v, 99), v.max()))
    print("   otsu thr=%.4f eta=%.4f  largest blob=%.3f"
          % (thr, eta, largest_blob_fraction(v < thr)))
    hist, edges = np.histogram(v, bins=20, range=(0.0, 1.0))
    for i, cnt in enumerate(hist):
        if cnt:
            print("     %.2f-%.2f  %7d  %s"
                  % (edges[i], edges[i + 1], cnt, "#" * int(40 * cnt / hist.max())))


def main():
    img = normalise_ref(os.path.join(REF, "apple_hw_back.jpg"), 460)
    g = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
    h, w = g.shape
    sx = W_MM / w
    print("crop %dx%d  sx=%.4f mm/px" % (w, h, sx))

    dump("whole image", g)
    for lo, hi in ((82, 95), (86, 95), (88, 94), (90, 94)):
        y0 = int(round(lo / sx))
        y1 = min(h, int(round(hi / sx)))
        dump("rows %.0f..%.0f mm" % (lo, hi), g[y0:y1, :])
    # and the same window with the outer 6 mm of width removed
    for lo, hi in ((88, 94),):
        y0 = int(round(lo / sx))
        y1 = min(h, int(round(hi / sx)))
        dump("rows %.0f..%.0f mm, centre 60%% of width" % (lo, hi),
             g[y0:y1, int(w * 0.2):int(w * 0.8)])


if __name__ == "__main__":
    main()
