"""Report per-object world bounds, sorted by |extent| — find bbox offenders.

usage:  blender --background --python inspect_bbox.py
"""
import os

import bpy
from mathutils import Vector

BLEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mac_studio.blend"))

bpy.ops.wm.open_mainfile(filepath=BLEND)
deps = bpy.context.evaluated_depsgraph_get()

rows = []
for obj in bpy.context.scene.objects:
    if obj.type != "MESH" or obj.name == "Floor":
        continue
    ev = obj.evaluated_get(deps)
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for corner in ev.bound_box:
        wc = ev.matrix_world @ Vector(corner)
        for i in range(3):
            lo[i] = min(lo[i], wc[i])
            hi[i] = max(hi[i], wc[i])
    rows.append((obj.name, lo, hi))

rows.sort(key=lambda r: r[1].y)
print("%-26s %9s %9s %9s %9s %9s %9s" % ("object", "minX", "maxX", "minY", "maxY", "minZ", "maxZ"))
for name, lo, hi in rows:
    print("%-26s %9.3f %9.3f %9.3f %9.3f %9.3f %9.3f"
          % (name, lo.x, hi.x, lo.y, hi.y, lo.z, hi.z))

lo = Vector((min(r[1].x for r in rows), min(r[1].y for r in rows), min(r[1].z for r in rows)))
hi = Vector((max(r[2].x for r in rows), max(r[2].y for r in rows), max(r[2].z for r in rows)))
print("TOTAL %.4f %.4f %.4f" % (hi.x - lo.x, hi.y - lo.y, hi.z - lo.z))
