#!/usr/bin/env python3
"""Fit the base band's perforation lattice from the full-resolution rear photo.

The upper field and the base band are not the same pattern, and treating them
as one is how the model ended up with a square, un-staggered band of square
holes where Apple has staggered round ones. This measures the band on its own
terms:

* its vertical extent, from the plain panel above to the bottom of the machine;
* the horizontal and vertical pitch, by autocorrelation of the band crop;
* the stagger, by which offset makes the row-to-row correlation peak;
* the open area, from the band's own two-mode split.
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))

import mac_studio_spec as S      # noqa: E402
from compare_render import otsu, largest_blob_fraction  # noqa: E402
from verify_spec import load    # noqa: E402

W_MM, H_MM = 197.0, 95.0


def autocorr_profile(a, axis):
    """Normalised autocorrelation of a 2-D array along one axis."""
    a = a - a.mean()
    n = a.shape[axis]
    out = np.zeros(n)
    for k in range(n):
        if axis == 0:
            p, q = a[k:], a[:n - k]
        else:
            p, q = a[:, k:], a[:, :n - k]
        d = np.sqrt((p * p).sum() * (q * q).sum())
        out[k] = float((p * q).sum() / d) if d > 0 else 0.0
    return out


def main():
    s = load("rear")
    g, sx, x0, y0 = s["g"], s["sx"], s["x0"], s["y0"]
    print("rear full-res: %s  sx=%.5f mm/px  chassis y0=%d" % (s["file"], sx, y0))

    def row_of(mm):
        return y0 + int(round(mm / sx))

    # the band interior: clear of the top edge and of the contact shadow
    top_mm, bot_mm = 88.3, 94.2
    ya, yb = row_of(top_mm), row_of(bot_mm)
    xa = x0 + int(round(30.0 / sx))
    xb = x0 + s["width_px"] - int(round(30.0 / sx))
    band = g[ya:yb, xa:xb].astype(np.float64) / 255.0
    print("band crop rows %d..%d (%.2f..%.2f mm), cols %d..%d"
          % (ya, yb, top_mm, bot_mm, xa, xb))
    print("  grey min %.3f max %.3f mean %.3f" % (band.min(), band.max(),
                                                  band.mean()))

    thr, eta = otsu(band)
    lf = largest_blob_fraction(band < thr)
    print("  otsu %.3f  eta %.2f  largest dark blob %.2f%%  -> %s"
          % (thr, eta, lf * 100.0,
             "perforation" if lf < 0.10 else "NOT perforation, refusing"))
    if lf >= 0.10:
        return
    holes = band < thr
    print("  open area: %.1f%%" % (holes.mean() * 100.0))

    # pitch by autocorrelation, searched over the plausible range
    px = autocorr_profile(holes, 1)
    pz = autocorr_profile(holes, 0)
    lo_px, hi_px = int(0.5 / sx), int(3.0 / sx)
    lo_pz, hi_pz = int(0.5 / sx), int(3.0 / sx)
    ix = int(np.argmax(px[lo_px:hi_px])) + lo_px
    iz = int(np.argmax(pz[lo_pz:hi_pz])) + lo_pz
    print("  autocorr argmax: %.3f mm in x (lag %d px), %.3f mm in z (lag %d px)"
          % (ix * sx, ix, iz * sx, iz))

    # The argmax alone is not enough: on a periodic signal it can land on a
    # harmonic. Print every local maximum so the fundamental can be picked out
    # by eye against the run lengths and the open area.
    def peaks(prof, lo, hi, label):
        print("  %s autocorrelation peaks:" % label)
        found = []
        for i in range(lo, hi - 1):
            if prof[i] > prof[i - 1] and prof[i] >= prof[i + 1] \
                    and prof[i] > 0.10:
                found.append((i, prof[i]))
        for i, v in found:
            print("     lag %3d px = %.3f mm   corr %.3f%s"
                  % (i, i * sx, v, "   <-- argmax" if i in (ix, iz) else ""))
        return [i for i, _ in found]
    peaks(px, lo_px, hi_px, "x")
    peaks(pz, lo_pz, hi_pz, "z")

    print("\n  dark share per row through the band (every row, 0-255):")
    share = holes.mean(axis=1)
    print("   " + " ".join("%3d" % round(v * 100) for v in share))
    print("  row index of each peak in that profile:")
    for i in range(1, len(share) - 1):
        if share[i] > share[i - 1] and share[i] >= share[i + 1]:
            print("     row %2d = %.2f mm from band top (%.3f mm share)"
                  % (i, i * sx, share[i] * 100))

    # Stagger. For each row separation k, find the horizontal shift s that
    # best aligns row k with row 0. On a staggered lattice s is a constant
    # fraction of the x pitch, independent of k; on a square lattice it is
    # always zero. That constant is the stagger, and it is the single number
    # that tells the two lattices apart.
    rows = holes.astype(np.float64)
    rows -= rows.mean(axis=1, keepdims=True)
    print("  stagger: best horizontal shift per row separation")
    fracs = []
    for k in range(1, max(2, iz)):
        if k >= rows.shape[0]:
            break
        a, b = rows[0], rows[k]
        denom = np.sqrt((a * a).sum() * (b * b).sum())
        if denom <= 0:
            continue
        cc = np.array([float((np.roll(a, s) * b).sum() / denom)
                       for s in range(ix)])
        s = int(np.argmax(cc))
        # roll() wraps, so only shifts in the first half are meaningful
        if s > ix // 2:
            s -= ix
        fracs.append(s / float(ix))
        print("     k=%2d rows (%.2f mm): best shift %+d px (%+.3f mm) "
              "= %+.2f pitch, corr %.3f"
              % (k, k * sx, s, s * sx, s / float(ix), cc.max()))
    if fracs:
        med = float(np.median(fracs))
        spread = float(np.max(fracs) - np.min(fracs))
        print("  => stagger %.2f of the x pitch, spread %.2f"
              % (med, spread))
        print("     (0.00 is a square lattice, 0.50 is half-staggered)")

    # hole size: the mean run length of dark pixels along rows and columns
    def runs(mask, axis):
        out = []
        arr = mask if axis == 1 else mask.T
        for line in arr:
            d = np.diff(np.concatenate(([0], line.view(np.int8), [0])))
            s_, e_ = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
            out.extend((e_ - s_).tolist())
        return np.array(out) if out else np.array([0])

    rx = runs(holes, 1)
    rz = runs(holes, 0)
    print("  hole run length  x: median %.2f px = %.3f mm  (n=%d)"
          % (np.median(rx), np.median(rx) * sx, len(rx)))
    print("  hole run length  z: median %.2f px = %.3f mm  (n=%d)"
          % (np.median(rz), np.median(rz) * sx, len(rz)))

    # The dark class is not only the holes. The band is a 1.3 mm recess and the
    # web between holes is in shadow too, so the 48.7% above counts the shadow
    # as opening. Cutting lower, at a fixed fraction of the way from the panel
    # to the hole floor, isolates the openings themselves; the depth at which
    # the cut is taken is reported so the number can be judged.
    print("\n  depth slices: open area and median run at several cuts")
    panel = float(np.percentile(band, 90))
    floor = float(np.percentile(band, 2))
    for frac in (0.5, 0.6, 0.7, 0.8, 0.9):
        cut = floor + (panel - floor) * frac
        m = band < cut
        if m.sum() == 0:
            continue
        a_x = runs(m, 1)
        a_z = runs(m, 0)
        lf2 = largest_blob_fraction(m)
        print("    cut %.3f (%.0f%% of the way to the floor): open %5.1f%%  "
              "run x %4.2f px %.3f mm  run z %4.2f px %.3f mm  blob %5.1f%%"
              % (cut, (1 - frac) * 100, m.mean() * 100,
                 np.median(a_x), np.median(a_x) * sx,
                 np.median(a_z), np.median(a_z) * sx, lf2 * 100))

    print("\nspec currently: GRILLE_PITCH_X=%.3f GRILLE_PITCH_Z=%.3f "
          "GRILLE_STAGGER=%.2f GRILLE_HOLE_R=%.3f band z %.2f..%.2f cm"
          % (S.GRILLE_PITCH_X, S.GRILLE_PITCH_Z, S.GRILLE_STAGGER,
             S.GRILLE_HOLE_R, S.GRILLE_BAND_Z0, S.GRILLE_BAND_Z1))


if __name__ == "__main__":
    main()
