"""Step through build_front_io one cut at a time, printing Body's minY.

A single front-slot cut is clean (see bool_sweep.py); this finds which cut in
the sequence first pushes the shell's minY past the skin.

usage:  blender --background --python cut_trace.py
"""
import importlib.util
import os

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("bld", os.path.join(HERE, "build_mac_studio.py"))
bld = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bld)

Y = -bld.D / 2.0


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
    ngon = sum(1 for p in body.data.polygons if len(p.vertices) > 3)
    flag = "  <-- BLEW OUT" if lo < Y - 1e-4 else ""
    print("%-22s minY=%+.3f  verts=%-6d ngons=%-5d%s" % (tag, lo, v, ngon, flag))


bpy.ops.wm.read_factory_settings(use_empty=True)
mats = bld.build_materials()
body = bld.build_body(mats)
report("fresh loft", body)

zc = 2.55
slots = [
    ("Front_USBC_1", -7.40, 0.32, 0.90),
    ("Front_USBC_2", -6.40, 0.32, 0.90),
    ("Front_SDXC", -4.70, 1.30, 0.34),
]
for name, x, w, h in slots:
    bld.cut_from_body(body, name, x, Y + 0.20, zc, w + 0.20, 0.60, h + 0.20,
                      bevel=0.16, mats=mats)
    report("after cut " + name, body)
    bld.add_socket(name, x, zc, w, h, Y + 0.10, mats, depth=0.34, wall=0.045)
    report("  +socket " + name, body)

bld.cut_from_body(body, "Front_LED", 7.60, Y + 0.20, zc, 0.24, 0.60, 0.24,
                  bevel=0.08, mats=mats)
report("after cut Front_LED", body)
