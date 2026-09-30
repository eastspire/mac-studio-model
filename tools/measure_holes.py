#!/usr/bin/env python3
"""Count the holes directly: peaks along a row, peaks along a column.

The spectral estimate is ambiguous for a staggered lattice - the same two
peaks admit several (pitch, orientation) readings, and they differ by a factor
of two. Counting the visible holes does not have that ambiguity, so this is
the number the spec is built from.
"""
import os

import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REF = os.path.join(ROOT, "reference")

MMPP = 197.0 / 1305.0
X0, TOP_ROW = 4, 6
row = lambda mm: TOP_ROW + int(mm / MMPP)   # noqa: E731


def peaks(sig, min_gap, thresh):
    out = []
    for i in range(1, len(sig) - 1):
        if sig[i] > sig[i - 1] and sig[i] >= sig[i + 1] and sig[i] > thresh:
            if not out or i - out[-1] >= min_gap:
                out.append(i)
    return out


def report(g, x_from, x_to, y_from, y_to, label, mmpx=MMPP):
    p = g[row(y_from):row(y_to), x_from:x_to].astype(np.float64)
    p = p - p.mean(axis=0, keepdims=True)
    p = p - p.mean(axis=1, keepdims=True)

    # one row through the middle: horizontal spacing
    mid = p.shape[0] // 2
    prof = p[mid]
    thr = prof.std() * 0.5
    pk = peaks(prof, 3, thr)
    if len(pk) > 2:
        d = np.diff(pk)
        print("  %-22s row peaks %d over %d px -> %.2f px = %.3f mm"
              % (label, len(pk), p.shape[1], d.mean(), d.mean() * mmpx))

    # one column: vertical spacing
    col = p[:, p.shape[1] // 2]
    thr = col.std() * 0.5
    pk = peaks(col, 2, thr)
    if len(pk) > 2:
        d = np.diff(pk)
        print("  %-22s col peaks %d over %d px -> %.2f px = %.3f mm"
              % (label, len(pk), p.shape[0], d.mean(), d.mean() * mmpx))
    return p


def main():
    g = np.asarray(Image.open(os.path.join(REF, "apple_hw_back.jpg"))
                   .convert("L"), dtype=np.float32)
    print("mm/px %.5f" % MMPP)
    print("REAR FIELD")
    report(g, X0 + 150, X0 + 450, 14.0, 44.0, "field, 30 mm tall")
    print("BASE BAND")
    report(g, X0 + 300, X0 + 600, 89.0, 94.0, "band, 5 mm tall")

    fg = np.asarray(Image.open(os.path.join(REF, "apple_static_front.jpg"))
                    .convert("L"), dtype=np.float32)
    MF = 197.0 / 1392.0
    global row
    row = lambda mm: 6 + int(mm / MF)   # noqa: E731
    print("BASE BAND (front, %.5f mm/px)" % MF)
    report(fg, 4 + 300, 4 + 600, 89.0, 94.0, "band, 5 mm tall", MF)

    # magnified crops so the count can be checked by eye
    out = os.path.join(ROOT, "renders", "compare")
    os.makedirs(out, exist_ok=True)
    Image.fromarray(g[row(16):row(26), X0 + 200:X0 + 320].astype(np.uint8)) \
        .resize((120 * 8, 100 * 8), Image.NEAREST) \
        .save(os.path.join(out, "zoom_field.png"))
    Image.fromarray(g[row(88.5):row(94.5), X0 + 300:X0 + 400].astype(np.uint8)) \
        .resize((100 * 10, 60 * 10), Image.NEAREST) \
        .save(os.path.join(out, "zoom_band.png"))
    print("  wrote zoom_field.png (10 mm x 8x) and zoom_band.png (8 mm x 10x)")


if __name__ == "__main__":
    main()
