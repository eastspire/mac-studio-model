#!/usr/bin/env python3
"""Side-by-side and blink overlay of the base band, photograph against model.

The band is the one region whose dark share disagrees by more than the
tolerance, and a number alone cannot say why. Stacking the two crops at the
same magnification settles it: if the model's holes sit in the same places at
the same size, the disagreement is shading - the photograph's 1.3 mm recess
throws its own web into shadow - and the geometry is right.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from compare_render import normalise_ref, otsu, REF, OUT  # noqa: E402

W_MM, H_MM = 197.0, 95.0
ZOOM = 6


def band_crop(g, sx, x_mm, half_mm, lo_mm, hi_mm):
    h, w = g.shape
    c = int(round(x_mm / sx))
    a = max(0, int(round(lo_mm / sx)))
    b = min(h, int(round(hi_mm / sx)))
    p = max(0, c - int(round(half_mm / sx)))
    q = min(w, c + int(round(half_mm / sx)))
    return g[a:b, p:q], a, p


def main():
    for view, ref_file in (("rear", "apple_hw_back.jpg"),
                           ("front", "apple_static_front.jpg")):
        rimg = normalise_ref(os.path.join(REF, ref_file), 460)
        gr = np.asarray(rimg.convert("L"), dtype=np.float32) / 255.0
        sx = W_MM / gr.shape[1]
        mp = os.path.join(OUT, "%s_model.png" % view)
        if not os.path.exists(mp):
            continue
        gm = np.asarray(Image.open(mp).convert("L").resize(rimg.size,
                                                           Image.LANCZOS),
                        dtype=np.float32) / 255.0
        smx = W_MM / gm.shape[1]

        rb, ra, rp = band_crop(gr, sx, 98.5, 14.0, 85.0, 95.0)
        mb, ma, mp_ = band_crop(gm, smx, 98.5, 14.0, 85.0, 95.0)
        print("\n%s  ref crop %s at %.4f mm/px, model crop %s at %.4f mm/px"
              % (view, rb.shape, sx, mb.shape, smx))
        for tag, b in (("ref", rb), ("model", mb)):
            t, e = otsu(b)
            print("   %-5s otsu %.3f  open %5.1f%%  min %.3f max %.3f"
                  % (tag, t, (b < t).mean() * 100, b.min(), b.max()))

        h = max(rb.shape[0], mb.shape[0])
        stack = Image.new("L", (rb.shape[1] + mb.shape[1] + 12, h), 255)
        stack.paste(Image.fromarray((np.clip(rb, 0, 1) * 255).astype(np.uint8)),
                    (0, 0))
        stack.paste(Image.fromarray((np.clip(mb, 0, 1) * 255).astype(np.uint8)),
                    (rb.shape[1] + 12, 0))
        big = stack.resize((stack.size[0] * ZOOM, stack.size[1] * ZOOM),
                           Image.NEAREST).convert("RGB")
        d = ImageDraw.Draw(big)
        d.line([(rb.shape[1] * ZOOM + 6, 0), (rb.shape[1] * ZOOM + 6,
                                               big.size[1])],
               fill=(255, 0, 0), width=2)
        d.text((6, 4), "APPLE", fill=(255, 0, 0))
        d.text((rb.shape[1] * ZOOM + 14, 4), "MODEL", fill=(255, 0, 0))
        for mm in range(86, 95, 2):
            yy = int((mm - 85.0) / sx) * ZOOM
            if 0 <= yy < big.size[1]:
                d.line([(0, yy), (big.size[0], yy)], fill=(0, 140, 255))
                d.text((6, yy + 1), "%d" % mm, fill=(0, 140, 255))
        p = os.path.join(OUT, "bandstack_%s.png" % view)
        big.save(p)
        print("   wrote %s  %s" % (p, big.size))


if __name__ == "__main__":
    main()
