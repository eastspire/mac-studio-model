#!/usr/bin/env python3
"""Per-object bounding-box audit, in millimetres, against the published envelope.

The build prints a single BBOX line, which tells you the model is wrong but
not which object is. A 158 mm tall machine with its floor at -63 mm is two
separate faults, and they are in two different objects.

Run inside Blender:
    blender --background --factory-startup \
      --python tools/audit_bbox.py -- /path/to/mac_studio.blend
"""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "blender"))

import mac_studio_spec as S  # noqa: E402

# Studio furniture, not part of the product: a 200 cm floor plane and 40 cm
# bounce cards otherwise dominate the numbers.
EXCLUDE = {"Floor", "BounceL", "BounceR"}

WANT = {
    "X": (S.W, S.W),
    "Y": (S.D, S.D),
    "Z": (S.H_TOTAL, S.H_TOTAL),
}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    blend = argv[0] if argv else os.path.join(ROOT, "blender", "mac_studio.blend")
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend))

    dg = bpy.context.evaluated_depsgraph_get()
    rows = []
    for obj in scene_objects():
        ev = obj.evaluated_get(dg)
        try:
            bb = [obj.matrix_world @ v.co for v in ev.data.vertices]
        except Exception:
            continue
        if not bb:
            continue
        xs = [p.x for p in bb]
        ys = [p.y for p in bb]
        zs = [p.z for p in bb]
        rows.append((obj.name,
                     min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))

    rows.sort(key=lambda r: r[5])          # lowest object first
    print("object                       x_min  x_max   y_min  y_max   z_min  z_max"
          "   (mm)")
    print("-" * 84)
    for name, x0, x1, y0, y1, z0, z1 in rows:
        flag = ""
        if z0 < -0.05:
            flag += " BELOW-FLOOR"
        if z1 > S.H_TOTAL + 0.05:
            flag += " ABOVE-TOP"
        if abs(x1 - x0) > S.W * 10 + 0.6:
            flag += " WIDE"
        print("%-26s %6.1f %6.1f  %6.1f %6.1f  %6.1f %6.1f%s"
              % (name, x0 * 10, x1 * 10, y0 * 10, y1 * 10, z0 * 10, z1 * 10, flag))

    prod = [r for r in rows if r[0] not in EXCLUDE]
    print("\nenvelope over product objects only:")
    for i, axis in enumerate("XYZ"):
        lo = min(r[1 + i * 2] for r in prod)
        hi = max(r[2 + i * 2] for r in prod)
        size = (hi - lo) * 10
        want = WANT[axis][0] * 10
        d = size - want
        print("  %s  %7.2f mm  want %7.2f mm  delta %+7.2f mm  %s"
              % (axis, size, want, d, "ok" if abs(d) <= 0.9 else "FAIL"))
        print("      min %+7.2f mm  max %+7.2f mm" % (lo * 10, hi * 10))


def scene_objects():
    return [o for o in bpy.context.scene.objects
            if o.type == "MESH" and o.name not in EXCLUDE]


if __name__ == "__main__":
    main()
