#!/usr/bin/env python3
"""Measure the Touch ID button off Apple's rear photograph, radius by radius.

tools/port_row.py turned up a real discrepancy: in the photograph the Touch ID
disc reads 84% bright inside its own opening, and in the render 32%. The render
paints the button's glyph as a FILLED disc of 0.52 x the button radius, which
makes the whole centre dark, and it paints the gap ring 0.6 mm wide. A Mac
Studio's Touch ID is the same anodised aluminium as the case with a narrow dark
gap around it, so it should read almost as bright as the panel.

That is a claim about two numbers nobody has measured: how wide the gap really
is, and how much of the button face the glyph covers. Both are measurable in
the photograph and neither is currently in the spec, so this measures them.

The measurement is a horizontal cut through the button's centre, taken on the
ORIGINAL rear photograph at 0.15096 mm/px rather than on a comparison crop, so
one pixel is 0.15 mm and a 0.3 mm gap is two pixels wide - enough to call.
Runs of the cut are reported in millimetres, and each is matched against the
spec's own radius so a disagreement shows up as a number rather than a feeling.

Run:  python3 tools/touchid_probe.py
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))
REF = os.path.join(ROOT, "reference")

import mac_studio_spec as S                    # noqa: E402
import verify_spec as V                        # noqa: E402

W_MM, H_MM = 197.0, 95.0


def runs_of(mask):
    m = np.asarray(mask, dtype=np.int8)
    if not m.any():
        return []
    d = np.diff(np.concatenate(([0], m, [0])))
    return list(zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0] - 1))


def main():
    c = V.Check("rear")
    g, sx = c.s["g"], c.s["sx"]
    print("rear photograph %s at %.5f mm/px" % (c.s["file"], sx))

    zc = S.IO_Z * 10.0
    # z is height above the BASE, and the photograph's row index is measured
    # DOWN from the chassis top. Using zc itself as a distance from the top
    # lands 48 mm high, inside the perforated field, and the cut then measures
    # the field's 1.2 mm hole pitch instead of the button.
    row = int(round(c.s["y0"] + (H_MM - zc) / sx))
    col = int(round(c.s["x0"] + (98.5 - S.TOUCHID_X * 10.0) / sx))
    R = S.TOUCHID_R * 10.0
    span = int(round(2.6 * R / sx))
    lo, hi = col - span, col + span
    cut = g[row - 1:row + 2, lo:hi].min(axis=0)      # 3 rows: the darkest
    cut = g[row, lo:hi].astype(np.float64)            # the centre row

    # The bare panel sets what "bright" means. Sampling it hard against the
    # photo's edge is useless: 12 mm out from the button the panel is already
    # down in the corner falloff and reads 108/255 against 195/255 a few
    # millimetres further in, so a threshold taken from there calls the whole
    # button dark. 5.5-8 mm out is bare panel and still clear of the gap.
    panel = float(np.median(np.concatenate(
        [g[row, col + int(round(5.5 / sx)):col + int(round(8.0 / sx))],
         g[row, col - int(round(8.0 / sx)):col - int(round(5.5 / sx))]])))
    print("bare panel 5.5-8 mm out: %.1f/255" % panel)
    thr = panel * 0.72
    dark = cut < thr
    print("cut at z %.1f mm, %d px wide (%.2f mm), threshold %.1f/255"
          % (zc, hi - lo, (hi - lo) * sx, thr))
    print()

    # A radial profile bins |r| over BOTH sides of the button. The panel's
    # brightness falls by about 40/255 across the 22 mm of this cut, so a
    # left/right comparison reads the lighting gradient as if it were geometry;
    # averaging the two sides at the same radius cancels it and leaves the
    # button.
    bin_mm = 0.15
    nb = int((6.0) / bin_mm)
    acc = np.zeros(nb)
    cnt = np.zeros(nb)
    rad = (np.arange(hi - lo) - (hi - lo) / 2.0) * sx
    for i in range(hi - lo):
        b = int(abs(rad[i]) / bin_mm)
        if b < nb:
            acc[b] += cut[i]
            cnt[b] += 1
    print("  radial profile, %.2f mm bins, both sides averaged:" % bin_mm)
    for b in range(nb):
        if cnt[b] == 0:
            continue
        v = acc[b] / cnt[b]
        bar = "#" * int(max(0, (panel - v)) * 0.18)
        print("    r %4.2f..%4.2f mm  %6.1f  %5.1f%% of panel  %-14s %s"
              % (b * bin_mm, (b + 1) * bin_mm, v, v / panel * 100, bar,
                 "DARK" if v < thr else ""))
    print()
    print("  spec button radius %.3f mm; render draws the gap ring 0.6 mm wide"
          % R)
    print("  and the glyph as a filled disc of radius %.3f mm (0.52 R)"
          % (0.52 * R))
    rr = [( (s - (hi - lo) / 2.0) * sx, (e - (hi - lo) / 2.0) * sx )
          for s, e in runs_of(dark)]
    rr = [(-b, -a) for a, b in rr][::-1]     # signed radius, right -> left
    print("  dark runs, as signed radius in mm from the button's centre:")
    for a, b in rr:
        print("    %+7.3f .. %+7.3f   %6.3f mm"
              % (a, b, b - a))
    print()
    print("  spec button radius %.3f mm; render draws the gap ring 0.6 mm wide"
          % R)
    print("  and the glyph as a filled disc of radius %.3f mm (0.52 R)"
          % (0.52 * R))
    print()
    for lo_r, hi_r in ((0.0, 0.52 * R), (0.52 * R, R - 0.6), (R - 0.6, R),
                       (R, 2.6 * R)):
        i0 = int(round((lo_r + (hi - lo) / 2.0) * sx / sx))
        i1 = int(round((hi_r + (hi - lo) / 2.0) * sx / sx))
        seg = cut[i0:i1]
        if seg.size == 0:
            continue
        print("    r %5.3f..%5.3f mm   mean %6.1f  (%4.1f%% of panel)"
              "   dark %5.1f%%"
              % (lo_r, hi_r, float(seg.mean()), float(seg.mean()) / panel * 100,
                 float((seg < panel * 0.72).mean()) * 100))


if __name__ == "__main__":
    main()
