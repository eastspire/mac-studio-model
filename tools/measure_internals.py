#usr/bin/env python3
"""Where the internal layers sit, read off Apple's cutaway renders.

The spec's FAN_Z, HEATSINK_Z, PIPE_Z, PCB_Z and PSU_Z were placed by eye
against these images. Eye is not a measurement, so this prints the row profile
of each X-ray next to the same axis with the model's own layer heights marked,
and the two can be read against each other in one place.

The anchor is the same as in the exterior work: left and right from the case
silhouette, bottom from the silhouette, height DERIVED from the width at
197:95. Both vertical anchors are found the same way in all four images to
within 2 px, which at 0.30 mm/px is 0.6 mm - well under what this can resolve.

A caveat worth stating: these are Apple's rendered cutaways, not photographs.
They are a different kind of picture from the flat-lay references, the case
walls are semi-transparent, and there is no perspective correction. Treat the
numbers as a layout check - is the blowers/heatsink/board/supply stack in the
right order and roughly the right size - and not as a 0.1 mm measurement.
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))
REF = os.path.join(ROOT, "reference", "hk")

import mac_studio_spec as S                 # noqa: E402
from xray_grid import chassis_box, SHOTS    # noqa: E402
from PIL import Image                       # noqa: E402

W_MM, H_MM = 197.0, 95.0

# name -> (spec cm from the bottom, half-height in cm, what it is)
LAYERS = [
    ("blower top", S.FAN_Z + S.FAN_SHROUD_H / 2, S.FAN_SHROUD_H / 2,
     "top of the two fan shrouds"),
    ("blower mid", S.FAN_Z, S.FAN_SHROUD_H / 2, "fan axis"),
    ("blower bot", S.FAN_Z - S.FAN_SHROUD_H / 2, S.FAN_SHROUD_H / 2,
     "bottom of the fan shrouds"),
    ("heatsink", S.HEATSINK_Z, 0.45, "finned heatsink"),
    ("pipes", S.PIPE_Z, 0.35, "copper heat-pipe plane"),
    ("board", S.PCB_Z, 0.25, "logic board"),
    ("psu", S.PSU_Z, 0.85, "power supply"),
]


def profile(name):
    im = Image.open(os.path.join(REF, name)).convert("L")
    g = np.asarray(im, dtype=np.float64) / 255.0
    x0, y0, x1, y1, h = chassis_box(g)
    crop = g[y0:y1 + 1, x0:x1 + 1]
    # drop the outer 4 mm: the case walls are a bright rim and would dominate
    m = int(round(4.0 / (W_MM / crop.shape[1])))
    inner = crop[:, m:crop.shape[1] - m]

    # A dark-share threshold is useless here and returns 100% on every row: the
    # cutaway interior is almost all dark, and the few bright things in it - the
    # copper plane, the port shells - are a small minority, so any cut between
    # the 2nd and 98th percentile sits above the entire picture. What actually
    # distinguishes one layer from the next is TEXTURE, not level: the blower
    # shrouds are a dense forest of fins and have by far the highest vertical
    # edge density in the machine, and the copper plane is the one bright
    # horizontal slab. So: edge density as the structural channel, row mean as
    # the copper channel.
    edge = np.abs(np.diff(inner, axis=0, prepend=inner[:1])).mean(axis=1)
    edge /= max(edge.max(), 1e-9)
    bright = inner.mean(axis=1)
    bright = (bright - bright.min()) / max(bright.max() - bright.min(), 1e-9)
    return crop, edge, bright, W_MM / crop.shape[1]


def main():
    for name in (sys.argv[1:] or SHOTS[:2]):
        crop, edge, bright, mm_px = profile(name)
        print("\n=== %s   %d rows, %.3f mm/px ===" % (name, crop.shape[0], mm_px))
        print("    # = edge density (fins and components), + = row brightness"
              " (the copper plane). 1 mm steps.\n")
        marks = {}
        for lab, z, _, _ in LAYERS:
            marks.setdefault(round((H_MM - z * 10) / mm_px), lab)
        for r in range(0, crop.shape[0], max(1, int(round(1.0 / mm_px)))):
            mm_top = r * mm_px
            bar = "#" * int(round(edge[r] * 40))
            bar += " " * (40 - len(bar))
            bar += "+" * int(round(bright[r] * 12))
            tag = marks.get(r, "")
            if tag:
                tag = "   <-- model: %s" % tag
            print("   %5.1f mm |%s|%3d%%%s" % (mm_top, bar, int(edge[r] * 100), tag))


if __name__ == "__main__":
    main()
