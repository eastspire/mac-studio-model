#!/usr/bin/env python3
"""Print the whole icon-band crop of apple_hw_back.jpg as ASCII, per glyph.

Bounded-box statistics kept coming out inconsistent between thresholds because
the glyph strokes are 1 px wide and only faintly darker than the panel. Rather
than keep tuning a threshold, this dumps every pixel of the crop - faint ones
included - so the shape and the true extent can be read directly. Rows are
labelled in millimetres from the top of the chassis, and columns are numbered
so a stroke can be located in the photograph.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))

import mac_studio_spec as S      # noqa: E402
from verify_spec import load     # noqa: E402

W_MM, H_MM = 197.0, 95.0
HALF_MM = 3.4

GLYPHS = [
    ("thunderbolt", "ICON_TB_X"),
    ("ethernet", "ICON_ETH_X"),
    ("usb", "ICON_USB_X"),
    ("hdmi", "ICON_HDMI_X"),
    ("headphone", "ICON_HP_X"),
]


def main():
    s = load("rear")
    g, sx, x0, y0, width_px = s["g"], s["sx"], s["x0"], s["y0"], s["width_px"]
    print("rear %.5f mm/px  (1 char = 1 px = %.3f mm)" % (sx, sx))
    print("shades: '#' < 12%% below panel, '+' < 35%%, '-' < 60%%, '.' bare metal\n")

    only = sys.argv[1:] or None
    for name, attr in GLYPHS:
        if only and name not in only:
            continue
        cx_cm = getattr(S, attr)
        cx_mm = 98.5 - cx_cm * 10
        cy_mm = H_MM - S.ICON_Z * 10
        ix0 = max(x0, x0 + int(round((cx_mm - HALF_MM) / sx)))
        ix1 = min(x0 + width_px - 1, x0 + int(round((cx_mm + HALF_MM) / sx)))
        iy0 = y0 + int(round((cy_mm - HALF_MM) / sx))
        iy1 = y0 + int(round((cy_mm + HALF_MM) / sx))
        patch = g[iy0:iy1 + 1, ix0:ix1 + 1].astype(np.float64)
        panel = float(np.median(patch))
        span = panel - float(patch.min())
        depth = np.clip((panel - patch) / max(span, 1e-6), 0.0, 1.0)

        print("=== %-13s spec x=%+.3f cm  crop centred on it, %.2f mm wide ==="
              % (name, cx_cm, patch.shape[1] * sx))
        print("    " + "".join(str(c % 10) for c in range(patch.shape[1])))
        for r in range(patch.shape[0]):
            line = "".join("#" if v > 0.88 else "+" if v > 0.65 else
                           "-" if v > 0.40 else
                           ":" if v > 0.18 else "." for v in depth[r])
            print("    %s  %5.1f" % (line, (iy0 + r - y0) * sx))
        print()


if __name__ == "__main__":
    main()
