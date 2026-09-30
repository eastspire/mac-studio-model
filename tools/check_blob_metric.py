#!/usr/bin/env python3
"""Validate largest_blob_fraction as a hole-vs-gradient discriminator.

The claim under test: on the same Otsu split, perforated regions give a small
largest connected component and lit bare panel gives a near-total one. If that
does not hold on these four known cases the metric is wrong and must not be
wired into the acceptance report.
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from compare_render import (normalise_ref, otsu, largest_blob_fraction,  # noqa
                            REF, OUT)

REFS = {"rear": "apple_hw_back.jpg", "front": "apple_static_front.jpg"}


def frac(arr):
    h, w = arr.shape
    return arr.reshape(h, w)


def report(tag, block, mm_lo, mm_hi, expect):
    t, eta = otsu(block)
    m = block < t
    lf = largest_blob_fraction(m)
    print("  %-28s dark=%5.1f%%  eta=%.2f  largest blob=%6.1f%%  expect=%s"
          % (tag, m.mean() * 100, eta, lf * 100, expect))
    return lf


def main():
    for view in ("rear", "front"):
        img = normalise_ref(os.path.join(REF, REFS[view]), 460)
        g = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
        h, w = g.shape
        print("\n=== %s (%dx%d) ===" % (view, w, h))

        def band(lo, hi):
            return g[int(round(lo / 95.0 * h)):int(round(hi / 95.0 * h))]

        # left-of-centre sub-window, away from ports, to sample bare metal
        mid = slice(int(w * 0.15), int(w * 0.45))
        report("bare panel 79-86mm", band(79, 86)[:, mid], 79, 86, "gradient")
        report("bare panel 60-70mm", band(60, 70)[:, mid], 60, 70, "gradient")

        if view == "rear":
            report("field 10-45mm", band(10, 45)[:, mid], 10, 45, "holes")
            report("base band 88-94mm", band(88, 94)[:, mid], 88, 94, "holes")
        else:
            report("port row 70-73mm", band(70, 73), 70, 73, "holes")

    # the model render, same windows
    for view in ("rear", "front"):
        p = os.path.join(OUT, "%s_model.png" % view)
        if not os.path.exists(p):
            continue
        g = np.asarray(Image.open(p).convert("L"), dtype=np.float32) / 255.0
        h, w = g.shape
        print("\n=== %s MODEL (%dx%d) ===" % (view, w, h))

        def band(lo, hi):
            return g[int(round(lo / 95.0 * h)):int(round(hi / 95.0 * h))]

        mid = slice(int(w * 0.15), int(w * 0.45))
        report("bare panel 79-86mm", band(79, 86)[:, mid], 79, 86, "gradient")
        if view == "rear":
            report("field 10-45mm", band(10, 45)[:, mid], 10, 45, "holes")
            report("base band 88-94mm", band(88, 94)[:, mid], 88, 94, "holes")


if __name__ == "__main__":
    main()
