"""Is the perforated field actually see-through, or is there a back?

Vision reading a render will describe a perforated panel as "semi-transparent
with internals visible" whenever the holes are deep and the interior is
unlit, because the dark blob behind each hole is genuinely the inside of the
machine. That is what a hole looks like - it is not a transparency defect -
but the two are easy to confuse and the difference matters.

So cast rays at the field and report what each one meets, in order. A hole that
is backed by solid metal returns [skin, floor, solid]; a hole that goes all the
way through the empty case returns [skin, floor, <something far behind>].

usage: blender --background --factory-startup --python tools/probe_field.py
"""
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "blender"))
import mac_studio_spec as S  # noqa: E402

BLEND = os.path.join(ROOT, "blender", "mac_studio.blend")
DIST = 12.0          # cm: far more than the case is deep, so "nothing after
                     # the field" means the ray left through the back


def trace(p, d):
    out = []
    travelled = 0.0
    for _ in range(24):
        ok, loc, nrm, idx, obj, mtx = bpy.context.scene.ray_cast(
            bpy.context.evaluated_depsgraph_get(), p, d, distance=DIST)
        if not ok:
            break
        step = (Vector(loc) - p).length
        travelled += step
        out.append((obj.name, round(travelled, 3)))
        p = Vector(loc) + d * 1e-4
    return out


def main():
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    print("Rear field: 400 rays fired into the grille, from outside the case.\n")
    kinds = {}
    through = 0
    n = 20
    for i in range(n):
        for j in range(n):
            x = -S.UPPER_HALF_X + 2 * S.UPPER_HALF_X * (i + 0.5) / n
            z = S.UPPER_Z0 + (S.UPPER_Z1 - S.UPPER_Z0) * (j + 0.5) / n
            p = Vector((x, S.D / 2.0 + 2.0, z))
            hits = trace(p, Vector((0, -1, 0)))
            key = tuple(h[0] for h in hits)
            kinds[key] = kinds.get(key, 0) + 1
            # "through" = fewer than 2 surfaces met, or nothing solid behind
            if len(hits) < 2:
                through += 1
    total = n * n
    print("distinct surface sequences, most common first:")
    for k, v in sorted(kinds.items(), key=lambda t: -t[1])[:8]:
        print("  %4d x  %s" % (v, " -> ".join(k) if k else "(nothing)"))
    print("\n  rays that met nothing at all: %d / %d  (%.1f%%)"
          % (through, total, through * 100.0 / total))

    # The pass condition. A ray fired at the field is expected to MISS the
    # panel where it passes through a hole, and that miss is the feature
    # working. So the meaningful question is not "did the ray hit the grille
    # mesh" - at 1.4 mm holes sampled on a 20x20 grid over 171 mm, the grid
    # points mostly fall on the METAL between holes and hit bare Body, which
    # is correct and is not a defect.
    #
    # What would be a defect is a field that is solid, i.e. every ray
    # stopping at the skin. So the assertion is the opposite of the first
    # version of this probe: the field must be OPEN. Sampling where the rays
    # land matters, and a grid coarse enough to straddle the holes measures
    # the metal, not the perforation.
    #
    # Fire rays at the hole CENTRES. The field is STAGGERED (alternate rows
    # offset by UPPER_STAGGER * pitch), so a uniform grid does not land on
    # hole centres - it straddles the metal. Reproduce the stagger or the
    # probe measures the wrong thing again.
    hit_skin = 0
    total_holes = 0
    cols = int(2 * S.UPPER_HALF_X / S.UPPER_PITCH_X)
    rows = int((S.UPPER_Z1 - S.UPPER_Z0) / S.UPPER_PITCH_Z)
    for iy in range(rows):
        z = S.UPPER_Z0 + S.UPPER_PITCH_Z * (iy + 0.5)
        shift = (S.UPPER_STAGGER * S.UPPER_PITCH_X) if (iy % 2) else 0.0
        for ix in range(cols + 1):
            x = -S.UPPER_HALF_X + S.UPPER_PITCH_X * (ix + 0.5) + shift
            if abs(x) > S.UPPER_HALF_X - S.UPPER_HOLE_R:
                continue
            total_holes += 1
            hits = trace(Vector((x, S.D / 2.0 + 2.0, z)), Vector((0, -1, 0)))
            # a hole is open if the ray got past the skin: either it met
            # nothing, or its first hit is deeper than the recess
            if not hits or hits[0][1] > S.UPPER_DEPTH + 0.01:
                hit_skin += 0        # open
            else:
                hit_skin += 1        # blocked at the skin
    open_share = 1.0 - hit_skin / float(max(total_holes, 1))
    print("\n  rays fired AT HOLE CENTRES: %d" % total_holes)
    print("    reached past the skin: %d  (%.1f%%)"
          % (total_holes - hit_skin, open_share * 100))
    ok = open_share > 0.5
    print()
    print("  Pass condition: a perforated field is OPEN, so most rays aimed at")
    print("  a hole's centre must reach past the skin into the fan bay. A low")
    print("  number here is the real defect - the field is solid, and the panel")
    print("  reads as smooth metal no matter how many holes the log claims.")
    print("\n%s" % ("FIELD OK" if ok
                    else "FIELD FAILED — the field is not actually perforated"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
