"""Run the full build, then report every object that exceeds the target bbox.

usage:  blender --background --python build_trace.py
"""
import importlib.util
import os

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("bld", os.path.join(HERE, "build_mac_studio.py"))
bld = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bld)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
mats = bld.build_materials()
body = bld.build_body(mats)


def rep(tag):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(deps)
    lo = hi = None
    for c in ev.bound_box:
        wc = ev.matrix_world @ Vector(c)
        lo = wc.y if lo is None else min(lo, wc.y)
        hi = wc.y if hi is None else max(hi, wc.y)
    flag = "  <-- BLEW OUT" if (lo < -9.851 or hi > 9.851) else ""
    print("%-20s minY=%+.3f maxY=%+.3f verts=%-6d%s" % (tag, lo, hi, len(ev.data.vertices), flag))


rep("fresh")
bld.build_rear_io(mats)
rep("after rear_io")
bld.build_front_io(mats, body)
rep("after front_io")
bld.build_bottom_details(mats)
rep("after bottom")
bld.build_grille_band(mats)
rep("after grille")

print("--- per-object offenders (|coord| > 9.85) ---")
deps = bpy.context.evaluated_depsgraph_get()
for obj in scene.objects:
    if obj.type != "MESH" or obj.name == "Floor":
        continue
    ev = obj.evaluated_get(deps)
    lo = hi = None
    for c in ev.bound_box:
        wc = ev.matrix_world @ Vector(c)
        lo = wc.y if lo is None else min(lo, wc.y)
        hi = wc.y if hi is None else max(hi, wc.y)
    if lo < -9.851 or hi > 9.851:
        print("  %-28s minY=%+.3f maxY=%+.3f" % (obj.name, lo, hi))
