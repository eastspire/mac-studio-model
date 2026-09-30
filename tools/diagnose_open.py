"""Are the perforations open, and where exactly is the shell missing?

tools/ground_truth_open.py reports an AREA fraction for the rear field, which
says the panel is sealed but not why, and the audit reports a Z shortfall
without saying which part of the build took the material. Both are answerable
in one run by sweeping the real geometry and printing a map.

Prints, per grille, a coarse ASCII picture of the panel: '#' solid, '.' open.
A field that reads as solid dots with a lattice of solid in between is a
perforated panel; a field that is all solid is a sealed one; a picture that
stops partway across the width says the prisms ran out of panel.

    python tools/diagnose_open.py        (inside Blender)
"""
import math
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, "/Users/sqs/code/mac-studio-model/blender")
import mac_studio_spec as S  # noqa: E402

BLEND = "/Users/sqs/code/mac-studio-model/blender/mac_studio.blend"


def skin_at(body, z, half_x):
    """The rear face's own y at height z, read off the mesh."""
    mw = [body.matrix_world @ v.co for v in body.data.vertices]
    band = [v.y for v in mw
            if abs(v.x) <= half_x and v.y < -9.0 and abs(v.z - z) < 0.05]
    return min(band) if band else None


def map_panel(sc, dg, z_lo, z_hi, half_x, ncols, nrows, y_face, label):
    print()
    print("%s: %d wide x %d tall, rear face at y=%.4f" % (label, ncols, nrows, -y_face))
    z0, z1 = y_face - 0.40, y_face
    open_n = total = 0
    for j in range(nrows - 1, -1, -1):
        z = z_lo + (z_hi - z_lo) * j / (nrows - 1.0)
        row = []
        for i in range(ncols):
            x = -half_x + 2.0 * half_x * i / (ncols - 1.0)
            org = Vector((x, z0, z))
            hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, org, Vector((0, 1, 0)))
            if not hit:
                row.append(".")
                open_n += 1
            elif ob.name == "Body" and (loc.y - y_face) < 0.5 * S.WALL:
                row.append("#")
            else:
                row.append(".")
                open_n += 1
            total += 1
        print("  z=%6.2f  %s" % (z, "".join(row)))
    print("  %s: %d/%d = %.1f%% open" % (label, open_n, total,
                                         100.0 * open_n / max(1, total)))


def envelope(body):
    mw = [body.matrix_world @ v.co for v in body.data.vertices]
    print("Body: %d verts" % len(mw))
    print("  x %+.3f..%+.3f  y %+.3f..%+.3f  z %+.3f..%+.3f"
          % (min(v.x for v in mw), max(v.x for v in mw),
             min(v.y for v in mw), max(v.y for v in mw),
             min(v.z for v in mw), max(v.z for v in mw)))
    print("  want x +/-%.3f  z %.3f..%.3f" % (S.W / 2, S.FOOT_H, S.H_TOTAL))
    # Where along z does the shell have material? A band with a gap in the
    # middle is a different problem from one that is short at the ends.
    steps = 24
    print("  material by height:")
    for k in range(steps + 1):
        z = S.FOOT_H + (S.H_TOTAL - S.FOOT_H) * k / steps
        band = [v for v in mw if abs(v.z - z) < 0.02]
        if not band:
            print("    z=%6.2f  (no vertices)" % z)
            continue
        xs = [v.x for v in band]
        print("    z=%6.2f  %5d verts  x %+7.2f..%+7.2f" % (
            z, len(band), min(xs), max(xs)))


def main():
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    for n in ("BounceL", "BounceR", "Floor"):
        o = bpy.data.objects.get(n)
        if o:
            o.hide_viewport = True
    sc = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    body = bpy.data.objects["Body"]

    envelope(body)
    y_face = S.D / 2.0
    map_panel(sc, dg, S.UPPER_Z0 + 0.10, S.UPPER_Z1 - 0.10,
              S.UPPER_HALF_X, 90, 30, y_face, "rear field")
    map_panel(sc, dg, S.GRILLE_BAND_Z0 + 0.055, S.GRILLE_BAND_Z1 - 0.055,
              S.W / 2.0 - S.R_VERT, 90, 10, y_face, "base band (rear face)")
    return 0


main()
