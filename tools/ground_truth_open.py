"""Ground truth for the ventilation: sweep the built .blend and measure.

This is deliberately NOT the same code path as verify_ventilation.py. That
verifier uses the spec's analytic surface to aim its rays, so when the spec
and the built geometry disagree, the two agree with each other and disagree
with reality. This one only knows the finished body: it fires a grid of
rays, asks what it hit, and reports the fraction that reached the cavity.

Run it after any change to the grille or the shell.
"""
import math
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, "/Users/sqs/code/mac-studio-model/blender")
import mac_studio_spec as S  # noqa: E402

BLEND = "/Users/sqs/code/mac-studio-model/blender/mac_studio.blend"

# A ray counts as open when it gets through the skin and past the cavity
# face. The shell keeps WALL of metal, so the surface is at D/2 and the
# cavity face at D/2 - WALL.
#
# Aim at the surface, not at the recessed floor. grille_inset steps the skin
# in by the recess only where the mask is on, and after the boolean the bore
# opens on whatever the loft actually produced - measured on this build, the
# field's skin is at -9.85 and the cavity at -9.70, so probing from -9.775
# starts a quarter of a millimetre INSIDE the metal and reports 1.8% open on
# a panel that is 85% perforated.
SKIN = S.D / 2.0
THROUGH = S.WALL + 0.02


def sweep(sc, dg, name, origin, direction, u_range, v_range, nu, nv):
    opened = total = 0
    blockers = {}
    for i in range(nu):
        u = u_range[0] + (u_range[1] - u_range[0]) * i / (nu - 1.0)
        for j in range(nv):
            v = v_range[0] + (v_range[1] - v_range[0]) * j / (nv - 1.0)
            org = origin(u, v)
            hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, org, direction)
            total += 1
            if not hit or (loc - org).dot(direction) > THROUGH:
                opened += 1
            else:
                blockers[ob.name] = blockers.get(ob.name, 0) + 1
    pct = 100.0 * opened / total if total else 0.0
    print("  %-12s %6d/%6d = %5.1f%% open   %s"
          % (name, opened, total, pct, blockers or ""))
    return pct


def main():
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    for n in ("BounceL", "BounceR", "Floor"):
        o = bpy.data.objects.get(n)
        if o:
            o.hide_viewport = True
    sc = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()

    y = -SKIN
    z0, z1 = S.UPPER_Z0 + 0.10, S.UPPER_Z1 - 0.10
    design = 100.0 * math.pi * S.UPPER_HOLE_R ** 2 / (S.UPPER_PITCH_X * S.UPPER_PITCH_Z)

    print("rear field, %d x %d rays, step %.2f mm in x"
          % (180, 120, 2 * S.UPPER_HALF_X * 10 / 180))
    got = sweep(sc, dg, "rear field",
                lambda x, z: Vector((x, y - 0.002, z)),
                Vector((0, 1, 0)),
                (-S.UPPER_HALF_X, S.UPPER_HALF_X), (z0, z1), 180, 120)
    print("     design %.1f%%" % design)
    return 0 if got > design * 0.7 else 1


main()
