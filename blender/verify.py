"""Verify the straddling convention: 0.10cm proud + N inward, for both panels.

Prints Body's minY/maxY after a full build. Anything past -9.851 / +9.851 means
a cutter's outer half got merged into the shell.

usage:  blender --background --python verify.py
"""
import importlib.util
import os

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("bld", os.path.join(HERE, "build_mac_studio.py"))
bld = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bld)


def bounds(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for c in ev.bound_box:
        wc = ev.matrix_world @ Vector(c)
        for i in range(3):
            lo[i] = min(lo[i], wc[i])
            hi[i] = max(hi[i], wc[i])
    return lo, hi


EXCLUDE = {"Floor", "BounceL", "BounceR"}

bpy.ops.wm.read_factory_settings(use_empty=True)
mats = bld.build_materials()
body = bld.build_body(mats)
bld.build_rear_io(mats)
lo1, hi1 = bounds(body)
print("after rear_io   minY=%+.4f maxY=%+.4f" % (lo1.y, hi1.y))
bld.build_front_io(mats, body)
lo2, hi2 = bounds(body)
print("after front_io  minY=%+.4f maxY=%+.4f" % (lo2.y, hi2.y))
bld.build_bottom_details(mats)
bld.build_grille_band(mats)
bld.build_studio(bpy.context.scene)

lo = Vector((1e9,) * 3)
hi = Vector((-1e9,) * 3)
deps = bpy.context.evaluated_depsgraph_get()
for obj in bpy.context.scene.objects:
    if obj.type != "MESH" or obj.name in EXCLUDE:
        continue
    ev = obj.evaluated_get(deps)
    for c in ev.bound_box:
        wc = ev.matrix_world @ Vector(c)
        for i in range(3):
            lo[i] = min(lo[i], wc[i])
            hi[i] = max(hi[i], wc[i])
size = hi - lo
print("SIZE %.4f %.4f %.4f" % (size.x, size.y, size.z))
ok = True
for axis, got, want in zip("XYZ", size, (bld.W, bld.D, bld.H_TOTAL)):
    d = (got - want) * 10.0
    if abs(d) > 0.5:
        ok = False
    print("  %s delta %+.3f mm %s" % (axis, d, "" if abs(d) <= 0.5 else "FAIL"))

print("--- offenders ---")
for obj in bpy.context.scene.objects:
    if obj.type != "MESH" or obj.name in EXCLUDE:
        continue
    ev = obj.evaluated_get(deps)
    l, h = bounds(ev)
    if l.y < -9.851 or h.y > 9.851:
        print("  %-26s minY=%+.3f maxY=%+.3f" % (obj.name, l.y, h.y))
print("VERIFY_OK" if ok else "VERIFY_FAIL")
