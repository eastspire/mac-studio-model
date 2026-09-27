"""Pin down which front-slot cutter parameter breaks the EXACT boolean.

Rebuilds a fresh shell, applies one front-slot cut under several cutter
geometries, and reports whether the shell's minY grew past the skin
(good = cut, bad = cutter absorbed).

usage:  blender --background --python bool_sweep.py
"""
import importlib.util
import os

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("bld", os.path.join(HERE, "build_mac_studio.py"))
bld = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bld)


def ybounds(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(deps)
    lo = hi = None
    for c in ev.bound_box:
        wc = ev.matrix_world @ Vector(c)
        lo = wc.y if lo is None else min(lo, wc.y)
        hi = wc.y if hi is None else max(hi, wc.y)
    return lo, hi, len(ev.data.vertices)


y = -bld.D / 2.0
print("skin at y = %.3f" % y)
for bevel, depth, off in [
    (0.16, 0.60, 0.20),
    (0.10, 0.60, 0.20),
    (0.05, 0.60, 0.20),
    (0.16, 1.20, 0.40),
    (0.16, 1.20, 0.60),
    (0.16, 0.60, 0.30),
    (0.00, 0.60, 0.20),
]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats = bld.build_materials()
    body = bld.build_body(mats)
    bld.cut_from_body(body, "probe", -7.40, y + off, 2.55, 0.52, depth, 1.10,
                      bevel=bevel, mats=mats)
    lo, hi, v = ybounds(body)
    bad = lo < y - 1e-4
    print("bevel=%.2f depth=%.2f off=%.2f  minY=%+.3f (%+.2fmm) verts=%d %s"
          % (bevel, depth, off, lo, (lo - y) * 10.0, v, "BAD" if bad else "ok"))
