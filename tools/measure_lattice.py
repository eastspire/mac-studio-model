#!/usr/bin/env python3
"""Measure the perforation lattice pitch on the rear field and the base band.

A staggered lattice does not repeat at its own pitch in the VERTICAL
direction: a given column of holes comes back every 2p, and adjacent columns
are offset by p/2. Reading the vertical period straight off a row profile and
dividing by two is the usual shortcut and it is wrong whenever the highlight
rows are not cleanly separated.

This takes the 2-D power spectrum of a high-passed patch instead. A regular
staggered lattice shows up as two strong, symmetric spectral peaks whose
distance from the origin is 1/p, so the pitch follows from geometry with no
guessing about which period was observed.
"""
import os

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REF = os.path.join(ROOT, "reference")

FN = "apple_hw_back.jpg"
X0, WIDTH_PX, TOP_ROW = 4, 1305, 6
MMPP = 197.0 / WIDTH_PX


def pitch_of(patch, label, mm_to_px=MMPP):
    """Patch: float array, roughly mean-removed. Returns pitch in mm."""
    a = patch - patch.mean(axis=0, keepdims=True)
    a = a - a.mean(axis=1, keepdims=True)
    win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    F = np.abs(np.fft.fftshift(np.fft.fft2(a * win))) ** 2
    F[a.shape[0] // 2, a.shape[1] // 2] = 0.0
    cy, cx = np.unravel_index(np.argmax(F), F.shape)
    # the peak may sit in any quadrant; take the distance from the centre
    fy = (a.shape[0] // 2 - cy) / float(a.shape[0])
    fx = (a.shape[1] // 2 - cx) / float(a.shape[1])
    freq = np.hypot(fx, fy)                 # cycles per pixel
    # the two dominant peaks of a staggered lattice sit at p and sqrt(3) p
    p_direct = 1.0 / freq if freq > 0 else float("nan")
    p_3 = p_direct / np.sqrt(3.0)
    print("  %-10s patch %-10s peak at (%.4f, %.4f) cyc/px  ->  p = %.3f mm"
          "  or p = %.3f mm if the sqrt(3) partner dominates"
          % (label, "%dx%d" % a.shape, fx, fy, p_direct * mm_to_px,
             p_3 * mm_to_px))
    return p_direct * mm_to_px, p_3 * mm_to_px


def hole_diameter(patch, pitch_mm, label):
    """Hole diameter from the dark fraction of the high-passed patch.

    The field floor is a constant, so the holes are the negative excursions.
    Their area fraction times the cell area is the hole area; a circle of
    diameter d in a cell of pitch p has fraction pi d^2 / (4 sqrt(3) p^2) for a
    staggered (hexagonal-ish) lattice.
    """
    a = patch - np.median(patch)
    p = np.percentile(a, 5.0)
    frac = float((a < p).mean())
    d = np.sqrt(frac * 4.0 * np.sqrt(3.0) * pitch_mm ** 2 / np.pi)
    print("  %-10s dark fraction %.3f -> hole diameter %.2f mm" % (label, frac, d))
    return d


def main():
    g = np.asarray(Image.open(os.path.join(REF, FN)).convert("L"),
                   dtype=np.float32)
    h, w = g.shape
    row = lambda mm: TOP_ROW + int(mm / MMPP)   # noqa: E731

    # rear perforated field, clear of the edges
    f = g[row(12):row(44), X0 + 120:X0 + 120 + 300]
    print("REAR FIELD")
    p, p3 = pitch_of(f, "field")
    hole_diameter(f, p, "field")

    # base band, on the rear panel below the ports
    b = g[row(89):row(94), X0 + 260:X0 + 260 + 300]
    print("BASE BAND (rear)")
    p, p3 = pitch_of(b, "band")
    hole_diameter(b, p, "band")

    # and again on the front, where the band is lit differently
    fg = np.asarray(Image.open(os.path.join(REF, "apple_static_front.jpg"))
                    .convert("L"), dtype=np.float32)
    MF = 197.0 / 1392.0
    bf = fg[TOP_ROW + int(89 / MF):TOP_ROW + int(94 / MF), 4 + 260:4 + 260 + 300]
    print("BASE BAND (front)")
    p, p3 = pitch_of(bf, "band", MF)
    hole_diameter(bf, p, "band")


if __name__ == "__main__":
    main()
