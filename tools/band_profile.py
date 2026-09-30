#!/usr/bin/env python3
"""Row dark-share profiles of the base band: photograph against model.

Counting rows and hole widths by eye off a 6x zoom is guesswork. These are the
actual per-row dark fractions for both images over the same 9 mm of height, so
the number of hole rows, their spacing and their depth can be read off
directly.
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from compare_render import normalise_ref, otsu, autocorr_peak, REF, OUT  # noqa

W_MM, H_MM = 197.0, 95.0


def prof(g, sx, label, lo=85.5, hi=94.5):
    h, w = g.shape
    a = int(round(lo / sx))
    b = min(h, int(round(hi / sx)))
    mid = slice(int(0.25 * w), int(0.75 * w))
    blk = g[a:b, mid]
    t, _ = otsu(blk)
    m = blk < t
    share = m.mean(axis=1)
    print("\n%s  rows %d..%d (%.2f..%.2f mm, %d rows)  otsu %.3f"
          % (label, a, b, lo, hi, b - a, t))
    print("  dark share per row (%%):")
    for i in range(0, len(share), 2):
        mm = lo + i * sx
        bar = "#" * int(share[i] * 40)
        print("   %5.2f mm  %5.1f  %s" % (mm, share[i] * 100, bar))
    p = share - share.mean()
    den = np.sqrt((p * p).sum()) or 1.0
    ac = np.array([float((p[k:] * p[:len(p) - k]).sum() / den)
                   for k in range(min(20, len(p) - 1))])
    print("  row-profile autocorrelation:", " ".join("%5.2f" % v for v in ac))
    pk = autocorr_peak(share, axis=0)
    print("  fundamental row period: %d px = %.3f mm"
          % (pk, pk * sx))
    # column profile too, for the hole width
    cshare = m.mean(axis=0)
    pkx = autocorr_peak(cshare, axis=0)
    print("  fundamental col period: %d px = %.3f mm"
          % (pkx, pkx * sx))
    # run lengths
    def runs(mask, axis):
        out = []
        arr = mask if axis == 1 else mask.T
        for line in arr:
            d = np.diff(np.concatenate(([0], line.view(np.int8), [0])))
            s_, e_ = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
            out.extend((e_ - s_).tolist())
        return np.array(out) if out else np.array([0])
    rx, rz = runs(m, 1), runs(m, 0)
    print("  hole run  x median %.2f px = %.3f mm   z median %.2f px = %.3f mm"
          % (np.median(rx), np.median(rx) * sx, np.median(rz), np.median(rz) * sx))
    return share


def main():
    rimg = normalise_ref(os.path.join(REF, "apple_hw_back.jpg"), 460)
    gr = np.asarray(rimg.convert("L"), dtype=np.float32) / 255.0
    sx = W_MM / gr.shape[1]
    mp = os.path.join(OUT, "rear_model.png")
    gm = np.asarray(Image.open(mp).convert("L").resize(rimg.size, Image.LANCZOS),
                    dtype=np.float32) / 255.0
    prof(gr, sx, "APPLE  rear")
    prof(gm, sx, "MODEL  rear")


if __name__ == "__main__":
    main()
