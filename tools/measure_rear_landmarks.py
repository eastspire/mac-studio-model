#!/usr/bin/env python3
"""Re-derive the rear-panel vertical landmarks with a corrected chassis box.

The earlier rear pass took the chassis to be 638 px tall. The photograph's own
edges put it at 631 px (rows 6..636 -> 95.0 mm at 0.15084 mm/px), and the row
that a naive edge finder picks first, row 45, is the TOP OF THE PERFORATED FIELD
at 5.9 mm, not the top of the machine. Every millimetre derived from the taller
box was therefore 1.1% too large. This re-measures the landmarks that matter.
"""
import os

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REF = os.path.join(ROOT, "reference")

FN = "apple_hw_back.jpg"
WIDTH_MM = 197.0
WIDTH_PX = 1306
TOP_ROW, BOT_ROW = 6, 636
MMPP = WIDTH_MM / WIDTH_PX


def main():
    g = np.asarray(Image.open(os.path.join(REF, FN)).convert("L"),
                   dtype=np.float32) / 255.0
    h, w = g.shape
    mm_of = lambda y: (y - TOP_ROW) * MMPP          # noqa: E731
    row_of = lambda mm: int(round(TOP_ROW + mm / MMPP))   # noqa: E731

    # 1. full-width row mean, excluding the extreme columns where the rounded
    #    corners darken the silhouette
    prof = g[:, int(w * 0.18):int(w * 0.82)].mean(axis=1)

    print("chassis rows %d..%d = %.1f mm at %.5f mm/px"
          % (TOP_ROW, BOT_ROW, (BOT_ROW - TOP_ROW) * MMPP, MMPP))

    # --- perforated field -------------------------------------------------
    # The field is the only large dark area up high; find it by thresholding
    # the row mean against the bare panel just below it.
    panel = float(np.median(prof[row_of(58):row_of(66)]))
    thr = panel * 0.72
    print("bare panel median %.3f  field threshold %.3f" % (panel, thr))
    top = None
    for y in range(TOP_ROW, row_of(70)):
        if prof[y] < thr:
            top = y
            break
    bot = None
    for y in range(BOT_ROW, TOP_ROW, -1):
        if y > row_of(50) and prof[y] < thr:
            bot = y
            break
    print("FIELD  top %.1f mm   bottom %.1f mm   height %.1f mm"
          % (mm_of(top), mm_of(bot), mm_of(bot) - mm_of(top)))

    # --- base band --------------------------------------------------------
    bthr = panel * 0.90
    btop = bot_band = None
    for y in range(int(row_of(80)), BOT_ROW):
        if prof[y] < bthr and btop is None:
            btop = y
    # walk to the last row still dark
    y = btop
    while y + 1 < BOT_ROW and prof[y + 1] < bthr:
        y += 1
    bot_band = y
    print("BAND   top %.1f mm   bottom %.1f mm   height %.1f mm   (z %.2f..%.2f cm)"
          % (mm_of(btop), mm_of(bot_band), mm_of(bot_band) - mm_of(btop),
             (95.0 - mm_of(bot_band)) / 10.0, (95.0 - mm_of(btop)) / 10.0))

    # --- port row ---------------------------------------------------------
    # dark, but the ports are small; use the per-row COUNT of dark pixels
    dark = g < thr
    cnt = dark[:, int(w * 0.10):int(w * 0.90)].sum(axis=1)
    lo, hi = row_of(60), row_of(85)
    seg = cnt[lo:hi]
    pk = lo + int(np.argmax(seg))
    # the run of rows holding at least 15% of the peak is the port band
    on = np.nonzero(seg > 0.15 * seg.max())[0]
    print("PORTS  peak row %.1f mm   band %.1f .. %.1f mm   centre %.1f mm"
          % (mm_of(pk), mm_of(lo + on[0]), mm_of(lo + on[-1]),
             mm_of((lo + on[0] + lo + on[-1]) / 2.0)))
    print("       centre height above foot plane = %.2f mm"
          % (95.0 - mm_of((lo + on[0] + lo + on[-1]) / 2.0)))

    # --- base band perforation pitch --------------------------------------
    # Autocorrelation of a high-pass version of a clean patch of the band.
    y0, y1 = int(row_of(89)), int(row_of(95))
    x0, x1 = int(w * 0.30), int(w * 0.55)
    patch = g[y0:y1, x0:x1]
    lp = patch.mean(axis=1, keepdims=True)
    hp = patch - lp
    hp = hp - hp.mean(axis=0, keepdims=True)
    ac = np.correlate(hp[:, hp.shape[1] // 2], hp[:, hp.shape[1] // 2], "full")
    ac = ac[ac.size // 2:]
    ac /= ac[0]
    peaks = [i for i in range(2, min(20, ac.size))
             if ac[i] > ac[i - 1] and ac[i] >= ac[i + 1] and ac[i] > 0.12]
    print("BAND PITCH  autocorr peaks (px) %s -> mm %s"
          % (peaks[:6], ["%.2f" % (p * MMPP) for p in peaks[:6]]))
    print("            hole pitch candidates: %s"
          % ", ".join("%.2f mm" % (p * MMPP / 2.0) for p in peaks[:3]))


if __name__ == "__main__":
    main()
