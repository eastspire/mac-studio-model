#!/usr/bin/env python3
"""Dump what chassis_box() and normalise_ref() actually produce, as images."""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from compare_render import chassis_box, normalise_ref, REF  # noqa: E402

OUT = os.path.join(ROOT, "renders", "compare")


def main():
    for name in ("apple_hw_back.jpg", "apple_static_front.jpg"):
        path = os.path.join(REF, name)
        im = Image.open(path)
        g = np.asarray(im.convert("L"), dtype=np.float32)
        x0, y0, x1, y1 = chassis_box(g)
        print("%s: image %s, box=(%d,%d,%d,%d) size=%dx%d"
              % (name, im.size, x0, y0, x1, y1, x1 - x0 + 1, y1 - y0 + 1))
        print("   aspect %.4f (want %.4f)"
              % ((x1 - x0 + 1) / float(y1 - y0 + 1), 197.0 / 95.0))
        crop = im.convert("RGB").crop((x0, y0, x1 + 1, y1 + 1))
        gg = np.asarray(crop.convert("L"), dtype=np.float32) / 255.0
        print("   crop grey: min %.3f p25 %.3f med %.3f p75 %.3f max %.3f"
              % (gg.min(), np.percentile(gg, 25), np.median(gg),
                 np.percentile(gg, 75), gg.max()))
        p = os.path.join(OUT, "cropbox_%s.png" % name.replace(".jpg", ""))
        crop.save(p)
        print("   wrote %s" % p)

        n = normalise_ref(path, 460)
        gn = np.asarray(n.convert("L"), dtype=np.float32) / 255.0
        print("   normalise_ref %s grey: med %.3f max %.3f"
              % (n.size, np.median(gn), gn.max()))
        p2 = os.path.join(OUT, "normref_%s.png" % name.replace(".jpg", ""))
        n.save(p2)
        print("   wrote %s" % p2)


if __name__ == "__main__":
    main()
