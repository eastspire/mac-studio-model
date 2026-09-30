#!/usr/bin/env python3
"""Debug the row-band profile: it printed one constant value for all 48 bands."""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from compare_render import normalise_ref, otsu, REF, OUT  # noqa: E402

W_MM, H_MM = 197.0, 95.0


def main():
    ref = normalise_ref(os.path.join(REF, "apple_hw_back.jpg"), 460)
    mod = Image.open(os.path.join(OUT, "rear_model.png")).convert("RGB")
    mod = mod.resize(ref.size, Image.LANCZOS)
    gr = np.asarray(ref.convert("L"), dtype=np.float32) / 255.0
    gm = np.asarray(mod.convert("L"), dtype=np.float32) / 255.0
    h = gr.shape[0]
    step = max(2, int(round(0.5 / H_MM * h)))
    print("ref %s  model %s  h=%d  step=%d" % (gr.shape, gm.shape, h, step))

    print("\n  y   mm     ref:thr eta  share | model:thr eta  share")
    for y in range(0, h - step + 1, step * 12):
        tr, er = otsu(gr[y:y + step])
        tm, em = otsu(gm[y:y + step])
        print("  %3d %5.1f   %.3f %.2f %5.1f  |  %.3f %.2f %5.1f"
              % (y, y * H_MM / h, tr, er, (gr[y:y + step] < tr).mean() * 100,
                 tm, em, (gm[y:y + step] < tm).mean() * 100))

    rrow = np.zeros(h)
    trusted = np.zeros(h, dtype=bool)
    for y in range(0, h - step + 1, step):
        tr, er = otsu(gr[y:y + step])
        if er < 0.50:
            continue
        rrow[y:y + step] = (gr[y:y + step] < tr).mean()
        trusted[y:y + step] = True
    print("\nrrow before interp: min %.3f max %.3f, trusted rows %d/%d"
          % (rrow.min(), rrow.max(), trusted.sum(), h))
    xs = np.linspace(0, 1, 48)
    idx = np.linspace(0, h - 1, h)
    r = np.interp(xs, idx, rrow)
    print("rrow after interp : min %.3f max %.3f" % (r.min(), r.max()))
    print("band values:", " ".join("%3d" % round(v * 100) for v in r))


if __name__ == "__main__":
    main()
