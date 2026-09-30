#!/usr/bin/env python3
"""Save an enlarged crop of the reference bottom edge, with mm rules.

The row profile reports a large dark share in the reference 79-86 mm below the
top edge on both panels, and the separability says the histogram really is
bimodal there. So something IS down there and it should simply be looked at
rather than inferred.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from compare_render import normalise_ref, REF  # noqa: E402

REFS = {"rear": "apple_hw_back.jpg", "front": "apple_static_front.jpg"}
OUT_H = 460
OUT = os.path.join(ROOT, "renders", "compare")


def main():
    for view in ("rear", "front"):
        img = normalise_ref(os.path.join(REF, REFS[view]), OUT_H).convert("RGB")
        w, h = img.size
        y0 = int(round(72.0 / 95.0 * h))
        crop = img.crop((0, y0, w, h))
        # 2x nearest so individual pixels stay countable
        big = crop.resize((w * 2, (h - y0) * 2), Image.NEAREST)
        d = ImageDraw.Draw(big)
        for mm in range(72, 96, 2):
            yy = int(round((mm - 72.0) / 95.0 * h)) * 2
            d.line([(0, yy), (big.size[0], yy)], fill=(255, 0, 0), width=1)
            d.text((6, yy + 2), "%d mm" % mm, fill=(255, 0, 0))
        p = os.path.join(OUT, "bottomstrip_%s.png" % view)
        big.save(p)
        print("wrote %s  %s  (rows 72..95 mm)" % (p, big.size))

        # the same strip from the model render, for a side-by-side
        mp = os.path.join(OUT, "%s_model.png" % view)
        if os.path.exists(mp):
            mi = Image.open(mp).convert("RGB")
            mh = mi.size[1]
            my0 = int(round(72.0 / 95.0 * mh))
            mc = mi.crop((0, my0, mi.size[0], mh))
            mbig = mc.resize((mi.size[0] * 2, (mh - my0) * 2), Image.NEAREST)
            dd = ImageDraw.Draw(mbig)
            for mm in range(72, 96, 2):
                yy = int(round((mm - 72.0) / 95.0 * mh)) * 2
                dd.line([(0, yy), (mbig.size[0], yy)], fill=(255, 0, 0), width=1)
                dd.text((6, yy + 2), "%d mm" % mm, fill=(255, 0, 0))
            p2 = os.path.join(OUT, "bottomstrip_%s_model.png" % view)
            mbig.save(p2)
            print("wrote %s  %s" % (p2, mbig.size))


if __name__ == "__main__":
    main()
