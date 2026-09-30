#!/usr/bin/env python3
"""Validate stagger_fraction on synthetic lattices of known stagger.

The real band has to be judged against a lattice whose answer is known. This
builds idealised bands - same pitch, same hole shape, stagger from 0.00 to 0.50
- runs the same measurement used by the acceptance test, and prints the whole
correlation curve so a wrong result can be seen rather than argued about.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "blender"))

from compare_render import autocorr_peak, stagger_fraction  # noqa: E402

PITCH_X_MM = 1.962
PITCH_Z_MM = 0.906
HOLE_RX_MM = 0.75
HOLE_RZ_MM = 0.28
SX = 0.15096          # mm per pixel, apple_hw_back.jpg


def synth(stagger, nrows=33, ncols=775):
    m = np.zeros((nrows, ncols), dtype=bool)
    for r in range(nrows):
        off = (r % 2) * stagger * PITCH_X_MM
        for c in range(ncols):
            u = ((c * SX + off) % PITCH_X_MM) - PITCH_X_MM / 2.0
            v = ((r * SX) % PITCH_Z_MM) - PITCH_Z_MM / 2.0
            if (u / HOLE_RX_MM) ** 2 + (v / HOLE_RZ_MM) ** 2 < 1.0:
                m[r, c] = True
    return m


def curve(mask, pitch):
    even = mask[0::2].mean(axis=0)
    odd = mask[1::2].mean(axis=0)
    even = even - even.mean()
    odd = odd - odd.mean()
    den = np.sqrt((even * even).sum() * (odd * odd).sum())
    if den <= 0:
        return None
    half = int(pitch) // 2
    return np.array([float((np.roll(even, t) * odd).sum() / den)
                     for t in range(half + 1)])


def main():
    print("synthetic lattices, %d x %d px at %.5f mm/px" % (33, 775, SX))
    for st in (0.00, 0.10, 0.20, 0.25, 0.30, 0.40, 0.50):
        m = synth(st)
        lag = autocorr_peak(m, axis=1)
        got = stagger_fraction(m, lag)
        cc = curve(m, lag)
        print("  true %.2f -> pitch %3d px (%.3f mm)  stagger %.3f   %s"
              % (st, lag, lag * SX, got,
                 "OK" if abs(got - st) < 0.08 else "<-- MISMATCH"))
        if cc is not None:
            print("        corr curve over shifts 0..%d: %s"
                  % (len(cc) - 1,
                     " ".join("%5.2f" % v for v in cc)))


if __name__ == "__main__":
    main()
