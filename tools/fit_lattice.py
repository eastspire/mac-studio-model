#!/usr/bin/env python3
"""Fit the perforation lattice by 2-D cross-correlation over a parameter grid.

Every closed-form estimate of the pitch disagreed with the others, because a
hole is 3-4 px across in a JPEG-compressed product shot. Correlation is the
robust answer: it scores a whole patch of ~150 holes at once, so a 2% pitch
error that makes peak counting pick the wrong peak shows up immediately as a
loss of correlation rather than as a plausible-looking number.

Searched: horizontal pitch, row spacing, and the per-row stagger. The real
lattice is not assumed to be square or half-offset - on the rear field the
rows are visibly further apart than the columns are, which no square model
can express.
"""
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REF = os.path.join(ROOT, "reference")

MMPP = 197.0 / 1305.0
X0, TOP_ROW = 4, 6


def highpass(a):
    a = a - a.mean(axis=0, keepdims=True)
    a = a - a.mean(axis=1, keepdims=True)
    lo = np.fft.fft2(a)
    h, w = a.shape
    ky = np.fft.fftfreq(h)[:, None]
    kx = np.fft.fftfreq(w)[None, :]
    r = np.hypot(ky, kx)
    lo *= np.exp(-(r / 0.06) ** 2)        # keep the lattice, drop the shading
    return np.real(np.fft.ifft2(lo))


def synth(shape, p, p_row, stagger):
    """Unit lattice image: +1 on a hole centre, 0 elsewhere."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    cx = np.round((xx - w / 2.0) / p) * p + w / 2.0
    ry = np.round((yy - h / 2.0) / p_row) * p_row + h / 2.0
    ox = np.where((np.round((yy - h / 2.0) / p_row) % 2) == 1, stagger * p, 0.0)
    return ((xx - cx - ox) ** 2 + (yy - ry) ** 2) < (0.32 * p) ** 2


def fit(patch, label, p_rng=None, r_rng=None, s_vals=(0.0, 0.25, 0.5)):
    ref = highpass(patch)
    # holes are DARK, so correlate against the negated high-pass
    ref = -ref
    ref = (ref - ref.mean()) / (ref.std() + 1e-9)
    shape = ref.shape
    allbest = []
    for p in p_rng:
        for pr in r_rng:
            if pr < p * 0.4 or pr > p * 2.2:
                continue
            for s in s_vals:
                t = synth(shape, p, pr, s)
                if t.std() < 1e-6:
                    continue
                t = (t - t.mean()) / t.std()
                # circular correlation via FFT
                c = np.real(np.fft.ifft2(np.fft.fft2(ref) * np.conj(np.fft.fft2(t))))
                c /= c.size
                score = c.max()
                allbest.append((score, p, pr, s))
    allbest.sort(reverse=True)
    for score, p, pr, s in allbest[:6]:
        print("      %6.3f  pitch %.2f  row %.2f  stag %.2f" % (score, p, pr, s))
    score, p, pr, s = allbest[0]
    print("  %-16s best score %.3f   pitch %.3f mm   row %.3f mm   stagger %.2f"
          % (label, score, p, pr, s))
    return score, p, pr, s


def main():
    g = np.asarray(Image.open(os.path.join(REF, "apple_hw_back.jpg"))
                   .convert("L"), dtype=np.float32)
    row = lambda mm: TOP_ROW + int(mm / MMPP)   # noqa: E731

    # A short patch does not constrain the row spacing: a 7% error over eight
    # rows is under one hole diameter, which the correlation barely notices.
    # The field is 48 mm tall, so most of it is used.
    field = g[row(6):row(48), X0 + 120:X0 + 120 + 260]
    print("REAR FIELD  (patch %dx%d px = %.1f x %.1f mm)"
          % (field.shape[1], field.shape[0],
             field.shape[1] * MMPP, field.shape[0] * MMPP))
    fit(field, "field",
        p_rng=np.arange(1.60, 2.10, 0.01),
        r_rng=np.arange(1.30, 1.90, 0.01),
        s_vals=(0.1, 0.2, 0.25, 0.3, 0.4, 0.5))

    band = g[row(88.6):row(94.4), X0 + 200:X0 + 200 + 300]
    print("BASE BAND   (patch %dx%d px = %.1f x %.1f mm)"
          % (band.shape[1], band.shape[0],
             band.shape[1] * MMPP, band.shape[0] * MMPP))
    fit(band, "band",
        p_rng=np.arange(0.80, 1.60, 0.01),
        r_rng=np.arange(0.80, 1.60, 0.01),
        s_vals=(0.0, 0.1, 0.25, 0.5))


if __name__ == "__main__":
    main()
