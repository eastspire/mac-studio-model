#!/usr/bin/env python3
"""Pixel-diff an orthographic face render against Apple's hardware diagram.

Both images are reduced to "share of dark pixels per horizontal band" and
"share of dark pixels per vertical column", which is the measurement that
actually matters for this model: where the perforated fields start and stop,
where the port band sits, and where each connector falls horizontally.

The comparison is scale- and position-independent by construction — each image
is cropped to its own chassis bounding box first, so the only thing that can
move a number is a real difference in the model. That matters because a
perspective render of a 19.7 x 19.7 x 9.5 cm block, framed by projected
bounding box rather than by the block, reads at h/w 0.75 instead of 0.48 and
every band taken from it is garbage.

Usage: python3 face_diff.py <mine.png> <apple.jpg> [label]
"""
import sys
import numpy as np
from PIL import Image

BANDS = 20


def chassis_crop(path, dark=95, metal_lo=150, metal_hi=172):
    """Crop to the chassis, return (grayscale, dark-mask, size).

    The two sources disagree about what the background is, so "bright =
    object" cannot be used: Apple's diagrams sit on white and the ortho render
    sits on a flat 0.55 grey world. A wide window around the metal captures the
    whole frame in the second case, because the world reads 175 and the lit
    aluminium 163 — only 12 levels apart, and a 26-level window swallows both.

    So: decide which side the background is on, then take a NARROW band on the
    other side of it. For the ortho renders the panel sits at 150..172; for
    Apple's diagrams the object is everything darker than the white paper.
    """
    a = np.asarray(Image.open(path).convert("L"), float)
    h, w = a.shape

    bg = float(np.median(np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])))
    if bg > 200:
        # white background: the object is the DARK part of the frame
        obj = a < bg - 12
    else:
        # grey world background: the object is the metal, just below it
        obj = (a >= metal_lo) & (a <= metal_hi)

    rows = np.where(obj.sum(axis=1) > w * 0.10)[0]
    cols = np.where(obj.sum(axis=0) > h * 0.10)[0]
    if not len(rows) or not len(cols):
        raise SystemExit("no chassis found in %s" % path)
    y0, y1, x0, x1 = rows[0], rows[-1], cols[0], cols[-1]

    sub = a[y0:y1 + 1, x0:x1 + 1]
    return sub, sub < dark, (x1 - x0, y1 - y0)


def profile(mask, n=BANDS, axis=0):
    out = []
    extent = mask.shape[axis]
    for i in range(n):
        a, b = int(extent * i / n), int(extent * (i + 1) / n)
        sl = mask[a:b] if axis == 0 else mask[:, a:b]
        out.append(sl.mean() * 100.0)
    return out


def main():
    mine_p, apple_p = sys.argv[1], sys.argv[2]
    label = sys.argv[3] if len(sys.argv) > 3 else "face"

    m_img, m_mask, m_size = chassis_crop(mine_p)
    a_img, a_mask, a_size = chassis_crop(apple_p)

    print("== %s ==" % label)
    print("mine  %4dx%4d px   h/w = %.4f" % (m_size[0], m_size[1], m_size[1] / m_size[0]))
    print("apple %4dx%4d px   h/w = %.4f" % (a_size[0], a_size[1], a_size[1] / a_size[0]))
    print("spec  19.70 x 9.50      h/w = %.4f" % (9.5 / 19.7))
    ratio_gap = abs(m_size[1] / m_size[0] - 9.5 / 19.7)
    print("proportion error: %+.4f  %s" % (ratio_gap, "OK" if ratio_gap < 0.02 else "<-- OFF"))
    print()

    mb = profile(m_mask, axis=0)
    ab = profile(a_mask, axis=0)
    print("dark-pixel share per %d%% band, top -> bottom" % (100 // BANDS))
    print("  band     apple     mine     diff")
    worst = 0.0
    for i, (a_, m_) in enumerate(zip(ab, mb)):
        d = m_ - a_
        worst = max(worst, abs(d))
        flag = "  <-- off" if abs(d) > 12 else ""
        print("  %2d-%2d%%  %6.1f  %6.1f  %+6.1f%s"
              % (i * 100 // BANDS, (i + 1) * 100 // BANDS, a_, m_, d, flag))
    print("\nworst band deviation: %.1f points" % worst)

    mc = profile(m_mask, axis=1)
    ac = profile(a_mask, axis=1)
    print("\ndark-pixel share per %d%% column, left -> right"
          % (100 // BANDS))
    print("  col      apple     mine     diff")
    for i, (a_, m_) in enumerate(zip(ac, mc)):
        d = m_ - a_
        flag = "  <-- off" if abs(d) > 12 else ""
        print("  %2d-%2d%%  %6.1f  %6.1f  %+6.1f%s"
              % (i * 100 // BANDS, (i + 1) * 100 // BANDS, a_, m_, d, flag))


if __name__ == "__main__":
    main()
