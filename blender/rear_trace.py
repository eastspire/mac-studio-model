"""Step through build_rear_io one stage at a time, printing Body's maxY.

The front cuts are provably clean (cut_trace.py). This does the same for the
rear bay, whose cutter grew to 0.85cm deep when the sockets became tub-shaped.

usage:  blender --background --python rear_trace.py
"""
import importlib.util
import os

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("bld", os.path.join(HERE, "build_mac_studio.py"))
bld = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bld)

Y = bld.D / 2.0


def ybounds(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    lo = hi = None
    for c in ev.bound_box:
        wc = ev.matrix_world @ Vector(c)
        lo = wc.y if lo is None else min(lo, wc.y)
        hi = wc.y if hi is None else max(hi, wc.y)
    return lo, hi, len(ev.data.vertices)


def report(tag, body):
    lo, hi, v = ybounds(body)
    flag = "  <-- BLEW OUT" if hi > Y + 1e-4 else ""
    print("%-26s maxY=%+.3f  verts=%-6d%s" % (tag, hi, v, flag))


bpy.ops.wm.read_factory_settings(use_empty=True)
mats = bld.build_materials()
body = bld.build_body(mats)
report("fresh loft", body)

bay_x, z0, z1 = 8.70, 2.20, 6.30
zc = (z0 + z1) / 2.0
for depth in (0.42, 0.60, 0.85, 1.20):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats = bld.build_materials()
    body = bld.build_body(mats)
    bld.cut_from_body(body, "Bay", 0.0, Y - depth / 2.0 + 0.05, zc,
                      bay_x * 2.0, depth + 0.2, z1 - z0, bevel=0.35, mats=mats)
    report("bay depth %.2f" % depth, body)

bpy.ops.wm.read_factory_settings(use_empty=True)
mats = bld.build_materials()
body = bld.build_body(mats)
bld.cut_from_body(body, "Bay", 0.0, Y - 0.85 / 2.0 + 0.05, zc,
                  bay_x * 2.0, 1.05, z1 - z0, bevel=0.35, mats=mats)
report("depth .85 (rebuilt)", body)
bld.add_socket("Port_TB5_1", -5.90, zc, 0.95, 0.30, Y - 0.45, mats)
report("  +1 socket", body)
