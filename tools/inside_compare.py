#usr/bin/env python3
"""The model's cutaway next to Apple's, at the same scale, layer by layer.

A pixel profile of the X-ray was tried and abandoned: those images are Apple's
rendered cutaways, not photographs, and the interior is JPEG-flattened enough
that an edge-density profile returns near zero on the fin stacks and a flat
line on the copper plane. They support a LAYOUT reading - which layer sits on
which, and roughly how thick each is - and nothing finer. So this puts the two
pictures side by side on a common chassis box and lets the comparison be visual,
which is what the reference is good enough for.

The model's cutaway comes from tools/compare_render.py's own SDF, i.e. from the
same spec the Blender build imports, so what is compared here is the spec's
internals against Apple's, not a private drawing.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))
REF = os.path.join(ROOT, "reference", "hk")
OUT = os.path.join(ROOT, "renders", "compare")
W_MM, H_MM = 197.0, 95.0

import compare_render as CR                 # noqa: E402

PAIRS = [
    # The X-ray set is a FRONT cutaway, so the model's front cutaway is the
    # one that can be laid against it.  cut_rear is kept for the port side,
    # where it is genuinely the same face.
    ("cut_front", "hw_elements_fans_xray.jpg"),
    ("cut_front", "hw_elements_case_xray.jpg"),
    ("cut_front", "hw_elements_foot_xray.jpg"),
    ("cut_rear", "hw_elements_case_xray.jpg"),
    ("cut_side", "hw_elements_foot_xray.jpg"),
]


def box_from_width(x0, x1):
    """A 197:95 box from a width, anchored top-left at x0."""
    w = x1 - x0 + 1
    return x0, x0, w, int(round(w * H_MM / W_MM))


def main():
    made = []
    for view, ref in PAIRS:
        rp = os.path.join(REF, ref)
        mp = os.path.join(OUT, "%s_model_full.png" % view)
        if not (os.path.exists(rp) and os.path.exists(mp)):
            print("skip %s vs %s (missing %s)"
                  % (view, ref, rp if not os.path.exists(rp) else mp))
            continue

        rim = Image.open(rp).convert("L")
        g = np.asarray(rim, dtype=np.float64) / 255.0
        col = g.mean(axis=0)
        lo, hi = np.percentile(col, 5), np.percentile(col, 95)
        dark = col < lo + 0.30 * (hi - lo)
        runs, start = [], None
        for i, v in enumerate(dark):
            if v and start is None:
                start = i
            elif not v and start is not None:
                if i - start > 20:
                    runs.append((start, i - 1))
                start = None
        if start is not None:
            runs.append((start, len(dark) - 1))
        rx0, rx1 = runs[0][0], runs[-1][1]
        rw = rx1 - rx0 + 1
        rh = int(round(rw * H_MM / W_MM))

        model = Image.open(mp).convert("RGB")
        # The render maps model space to pixels linearly, so the model's box is
        # computed rather than detected. Detecting it in the render is what put
        # the first attempt's lower half off the sheet: the render has a 3 cm
        # margin, the silhouette's darkest run is the cut edge rather than the
        # skin, and a threshold that finds it does not find the bottom.
        key = view[len("cut_"):]
        mW, mH = model.size
        mx0, my0, mx1, my1 = CR.model_chassis_box(key, mW, mH)
        mw, mh = mx1 - mx0 + 1, my1 - my0 + 1

        W = 900
        a = rim.crop((rx0, 0, rx0 + rw, rh)).resize(
            (W, int(W * H_MM / W_MM)), Image.LANCZOS)
        b = model.crop((mx0, my0, mx0 + mw, my0 + mh)).resize(
            (W, int(W * H_MM / W_MM)), Image.LANCZOS)
        gap = 26
        sheet = Image.new("RGB", (W, 2 * a.height + gap), (255, 255, 255))
        sheet.paste(a.convert("RGB"), (0, 0))
        sheet.paste(b, (0, a.height + gap))
        d = ImageDraw.Draw(sheet)
        d.text((8, 4), "APPLE  %s   (%.3f mm/px in the source)" % (ref, W_MM / rw),
               fill=(20, 20, 130))
        d.text((8, a.height + gap + 4),
               "MODEL  %s cutaway, offline SDF from the spec   (%.3f mm/px)"
               % (view, W_MM / mw), fill=(130, 20, 20))
        d.line([(0, a.height + gap // 2), (W, a.height + gap // 2)],
               fill=(0, 0, 0))
        p = os.path.join(OUT, "inside_%s_vs_%s.png" % (view, ref.split(".")[0]))
        sheet.save(p)
        made.append(p)
        print("%-18s vs %-30s -> %s" % (view, ref, os.path.basename(p)))
    return made


if __name__ == "__main__":
    main()
