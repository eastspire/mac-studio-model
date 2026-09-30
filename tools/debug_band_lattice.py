#!/usr/bin/env python3
"""Debug the band lattice check: print the autocorrelation profiles raw.

verify_spec reported the same lag of 10 px for both axes and a stagger of 0.00
on a lattice that is plainly half-staggered, so the measurement is being
inspected before its result is trusted.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "blender"))

import mac_studio_spec as S                       # noqa: E402
from compare_render import (otsu, autocorr_profile, autocorr_peak,  # noqa
                            stagger_fraction, row_pitch_profile)
from verify_spec import load                      # noqa: E402


def main():
    s = load("rear")
    g, sx, x0, y0 = s["g"], s["sx"], s["x0"], s["y0"]
    ya = y0 + int(round(88.5 / sx))
    yb = y0 + int(round(93.5 / sx))
    xa = x0 + int(round(40.0 / sx))
    xb = x0 + s["width_px"] - int(round(40.0 / sx))
    band = g[ya:yb, xa:xb].astype(np.float64) / 255.0
    thr, eta = otsu(band)
    holes = band < thr
    print("band crop %s  (%.2f x %.2f mm)  otsu %.3f  open %.1f%%"
          % (holes.shape, holes.shape[1] * sx, holes.shape[0] * sx, thr,
             holes.mean() * 100))

    px = autocorr_profile(holes, 1)
    n = min(len(px), 30)
    print("\nx autocorrelation, lags 0..%d:" % (n - 1))
    print("  " + " ".join("%5.1f" % v for v in px[:n]))
    lag_x = autocorr_peak(holes, axis=1)
    print("  autocorr_peak(x) -> %d px = %.3f mm   spec %.3f mm"
          % (lag_x, lag_x * sx, S.GRILLE_PITCH_X * 10.0))

    rp = row_pitch_profile(holes)
    pz = autocorr_profile(rp - rp.mean(), 0)
    print("\nrow dark-share profile (%d rows):" % len(rp))
    print("  " + " ".join("%4.0f" % (v * 100) for v in rp))
    print("  autocorrelation:")
    print("  " + " ".join("%5.2f" % v for v in pz[:min(len(pz), 20)]))
    lag_z = autocorr_peak(rp, axis=0)
    print("  autocorr_peak(rows) -> %d px = %.3f mm   spec %.3f mm"
          % (lag_z, lag_z * sx, S.GRILLE_PITCH_Z * 10.0))

    print("\nstagger_fraction(holes, %d) = %.3f   spec %.2f"
          % (lag_x, stagger_fraction(holes, lag_x), S.GRILLE_STAGGER))
    even = holes[0::2].mean(axis=0)
    odd = holes[1::2].mean(axis=0)
    even = even - even.mean()
    odd = odd - odd.mean()
    den = np.sqrt((even * even).sum() * (odd * odd).sum())
    half = lag_x // 2
    cc = np.array([float((np.roll(even, t) * odd).sum() / den)
                   for t in range(half + 1)])
    print("  even/odd correlation over shifts 0..%d (%.1f mm):"
          % (half, half * sx))
    print("   " + " ".join("%5.2f" % v for v in cc))
    print("   peak at shift %d px = %.2f of the pitch"
          % (int(np.argmax(cc)), int(np.argmax(cc)) / float(lag_x)))
    a = holes.astype(np.float64)
    a = a - a.mean(axis=1, keepdims=True)
    for k in range(1, 13):
        if k >= a.shape[0]:
            break
        den2 = np.sqrt((a[0] ** 2).sum() * (a[k] ** 2).sum())
        if den2 <= 0:
            continue
        c2 = np.array([float((np.roll(a[0], t) * a[k]).sum() / den2)
                       for t in range(lag_x)])
        print("   k=%2d: best shift %+d px (%+.2f pitch), corr %.3f"
              % (k, int(np.argmax(c2)), int(np.argmax(c2)) / float(lag_x),
                 c2.max()))


if __name__ == "__main__":
    main()
