#!/usr/bin/env python3
"""Measure the engraved icon row above the rear connectors.

The icons are modelled - build_rear_icons() places a bolt, a network glyph, a
USB trident, an HDMI wordmark and a headphone mark - but their x positions were
hard-coded and never checked against the photograph, which is how a feature can
be present in the model and still be in the wrong place. This finds them in
apple_hw_back.jpg the same way the ports are found: they are dark marks on
otherwise bare panel, in a band above the connector row and below the field.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))

import mac_studio_spec as S      # noqa: E402
from verify_spec import load, components  # noqa: E402

W_MM, H_MM = 197.0, 95.0


def main():
    s = load("rear")
    g, sx, x0, y0 = s["g"], s["sx"], s["x0"], s["y0"]
    print("rear: sx=%.5f mm/px, chassis x0=%d y0=%d" % (sx, x0, y0))
    print("spec ICON_Z=%.2f cm -> %.1f mm from the top" % (S.ICON_Z,
                                                           H_MM - S.ICON_Z * 10))

    # a band that clears the connector row below and the field above
    lo = H_MM - S.ICON_Z * 10 - 1.6
    hi = H_MM - S.ICON_Z * 10 + 1.6
    ry0 = y0 + int(round(lo / sx))
    ry1 = y0 + int(round(hi / sx))
    ix0 = x0 + int(round(6.0 / sx))
    ix1 = x0 + s["width_px"] - int(round(6.0 / sx))
    band = g[ry0:ry1 + 1, ix0:ix1 + 1]
    print("icon band %.1f..%.1f mm from the top (rows %d..%d)"
          % (lo, hi, ry0, ry1))
    print("  band grey: min %.3f  p1 %.3f  median %.3f  max %.3f"
          % (band.min() / 255.0, np.percentile(band, 1) / 255.0,
             np.median(band) / 255.0, band.max() / 255.0))

    thr = (np.percentile(band, 50) + np.percentile(band, 1)) / 2.0
    mask = band < thr
    print("  threshold %.1f/255, %d dark pixels (%.2f%%)"
          % (thr, mask.sum(), mask.mean() * 100))
    comps = components(mask, int(0.02 / (sx * sx)))
    # image-x ascending == model-x DESCENDING for a rear view
    print("\n  %d icon blobs, left to right in the photograph:" % len(comps))
    print("   #   x_mm(model)  z_mm  width_mm  height_mm  area_px")
    for i, comp in enumerate(comps):
        cx = ix0 + (comp[0] + comp[2] + 1) / 2.0
        cy = ry0 + (comp[1] + comp[3] + 1) / 2.0
        model_mm = 98.5 - (cx - x0) * sx
        print("  %2d   %+8.2f   %5.2f   %6.3f   %6.3f   %6d"
              % (i, model_mm / 10.0, (H_MM - (cy - y0) * sx) / 10.0,
                 (comp[2] - comp[0] + 1) * sx, (comp[3] - comp[1] + 1) * sx,
                 comp[4]))
    print("\n  spec places them at:")
    print("     Icon_Thunderbolt  x=+6.13 cm")
    print("     Icon_Network      x=%+.2f cm" % -1.916)
    print("     Icon_USB          x=%+.2f cm" % -1.916)
    print("     Icon_HDMI         x=%+.2f cm" % -4.276)
    print("     Icon_Headphone    x=%+.2f cm" % S.HEADPHONE_X)
    print("     all at z=%.2f cm" % S.ICON_Z)


if __name__ == "__main__":
    main()
