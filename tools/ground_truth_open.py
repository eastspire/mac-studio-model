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


def sweep(sc, dg, name, origin, direction, u_range, v_range, nu, nv,
          standoff=0.0, skin_y=None, depth_limit=None):
    """Sweep a rectangular patch and report the open fraction.

    A sample is open when the first thing the ray meets is already past the
    skin, i.e. it fell through a hole rather than striking the face. Passing
    `skin_y` and `depth_limit` switches from a distance test to that positional
    one; without them the fallback is the old distance comparison, which cannot
    distinguish a hole from a wall of the same thickness.
    """
    opened = total = 0
    blockers = {}
    for i in range(nu):
        u = u_range[0] + (u_range[1] - u_range[0]) * i / (nu - 1.0)
        for j in range(nv):
            v = v_range[0] + (v_range[1] - v_range[0]) * j / (nv - 1.0)
            org = origin(u, v)
            hit, loc, nrm, _i, ob, _m = sc.ray_cast(dg, org, direction)
            total += 1
            # A sample is open when the first surface met FACES AWAY from the
            # incoming ray. The panel's skin faces the ray, so hitting it means
            # the sample is on the metal; a ray that fell through a hole meets
            # the cavity's far wall facing back the other way.
            #
            # This is the only criterion that survived measurement. Distance
            # cannot work - the wall is WALL thick and the cavity is WALL deep,
            # so "travelled far enough" is equally true of a hole and of metal
            # that happens to be the same thickness. Comparing against a
            # measured skin plane has the same problem, because the cavity's
            # far wall sits only 0.075 in from a skin at -9.775.
            if not hit or nrm.dot(direction) > 0.0:
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

    # THE TEST, and getting it right matters more than the sampling.
    #
    # "Did the ray travel far enough?" cannot work. The shell is WALL thick
    # and the cavity is WALL deep, so a ray that threads a hole and strikes
    # the cavity's far wall has travelled the same distance as one that stopped
    # in the metal. Sweeping a hole row at 0.02 mm steps - eight samples across
    # each hole - measured 0/858 open, while a per-hole probe using a
    # different distance threshold reported 3069/3069. Both were measuring the
    # built model; only one of them was measuring holes.
    #
    # The unambiguous test is: does the ray meet the panel AT ITS SKIN? A hole
    # mouth is a gap in the skin, so a ray down one arrives at the cavity wall
    # having crossed no skin at all. Find the skin's plane once, from a point
    # that is definitionally on a bridge, and require the first hit to be
    # deeper than the skin by more than the wall's own thickness.
    #
    # Anything shallower than that is the face itself: the bridge between two
    # holes, or the lip around a bore.
    y = -S.D / 2.0 - 0.5
    STANDOFF = 0.5
    z0, z1 = S.UPPER_Z0 + 0.10, S.UPPER_Z1 - 0.10
    design = 100.0 * math.pi * S.UPPER_HOLE_R ** 2 / (S.UPPER_PITCH_X * S.UPPER_PITCH_Z)

    # The skin plane: the OUTERMOST Body surface on this face. Taken from the
    # panel's own vertices, and recomputed every run because the booleans move
    # it - before the cut it is the nominal -9.85, after it is whatever lip the
    # difference left. Hardcoding it is how this tool reported 26.3% against a
    # skin it had placed 0.75 mm outside the real one.
    body = bpy.data.objects["Body"]
    mw = [body.matrix_world @ v.co for v in body.data.vertices]
    region = [v for v in mw
              if abs(v.x) <= S.UPPER_HALF_X and v.y < -9.0 and z0 <= v.z <= z1]
    if not region:
        print("  no Body geometry in the field - cannot measure")
        return 1
    skin_y = min(v.y for v in region)
    print("outermost Body surface on the rear: %+.4f" % skin_y)
    # Past the skin, the only thing a ray can meet is the cavity's far wall,
    # which sits a further WALL in. A bore's own wall is nearer than that and
    # is not a hole - it is the rim.
    depth_limit = S.WALL * 0.9
    print("skin at %+.4f; open means the first hit is deeper than %.4f"
          % (skin_y, depth_limit))

    step = S.UPPER_HOLE_R * 0.5
    nu = max(4, int(2 * S.UPPER_HALF_X / step) + 1)
    nv = max(4, int((z1 - z0) / step) + 1)
    print("rear field, %d x %d rays, step %.2f mm against a %.2f mm hole"
          % (nu, nv, step * 10, S.UPPER_HOLE_R * 2 * 10))
    got = sweep(sc, dg, "rear field",
                lambda x, z: Vector((x, y, z)),
                Vector((0, 1, 0)),
                (-S.UPPER_HALF_X, S.UPPER_HALF_X), (z0, z1), nu, nv,
                STANDOFF, skin_y, depth_limit)
    print("     design %.1f%%" % design)
    return 0 if got > design * 0.7 else 1


main()
