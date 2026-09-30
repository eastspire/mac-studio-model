#!/usr/bin/env python3
"""Measure the five engraved glyphs in the photo, in millimetres.

tools/icon_zoom.py shows what they look like; this says how big they are and
where they sit, to a stated tolerance rather than to whatever one threshold
happened to produce. The glyphs are 1..20 px wide in a 644 px photograph, so
the bounding box is threshold-sensitive: at a midpoint cut the headphone mark
came out 2.72 mm across and at a looser one 3.02 mm. Each glyph is therefore
measured at three cuts spanning the panel-to-glyph range and the MEDIAN of the
three is reported, with the spread printed next to it so a later disagreement
can be told apart from the noise floor.

The crops are also printed as ASCII at full resolution, because the builder's
Ethernet mark is four upward chevrons while the photograph shows two outward
chevrons with two dots between them, and the USB trident ends in a filled
circle rather than a square. Those are shape faults, not position faults, and
only the picture shows them.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))

import mac_studio_spec as S      # noqa: E402
from verify_spec import load, components   # noqa: E402

W_MM, H_MM = 197.0, 95.0
HALF_MM = 4.0                    # crop half-width; the HDMI wordmark is 5.74 mm
CUTS = (0.30, 0.40, 0.50)        # fraction of panel->glyph range that is "dark"

GLYPHS = [
    ("thunderbolt", "ICON_TB_X"),
    ("ethernet", "ICON_ETH_X"),
    ("usb", "ICON_USB_X"),
    ("hdmi", "ICON_HDMI_X"),
    ("headphone", "ICON_HP_X"),
]


def glyph_mask(patch, sx, cut):
    """Threshold, then keep only blobs big enough to be an engraved mark.

    components() returns (x0, y0, x1, y1, area) - x first. Slicing it as
    (y0, x0, y1, x1) does not raise: rows 3..27 with columns 17..12 is simply
    an empty slice, so the cleaned mask comes back almost entirely False and
    every measurement below is of nothing. The HDMI wordmark came out 3.02 mm
    wide that way; it is 5.74 mm.
    """
    lo = float(patch.min())
    hi = float(np.median(patch))
    mask = patch < hi - cut * (hi - lo)
    clean = np.zeros_like(mask)
    for x0, y0, x1, y1, _ in components(mask, int(0.010 / (sx * sx))):
        clean[y0:y1 + 1, x0:x1 + 1] = True
    return clean & mask


def bbox(mask):
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return None
    return ys.min(), ys.max(), xs.min(), xs.max()


def main():
    s = load("rear")
    g, sx, x0, y0, width_px = s["g"], s["sx"], s["x0"], s["y0"], s["width_px"]
    print("rear %.5f mm/px, chassis x0=%d y0=%d width=%d" % (sx, x0, y0, width_px))
    print("spec Z is cm from the BOTTOM; rows below are mm from the TOP.")
    print("each glyph measured at cuts %s, median reported\n" % (CUTS,))

    print("%-13s %8s %8s %8s %8s %8s %7s"
          % ("glyph", "x cm", "z cm", "w mm", "h mm", "dW", "parts"))
    print("-" * 68)
    for name, attr in GLYPHS:
        cx_cm = getattr(S, attr)
        cx_mm = 98.5 - cx_cm * 10
        cy_mm = H_MM - S.ICON_Z * 10
        ix0 = max(x0, x0 + int(round((cx_mm - HALF_MM) / sx)))
        ix1 = min(x0 + width_px - 1, x0 + int(round((cx_mm + HALF_MM) / sx)))
        iy0 = y0 + int(round((cy_mm - HALF_MM) / sx))
        iy1 = y0 + int(round((cy_mm + HALF_MM) / sx))
        patch = g[iy0:iy1 + 1, ix0:ix1 + 1]

        cxs, czs, ws, hs, ns = [], [], [], [], []
        for cut in CUTS:
            m = glyph_mask(patch, sx, cut)
            bb = bbox(m)
            if bb is None:
                continue
            ry0, ry1, rx0, rx1 = bb
            cxs.append(98.5 - (ix0 + (rx0 + rx1 + 1) / 2.0 - x0) * sx)
            czs.append((H_MM - (iy0 + (ry0 + ry1 + 1) / 2.0 - y0) * sx) / 10.0)
            ws.append((rx1 - rx0 + 1) * sx)
            hs.append((ry1 - ry0 + 1) * sx)
            ns.append(len(components(m, int(0.010 / (sx * sx)))))

        mx, mz = float(np.median(cxs)), float(np.median(czs))
        mw, mh = float(np.median(ws)), float(np.median(hs))
        print("%-13s %+8.3f %8.3f %8.3f %8.3f %8.3f %7d"
              % (name, mx / 10.0, mz, mw, mh,
                 (max(ws) - min(ws)) / 2.0, int(np.median(ns))))
        print("%-13s spec x %+8.3f  ->  %+0.3f mm      spec z %.3f -> %+0.3f mm"
              % ("", cx_cm, mx - cx_cm * 10, S.ICON_Z, mz * 10 - S.ICON_Z * 10))
        print("%-13s part widths mm: %s"
              % ("", " ".join("%.2f" % ((c[2] - c[1] + 1) * sx)
                               for c in components(glyph_mask(patch, sx, CUTS[1]),
                                                   int(0.010 / (sx * sx))))))

        if name in ("ethernet", "usb", "thunderbolt"):
            m = glyph_mask(patch, sx, CUTS[1])
            ry0, ry1, rx0, rx1 = bbox(m)
            sub = m[ry0:ry1 + 1, rx0:rx1 + 1]
            print("        %s" % "".join(str((rx0 + c) % 10)
                                       for c in range(sub.shape[1])))
            for r in range(sub.shape[0]):
                print("        %s  %5.1f mm from top"
                      % ("".join("#" if v else "." for v in sub[r]),
                         (iy0 + ry0 + r - y0) * sx))
        print()


if __name__ == "__main__":
    main()
