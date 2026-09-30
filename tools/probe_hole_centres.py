"""Is each perforation actually open? Probe the exact centres.

tools/ground_truth_open.py sweeps a grid and reports an AREA fraction, which
tells you the panel is sealed but not why. This one recomputes the hole
centres with build_grille_field's own walk and shoots a ray down each one, so
a miss is attributable to a specific place in the placement code.

The two disagree in a way worth knowing: the grid reports 0.1% open and this
reports what fraction of the 3,069 named holes pass. If the named holes mostly
pass and the grid does not, the bores are open but small and the grid's
spacing is aliasing them. If the named holes mostly fail, the bores are in
the wrong place.
"""
import math
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, "/Users/sqs/code/mac-studio-model/blender")
import mac_studio_spec as S  # noqa: E402

BLEND = "/Users/sqs/code/mac-studio-model/blender/mac_studio.blend"


def field_centres():
    """Recompute the rear field's hole centres, exactly as the builder does."""
    src = open("/Users/sqs/code/mac-studio-model/blender/build_mac_studio.py").read()
    ns = {"math": math, "ARC_SEG": S.ARC_SEG}
    # field_mask() reads the spec's constants as module globals, exactly as it
    # does in the builder, so the whole spec namespace has to be visible.
    for k in dir(S):
        if k.isupper():
            ns[k] = getattr(S, k)
    for fn in ("rounded_rect", "field_mask"):
        i = src.index("def %s(" % fn)
        j = src.index("\ndef ", i + 5)
        exec(src[i:j], ns)
    rr, fmask = ns["rounded_rect"], ns["field_mask"]

    recess = S.UPPER_DEPTH
    hx, hy = S.W / 2.0 - recess, S.D / 2.0 - recess
    perim = rr(hx, hy, S.R_VERT - recess, seg=24, edge_sub=160)
    acc = [0.0]
    for i in range(1, len(perim)):
        acc.append(acc[-1] + math.hypot(perim[i][0] - perim[i - 1][0],
                                        perim[i][1] - perim[i - 1][1]))
    acc.append(acc[-1] + math.hypot(perim[0][0] - perim[-1][0],
                                    perim[0][1] - perim[-1][1]))
    total = acc[-1]

    def point_at(s):
        if s <= 0.0:
            return perim[0]
        if s >= acc[-1]:
            return perim[-1]
        lo, hi = 0, len(perim) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if acc[mid] < s:
                lo = mid + 1
            else:
                hi = mid
        px, py = perim[lo]
        nx_, ny_ = perim[(lo + 1) % len(perim)]
        seg = acc[lo + 1] - acc[lo]
        f = 0.0 if seg <= 0 else min(1.0, max(0.0, (s - acc[lo]) / seg))
        return px + (nx_ - px) * f, py + (ny_ - py) * f

    out = []
    z0, z1 = S.UPPER_Z0 + 0.10, S.UPPER_Z1 - 0.10
    rows = max(1, int((z1 - z0) / S.UPPER_PITCH_Z) + 2)
    for row in range(rows):
        z = z0 + (z1 - z0) - row * S.UPPER_PITCH_Z
        s = (S.UPPER_STAGGER * S.UPPER_PITCH_X) if (S.UPPER_STAGGER and row % 2) else 0.0
        while s < total:
            px, py = point_at(s)
            if fmask(px, py, hx, hy) >= 0.5:
                out.append((px, py, z))
            s += S.UPPER_PITCH_X
    return out


def main():
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    for n in ("BounceL", "BounceR", "Floor"):
        o = bpy.data.objects.get(n)
        if o:
            o.hide_viewport = True
    sc = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()

    centres = field_centres()
    print("recomputed %d hole centres" % len(centres))
    org_y = -S.D / 2.0 - 0.5
    d = Vector((0, 1, 0))
    # A bore is open if the ray clears the skin without meeting Body. The
    # skin is the outermost Body hit anywhere on this face, so derive the
    # threshold from the model rather than assuming WALL.
    skin = None
    for px, py, z in centres[:1]:
        p = Vector((px, org_y, z))
        hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, p, d)
        skin = loc.y if hit else None
    print("first Body hit from outside at a hole centre: %s"
          % ("%+.4f" % skin if skin is not None else "VOID"))

    opened = blocked = 0
    first_block = None
    for px, py, z in centres:
        p = Vector((px, org_y, z))
        hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, p, d)
        if not hit:
            opened += 1
            continue
        # open if the first hit is well inside the cavity, not at the skin
        if (loc.y - org_y) > S.WALL + 0.05:
            opened += 1
        else:
            blocked += 1
            if first_block is None:
                first_block = (px, py, z, ob.name, loc.y)
    n = opened + blocked
    print("named holes: %d/%d open (%.1f%%)" % (opened, n, 100.0 * opened / n))
    if first_block:
        px, py, z, name, y = first_block
        print("  first blocked: x=%+.4f y=%+.4f z=%+.4f -> %s at %+.4f"
              % (px, py, z, name, y))
    return 0 if opened * 2 > n else 1


main()
