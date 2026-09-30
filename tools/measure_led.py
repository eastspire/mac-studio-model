#!/usr/bin/env python3
"""Report the status LED measurement from the front photograph.

The measurement itself lives in tools/verify_spec.py, which is the acceptance
test, so that there is exactly one definition of it. This script exists to show
the numbers and the intermediate profile when the LED check is being tuned;
it cannot disagree with the test because it calls the same code.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "blender"))

import mac_studio_spec as S      # noqa: E402
from verify_spec import load, measure_led, H_MM, W_MM  # noqa: E402


def main():
    s = load("front")
    g, sx, x0, y0 = s["g"], s["sx"], s["x0"], s["y0"]
    print("front: x0=%d y0=%d width=%d  sx=%.5f mm/px" % (x0, y0, s["width_px"], sx))
    print("spec: LED_X=%.3f cm  IO_Z=%.2f cm  LED_R=%.3f cm (dia %.2f mm)"
          % (S.LED_X, S.IO_Z, S.LED_R, S.LED_R * 20.0))

    led = measure_led(g, sx, x0, y0)
    if led is None:
        print("LED NOT FOUND in the modelled box")
        return
    lx, lz, dh, dv = led
    print("\nmeasured  x = %.3f cm  (delta %+.3f mm)"
          % (lx, lx * 10.0 - S.LED_X * 10.0))
    print("measured  z = %.3f cm  (delta %+.3f mm)"
          % (lz, lz * 10.0 - S.IO_Z * 10.0))
    print("diameter   horizontal %.3f mm, vertical %.3f mm, mean %.3f mm"
          % (dh, dv, (dh + dv) / 2.0))
    print("  vs spec %.3f mm -> %+.3f mm; axis spread %.3f mm"
          % (S.LED_R * 20.0, (dh + dv) / 2.0 - S.LED_R * 20.0, abs(dh - dv)))

    # Independent cross-check: the equivalent disc diameter from AREA. The
    # chord method assumes the dot is convex and picks its widest row; the area
    # method assumes nothing about shape beyond being round. If the two agree
    # the diameter is real, and if they do not, the difference is the size of
    # the JPEG blur and neither number should be trusted to better than that.
    box = int(np.ceil(6.0 / sx))
    lcx = x0 + int(round((S.LED_X * 10.0 + W_MM / 2.0) / sx))
    lcy = y0 + int(round((H_MM - S.IO_Z * 10.0) / sx))
    win = g[lcy - box:lcy + box + 1, lcx - box:lcx + box + 1].astype(np.float64)
    edge = 3
    base = float(np.median(np.concatenate(
        [win[:edge, :].ravel(), win[-edge:, :].ravel(),
         win[:, :edge].ravel(), win[:, -edge:].ravel()])))
    resid = np.clip(win - base, 0.0, None)
    peak = resid.max()
    above = resid >= peak * 0.25
    area_px = float(above.sum())
    d_area = 2.0 * np.sqrt(area_px / np.pi) * sx
    print("cross-check: quarter-peak area %.0f px -> equivalent disc "
          "diameter %.3f mm" % (area_px, d_area))
    print("  chord method %.3f / %.3f mm, area method %.3f mm"
          % (dh, dv, d_area))
    print("  spread between the two methods: %.3f mm"
          % max(abs(d_area - dh), abs(d_area - dv)))
    print("  => LED_R should be about %.3f cm" % ((dh + dv + d_area) / 3.0 / 20.0))

    # the raw profile, so a change in the number can be traced to the pixels
    xi = box
    print("\nhorizontal profile through the dot (0-255, centre column marked):")
    prof = win[xi, :]
    line = []
    for i, v in enumerate(prof):
        line.append("%4d" % round(v))
    print("  " + " ".join(line))
    print("  " + " ".join("   ." if abs(i - box) < 1 else "   " for i in
                           range(len(prof))))


if __name__ == "__main__":
    main()
