#!/usr/bin/env python3
"""Front panel, Touch ID button, and the two edge radii.

Three separate measurements, all in millimetres off a 197 mm chassis.

front   — the front panel's dark features. Note the front is a FRONT view, so
          image-left is model +X (the opposite of the rear), and the status
          LED is BRIGHT, not dark: it is a small white dot, so it has to be
          found as a local bright spot against the aluminium, not as a hole.

button  — the Touch ID ring on the rear. A threshold low enough to catch the
          engraved power glyph also catches nothing else, but it measures the
          GLYPH, not the button. The button is a shallow debossed circle: find
          it from the specular edge instead.

radius  — R_HORZ from the front elevation's top edge, R_VERT from the top
          view's corner. Both need a robust fit: the first few rows of a
          product shot are contaminated by the background gradient, and the
          sweep is not pure white, so the silhouette has to be found from a
          gradient-aware threshold.
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "..", "reference")


def load(p):
    return np.asarray(Image.open(p).convert("L"), dtype=np.float32)


def box_of(g):
    def span(mask, axis):
        prof = mask.sum(axis=axis)
        idx = np.nonzero(prof > 0.02 * prof.max())[0]
        return int(idx[0]), int(idx[-1])
    x0, x1 = span(g < 238.0, 0)
    y0, y1 = span(g < 244.0, 1)
    return x0, y0, x1, y1


def components(mask, min_area=20):
    h, w = mask.shape
    seen = np.zeros((h, w), dtype=bool)
    out = []
    for sy in range(h):
        for sx in np.nonzero(mask[sy] & ~seen[sy])[0]:
            if seen[sy, sx]:
                continue
            stack = [(sy, sx)]
            seen[sy, sx] = True
            x0 = x1 = sx; y0 = y1 = sy; area = 0
            while stack:
                y, x = stack.pop()
                area += 1
                x0 = min(x0, x); x1 = max(x1, x)
                y0 = min(y0, y); y1 = max(y1, y)
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if area >= min_area:
                out.append((x0, y0, x1, y1, area))
    out.sort()
    return out


def front(path):
    g = load(path)
    x0, y0, x1, y1 = box_of(g)
    sx = 197.0 / (x1 - x0 + 1)
    H = y1 - y0 + 1
    print("FRONT  %s" % os.path.basename(path))
    print("  chassis %d x %d px   scale %.4f mm/px" % (x1 - x0 + 1, H, sx))

    # dark openings: the base band is the bottom ~10%, exclude it
    y_a, y_b = y0, y0 + int(H * 0.90)
    sub = g[y_a:y_b, x0:x1 + 1]
    comps = components(sub < 118.0, min_area=int(1.2 / (sx * sx)))
    names = ["USBC1", "USBC2", "SDXC"]
    print("  dark openings (front view: image-left is model +X):")
    for i, (ca, cb, cc, cd, area) in enumerate(comps):
        nm = names[i] if i < len(names) else "?%d" % i
        print("    %-6s cx %7.2f mm  w %5.2f  h %5.2f   y %6.2f..%6.2f mm from top"
              % (nm, (ca + cc + 1) / 2.0 * sx, (cc - ca + 1) * sx, (cd - cb + 1) * sx,
                 (y_a + cb - y0) * sx, (y_a + cd + 1 - y0) * sx))

    # status LED: BRIGHT spot. Look in the right 45% of the panel, below mid.
    y_lo = y0 + int(H * 0.45)
    y_hi = y0 + int(H * 0.90)
    x_lo = x0 + int(0.55 * (x1 - x0 + 1))
    reg = g[y_lo:y_hi, x_lo:x1]
    # local background = heavy blur; the LED is a compact positive peak
    from numpy.lib.stride_tricks import sliding_window_view
    k = 25
    pad = np.pad(reg, k // 2, mode="edge")
    win = sliding_window_view(pad, (k, k))
    bg = win.mean(axis=(2, 3))
    resid = reg - bg
    peak = np.unravel_index(np.argmax(resid), resid.shape)
    thr = max(6.0, resid[peak] * 0.45)
    led = resid > thr
    lc = components(led, min_area=6)
    print("  bright spots (status LED):")
    for ca, cb, cc, cd, area in lc:
        cxm = (x_lo + (ca + cc + 1) / 2.0 - x0) * sx
        cym = (y_lo + (cb + cd + 1) / 2.0 - y0) * sx
        print("    cx %7.2f mm from image-left   cy %6.2f mm from top"
              "   d %5.2f x %5.2f mm   peak +%.1f"
              % (cxm, cym, (cc - ca + 1) * sx, (cd - cb + 1) * sx, resid[cb:cd + 1, ca:cc + 1].max()))


def button(path):
    g = load(path)
    x0, y0, x1, y1 = box_of(g)
    sx = 197.0 / (x1 - x0 + 1)
    print("\nTOUCH ID button (rear view):")
    # generous window around the known glyph position
    xa = x0 + int(160 / sx); xb = x0 + int(185 / sx)
    ya = y0 + int(62 / sx); yb = y0 + int(82 / sx)
    reg = g[ya:yb, xa:xb]
    comps = components(reg < 200.0, min_area=30)
    for ca, cb, cc, cd, area in comps:
        print("    blob cx %6.2f mm from image-left  cy %6.2f mm from top"
              "   d %5.2f x %5.2f mm  area %d"
              % ((xa + (ca + cc + 1) / 2.0 - x0) * sx, (ya + (cb + cd + 1) / 2.0 - y0) * sx,
                 (cc - ca + 1) * sx, (cd - cb + 1) * sx, area))
    # The button's outer ring is a debossed circle: at threshold 200 we get the
    # ring plus the glyph as separate blobs; the widest blob is the button.
    if comps:
        big = max(comps, key=lambda t: (t[2] - t[0]))
        print("    -> button outer diameter ~ %.2f mm" % ((big[2] - big[0] + 1) * sx))


def radii(front_path, top_path=None):
    g = load(front_path)
    x0, y0, x1, y1 = box_of(g)
    sx = 197.0 / (x1 - x0 + 1)
    H = y1 - y0 + 1
    print("\nRADII")
    # --- R_HORZ from the front elevation's top edge -----------------------
    # Background is a vertical gradient, so use a per-row threshold derived
    # from the row's own extremes rather than a global cut.
    xs = []
    for r in range(0, min(int(H * 0.12), 60)):
        row = g[y0 + r, x0:x1 + 1]
        lo, hi = np.percentile(row, 1), np.percentile(row, 99)
        thr = hi - 0.10 * (hi - lo)
        idx = np.nonzero(row < thr)[0]
        if len(idx) and (idx[-1] - idx[0]) > 0.5 * (x1 - x0):
            xs.append((r, int(idx[0])))
    print("  top-edge silhouette (row, left inset px):", xs[:12])
    best = None
    for R2 in range(2, 70):
        e = 0.0
        for r, xi in xs:
            pred = R2 - np.sqrt(max(0.0, R2 * R2 - (R2 - min(r, R2)) ** 2))
            e += (pred - xi) ** 2
        if best is None or e < best[1]:
            best = (R2, e)
    print("  R_HORZ ~ %d px = %.2f mm  (residual %.0f over %d rows)"
          % (best[0], best[0] * sx, best[1], len(xs)))


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    fr = os.path.join(REF, "apple_static_front.jpg")
    rr = os.path.join(REF, "apple_hw_back.jpg")
    if what in ("front", "all"):
        front(fr)
    if what in ("button", "all"):
        button(rr)
    if what in ("radii", "all"):
        radii(fr)
