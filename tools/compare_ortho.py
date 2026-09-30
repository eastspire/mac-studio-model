#!/usr/bin/env python3
"""Compare the model's orthographic elevations against Apple's own diagrams.

The comparison is only meaningful if both images are on the same chassis box
and both are the object alone. So:

  * the ortho renders are RGBA on a transparent film, so the ALPHA channel
    gives the object mask exactly - no background median heuristic, which is
    what previously found the lit floor and reported every elevation as
    "clipped";
  * Apple's diagram is cropped by its own detected chassis box;
  * the chassis aspect is printed FIRST, as the canary. If it is wrong the
    crop failed and no zone number from that run means anything.

Each zone is then split on its OWN two modes (Otsu within that zone), so the
number is a physical open area rather than a lighting artefact - a fixed cut
is defeated by any lighting difference between a render and a JPEG.
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
ORTHO = os.path.join(ROOT, "renders", "ortho")
W_MM, H_MM = 197.0, 95.0
WANT_ASPECT = W_MM / H_MM

# Apple's own assets, downloaded at 2x from the live product page.
REF = {
    "rear": os.path.join(ROOT, "reference", "apple_x2", "hw_back_x2.jpg"),
    "front": os.path.join(ROOT, "reference", "apple_x2", "hw_front_x2.jpg"),
    "right": None,      # Apple publishes no side elevation
    "left": None,
    "top": None,
    "bottom": None,
}

# Measured off apple_hw_back.jpg: mm from the top of the chassis. See
# docs/VERIFICATION.md, "Panel layout".
REAR_ZONES = [
    ("top field", 4.7, 52.8),
    ("solid", 52.8, 62.9),
    ("port row", 62.9, 79.3),
    ("solid", 79.3, 87.4),
    ("base band", 87.4, 95.0),
]
FRONT_ZONES = [
    ("solid", 4.7, 52.8),
    ("solid", 52.8, 62.9),
    ("port row", 62.9, 79.3),
    ("solid", 79.3, 87.4),
    ("base band", 87.4, 95.0),
]


def otsu(block):
    x = np.asarray(block, dtype=np.float64).ravel()
    hist, _ = np.histogram(x, bins=64, range=(0.0, 1.0))
    tot = hist.sum()
    w = np.cumsum(hist)
    m = np.cumsum(hist * np.arange(64))
    mt = m[-1]
    den = w * (tot - w)
    with np.errstate(divide="ignore", invalid="ignore"):
        sig = np.where(den > 0, (mt * w - tot * m) ** 2 / den, 0.0)
    return (int(np.argmax(sig)) + 0.5) / 64.0


def normalise(block):
    """Rescale a zone to its own 2nd..98th percentile range.

    The comparison has to be lighting-independent, and it cannot be: the
    render comes out at a mean luminance of 0.21 where Apple's photograph
    sits at 0.64, because a metallic panel under a flat studio world is not
    exposed like a lit product photograph. An Otsu split is only invariant to
    that if the two images' zones span the same range - otherwise the cut
    lands in a different place in each and the "open area" is meaningless.
    Measured on the port row: the model's own structure is clearly present
    and correctly shaped, but an adaptive cut called 99.6% of it dark while
    the photograph's correctly-lit equivalent called 0.2%.

    Percentile rather than min/max, so a handful of specular highlights or
    JPEG ringing cannot set the scale.
    """
    lo = float(np.percentile(block, 2))
    hi = float(np.percentile(block, 98))
    if hi - lo < 1e-6:
        return np.zeros_like(block)
    return np.clip((block - lo) / (hi - lo), 0.0, 1.0)


def open_area(block):
    """The share of a zone that belongs to its DARKER mode, after normalising.

    Otsu alone is not enough, and the failure is worth stating because it
    produced a table that read as a total model failure. In the perforated
    field the two classes are the holes and the metal between them; on an
    underexposed render the classes merge, Otsu picks an arbitrary cut, and
    the resulting "open area" lands near 99% - indistinguishable from a model
    that is 99% hole.

    Returns (adaptive_share, fixed_share, bimodality). The adaptive share is
    the number to compare; the fixed one is a cross-check and bimodality says
    whether the split means anything at all.
    """
    if block.size == 0:
        return float("nan"), float("nan"), 0.0
    n = normalise(block)
    t = otsu(n)
    lo, hi = n[n < t], n[n >= t]
    if lo.size < 20 or hi.size < 20:
        valley = 0.0
    else:
        valley = float(np.percentile(hi, 10) - np.percentile(lo, 90))
    return float((n < t).mean()), float((n < 0.5).mean()), valley


def model_gray(name):
    """The ortho render, cropped to its alpha mask, scaled to the chassis box."""
    p = os.path.join(ORTHO, name + ".png")
    im = Image.open(p).convert("RGBA")
    a = np.asarray(im)[:, :, 3]
    ys, xs = np.nonzero(a > 8)
    if len(ys) == 0:
        return None, None
    w = int(xs.max() - xs.min() + 1)
    h = int(ys.max() - ys.min() + 1)
    grey = np.asarray(im.convert("L"), dtype=np.float64) / 255.0
    crop = grey[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    # Put both images on the same 197 x 95 box.
    tw = 1305
    th = int(round(tw * H_MM / W_MM))
    crop = np.asarray(Image.fromarray((crop * 255).astype(np.uint8))
                      .resize((tw, th), Image.Resampling.LANCZOS), dtype=np.float64) / 255.0
    return crop, (w, h)


def ref_gray(path):
    """Apple's diagram, cropped to its detected chassis box, on the same box."""
    g = np.asarray(Image.open(path).convert("L"), dtype=np.float64) / 255.0
    # The diagram sits on a light background; take the bright-ish object by
    # its own border contrast, then fit the published 197:95 aspect.
    border = np.concatenate([g[0, :], g[-1, :], g[:, 0], g[:, -1]])
    bg = float(np.median(border))
    mask = np.abs(g - bg) > 0.012
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return None, None
    w = int(xs.max() - xs.min() + 1)
    h = int(ys.max() - ys.min() + 1)
    crop = g[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    # The detected box includes the contact shadow, which is why this image
    # reads taller than 197:95. Trim the extra height off the bottom, where
    # the shadow always is, by scaling to the WIDTH and taking the top.
    tw = 1305
    th = int(round(tw * H_MM / W_MM))
    crop = np.asarray(Image.fromarray((crop * 255).astype(np.uint8))
                      .resize((tw, th), Image.Resampling.LANCZOS), dtype=np.float64) / 255.0
    return crop, (w, h)


def zone_table(view, mine, theirs, zones, margin_px=34):
    sx = 1305.0 / W_MM
    print("\n%s" % view)
    print("  %-11s %-14s %8s %8s %7s   %8s %8s"
          % ("zone", "mm from top", "apple", "model", "diff", "apple@fix", "model@fix"))
    worst = 0.0
    for name, a, b in zones:
        r0, r1 = int(round(a * sx)), int(round(b * sx))
        blk_m = mine[r0:r1, margin_px:1305 - margin_px]
        blk_a = theirs[r0:r1, margin_px:1305 - margin_px]
        if blk_m.size == 0 or blk_a.size == 0:
            continue
        ma, fa, va = open_area(blk_a)
        mm_, fm, vm = open_area(blk_m)
        d_fixed = (fm - fa) * 100
        worst = max(worst, abs(d_fixed))
        print("  %-11s %5.1f..%-6.1f %7.1f%% %7.1f%% %+6.1f   %7.1f%% %7.1f%%"
              % (name, a, b, ma * 100, mm_ * 100, (mm_ - ma) * 100,
                 fa * 100, fm * 100))
        if name.endswith("field") or name == "base band":
            print("      bimodality: apple %.3f  model %.3f   (near 0 => the"
                  " classes merged and the adaptive split is void)"
                  % (va, vm))
    return worst


def main():
    views = sys.argv[1:] or ["rear", "front"]
    overall = 0.0
    for v in views:
        mine, mbox = model_gray(v)
        if mine is None:
            print("%s: no ortho render" % v)
            continue
        print("=" * 64)
        print("VIEW %s   model box %dx%d px  aspect %.3f  (chassis is %.3f)"
              % (v, mbox[0], mbox[1], mbox[0] / float(mbox[1]), WANT_ASPECT))
        if REF.get(v) is None:
            print("  Apple publishes no %s elevation - nothing to diff" % v)
            print("  (rendered anyway: %dx%d px, aspect %.3f)"
                  % (mbox[0], mbox[1], mbox[0] / float(mbox[1])))
            continue
        theirs, rbox = ref_gray(REF[v])
        print("  apple box %dx%d px  aspect %.3f" % (rbox[0], rbox[1],
                                                    rbox[0] / float(rbox[1])))
        zones = REAR_ZONES if v == "rear" else FRONT_ZONES
        overall = max(overall, zone_table(v, mine, theirs, zones))
    print("\n" + "=" * 64)
    print("worst zone deviation: %.1f points" % overall)
    return 0


if __name__ == "__main__":
    sys.exit(main())
