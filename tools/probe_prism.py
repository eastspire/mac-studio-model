"""Probe the prism geometry without a full build.

Loads the saved .blend, rebuilds ONE row of prisms by hand at a known place
on the rear panel, tries each candidate span, and reports which one the
existing hollow_body cavity actually accepts.

The full build takes five minutes because of the booleans; this takes
seconds, so the span can be searched instead of guessed.
"""
import math
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, "/Users/sqs/code/mac-studio-model/blender")
import mac_studio_spec as S  # noqa: E402

BLEND = "/Users/sqs/code/mac-studio-model/blender/mac_studio.blend"


def chain(sc, dg, x, z):
    """What a ray straight in from outside the rear panel meets."""
    org = Vector((x, -S.D / 2.0 - 1.0, z))
    d = Vector((0, 1, 0))
    p = org.copy()
    out = []
    for _ in range(6):
        hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, p, d)
        if not hit:
            out.append(("VOID", None))
            break
        out.append((ob.name, loc.y))
        p = loc + d * 0.0002
    return out


def main():
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    for n in ("BounceL", "BounceR", "Floor"):
        o = bpy.data.objects.get(n)
        if o:
            o.hide_viewport = True
    sc = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()

    skin = S.D / 2.0
    cavity = S.D / 2.0 - S.WALL
    floor = S.D / 2.0 - S.UPPER_DEPTH
    z = (S.UPPER_Z0 + S.UPPER_Z1) / 2.0

    print("skin      %+.4f" % -skin)
    print("floor     %+.4f   (skin - UPPER_DEPTH)" % -floor)
    print("cavity    %+.4f   (skin - WALL)" % -cavity)
    print()
    print("a ray at a BRIDGE between holes, x=0, z=%.3f:" % z)
    for name, y in chain(sc, dg, 0.0, z):
        print("    %-14s %s" % (name, "%+.4f" % y if y is not None else ""))

    print()
    print("the walk sits at |x| or |y| = %.4f, so a prism placed there must"
          % floor)
    print("reach the skin at %.4f: that is %.4f outward, plus %.4f of wall"
          % (skin, floor - skin, S.WALL))
    print("total span %.4f cm = %.2f mm" % (floor - cavity, (floor - cavity) * 10))
    return 0


main()
