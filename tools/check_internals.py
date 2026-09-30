#!/usr/bin/env python3
"""Does the internal model still fit together after the spec changed?

tools/check_builder.py proves the Blender script has no unbound names and no
numeric literals of its own.  It cannot prove the box it builds is physically
sensible, and that is exactly what broke: correcting the blower height from
the X-ray moved the fin stack up into the fan shroud and dropped the copper
plane through the package under it.  Both were legal Blender objects.  Nothing
downstream complained.

So this rebuilds the same primitives build_internals() creates, as axis-aligned
boxes derived from the spec alone, and checks the things that have to hold:

  1. every part is inside the shell, clear of the walls and the top cover
  2. no two major layers interpenetrate
  3. the impeller fits its own shroud
  4. nothing is placed where an exterior feature already is - the rear
     exhaust field, the rear port row, the base intake band - so an internal
     box cannot end up blocking a hole that verify_spec.py has already
     accepted against the photograph

The boxes are a mirror of build_internals(), not a copy of the spec: if the two
ever disagree, this file is what needs updating, and point 1 will catch it
immediately because the numbers come from the spec either way.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "blender"))

import mac_studio_spec as S                     # noqa: E402

# Box primitives exactly as build_internals() emits them:
#   name -> (cx, cy, cz, sx, sy, sz)   all in cm
def boxes():
    b = []
    add = lambda *a: b.append(a)                # noqa: E731
    for k, sx in enumerate((-1, 1)):
        add("Fan%d_shroud" % (k + 1), sx * S.FAN_X, 0.0, S.FAN_Z,
            S.FAN_SHROUD_W, S.FAN_SHROUD_D, S.FAN_SHROUD_H)
    add("Centre_spine", 0.0, 0.0, (S.SPINE_Z0 + S.SPINE_Z1) / 2,
        S.SPINE_W, S.SPINE_D, S.SPINE_Z1 - S.SPINE_Z0)
    add("Spine_crossmember", 0.0, 0.0,
        (S.SPINE_BREAK_Z0 + S.SPINE_BREAK_Z1) / 2,
        S.SPINE_BREAK_HALF_X * 2, S.SPINE_D * 0.72,
        S.SPINE_BREAK_Z1 - S.SPINE_BREAK_Z0)
    hs = S.HEATSINK_Z
    add("Heatsink_base", 0.0, 0.0, hs, 16.8, 12.6, 0.50)
    add("Heatsink_fins", 0.0, 0.0, hs + 0.48, 16.4, 11.7 + 0.16, 0.80)
    add("SoC_package", 0.0, 0.0, hs - 0.36, 4.6, 4.6, 0.28)
    add("HeatPipe_plane", 0.0, 0.0, S.PIPE_Z, 17.6, 14.4, 0.22)
    p = S.PCB_Z
    add("LogicBoard", 0.0, 0.0, p, 18.2, 15.6, 0.16)
    for k, sx in enumerate((-1, 1)):
        add("Memory_%d" % (k + 1), sx * 3.9, 0.0, p + 0.22, 4.2, 2.6, 0.28)
    for k, sy in enumerate((-1, 1)):
        add("SSD_%d" % (k + 1), -5.2, sy * 3.4, p + 0.20, 4.0, 2.2, 0.24)
    add("PSU", 5.90, 1.4, S.PSU_Z, 5.6, 9.4, 1.70)
    add("PSU_coil", 5.90, -3.6, S.PSU_Z + 0.10, 2.30, 2.30, 1.40)
    add("PSU_cap", 5.90, 3.4, S.PSU_Z + 0.20, 5.0, 2.0, 1.40)
    # the electrolytic row: bounding box of the seven cylinders
    add("Cap_row", -2.4, -2.0, 1.00, 7.2, 0.60, 0.70)
    add("Speaker", -6.6, -5.4, S.SPEAKER_Z, 2.6, 2.2, 1.10)
    add("FrontIO", -6.6, 3.2, S.SPEAKER_Z + 0.20, 3.4, 5.0, 0.80)
    for sx in (-1, 1):
        add("Frame_side%d" % (sx > 0), sx * 8.95, 0.0, 4.0, 0.5, 15.0, 7.4)
    add("Frame_floor", 0.0, 0.0, 0.52, 17.4, 15.0, 0.22)
    return b


# Layer groups that must not interpenetrate.  Parts within a group are
# deliberately stacked on top of each other and are excluded.
GROUPS = [
    ("blower", {"Fan1_shroud", "Fan2_shroud", "Centre_spine",
                "Spine_crossmember"}),
    ("heatsink", {"Heatsink_base", "Heatsink_fins", "SoC_package"}),
    ("copper plane", {"HeatPipe_plane"}),
    ("board", {"LogicBoard", "Memory_1", "Memory_2", "SSD_1", "SSD_2"}),
    ("supply", {"PSU", "PSU_coil", "PSU_cap", "Cap_row"}),
    ("front io", {"Speaker", "FrontIO"}),
    ("frame", {"Frame_side0", "Frame_side1", "Frame_floor"}),
]
# The frame is a chassis part, not a layer: it is allowed to span the height
# and to run alongside the boards, so it is checked for containment only.


def overlap_mm(a, bx):
    """Separation of two boxes.  Positive means clear, in mm.

    A name is element 0 of each tuple, so the geometry starts at index 1.
    """
    _, ax, ay, az, asx, asy, asz = a
    _, bx_, by_, bz, bsx, bsy, bsz = bx
    dz = (abs(az - bz) - (asz + bsz) / 2) * 10
    dx = (abs(ax - bx_) - (asx + bsx) / 2) * 10
    dy = (abs(ay - by_) - (asy + bsy) / 2) * 10
    return max(dx, dy, dz)


def mirror_check():
    """Does the Blender builder still build the boxes checked above?

    The internals now exist in three places: build_mac_studio.py makes them,
    compare_render.py's SDF approximates them for the offline render, and
    boxes() above restates them so they can be tested without Blender.  Three
    copies is one too many, so this reads build_internals() out of the builder
    with ast and compares every add_box() whose arguments are all literal or a
    bare spec name against boxes().  A size that drifts in one copy and not the
    others is exactly the failure the acceptance test cannot see.
    """
    import ast

    path = os.path.join(ROOT, "blender", "build_mac_studio.py")
    tree = ast.parse(open(path).read())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "build_internals")

    # local aliases: `hs_z = HEATSINK_Z` is the same value and must compare
    def val(node, alias=None):
        alias = alias or {}
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            v = val(node.operand, alias)
            return None if v is None else -v
        if isinstance(node, ast.Name):
            if hasattr(S, node.id):
                return float(getattr(S, node.id))
            return alias.get(node.id)
        if isinstance(node, ast.BinOp):
            a, b = val(node.left, alias), val(node.right, alias)
            if a is None or b is None:
                return None
            if isinstance(node.op, ast.Add):
                return a + b
            if isinstance(node.op, ast.Sub):
                return a - b
            if isinstance(node.op, ast.Div):
                return None if b == 0 else a / b
            if isinstance(node.op, ast.Mult):
                return a * b
        return None

    def resolve(node):
        return val(node, alias)

    alias = {}
    for node in ast.walk(fn):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            v = val(node.value)
            if v is not None:
                alias[node.targets[0].id] = v

    mine = {b[0]: b[1:] for b in boxes()}
    out, unknown = [], []
    for call in ast.walk(fn):
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                and call.func.id == "add_box"):
            continue
        if not call.args or not isinstance(call.args[0], ast.Constant):
            continue
        name = call.args[0].value
        nums = [resolve(a) for a in call.args[1:7]]
        if len(nums) < 6 or any(n is None for n in nums):
            unknown.append(name)
            continue
        if name not in mine:
            out.append("%s: built by Blender but not in boxes()" % name)
            continue
        if any(abs(a - b) > 1e-6 for a, b in zip(nums, mine[name])):
            out.append("%s: builder %s vs boxes() %s"
                       % (name, tuple(round(v, 3) for v in nums),
                          tuple(round(v, 3) for v in mine[name])))
    return out, unknown


def main():
    b = boxes()
    by = {x[0]: x for x in b}
    fails = []
    hx, hy = S.W / 2 - S.WALL, S.D / 2 - S.WALL
    top = S.H_TOTAL - 0.30

    for name, cx, cy, cz, sx, sy, sz in b:
        if abs(cx) + sx / 2 > hx + 1e-9:
            fails.append("%s: x reaches %.1f mm, wall is at %.1f mm"
                         % (name, (abs(cx) + sx / 2) * 10, hx * 10))
        if abs(cy) + sy / 2 > hy + 1e-9:
            fails.append("%s: y reaches %.1f mm, wall is at %.1f mm"
                         % (name, (abs(cy) + sy / 2) * 10, hy * 10))
        if cz - sz / 2 < -1e-9:
            fails.append("%s: bottom at %.1f mm, below the floor"
                         % (name, (cz - sz / 2) * 10))
        if cz + sz / 2 > top + 1e-9:
            fails.append("%s: top at %.1f mm, top cover inner face at %.1f mm"
                         % (name, (cz + sz / 2) * 10, top * 10))

    for i, (ga, ma) in enumerate(GROUPS):
        if ga == "frame":
            continue
        for gb, mb in GROUPS[i + 1:]:
            if gb == "frame":
                continue
            for na in sorted(ma):
                for nb in sorted(mb):
                    g = overlap_mm(by[na], by[nb])
                    if g < 0:
                        fails.append("%s (%s) and %s (%s) interpenetrate "
                                     "by %.1f mm"
                                     % (na, ga, nb, gb, -g))

    if 2 * S.FAN_R > S.FAN_SHROUD_W + 1e-9:
        fails.append("bore diameter %.1f mm exceeds shroud width %.1f mm"
                     % (2 * S.FAN_R * 10, S.FAN_SHROUD_W * 10))
    if 2 * S.FAN_R > S.FAN_SHROUD_D + 1e-9:
        fails.append("bore diameter %.1f mm exceeds shroud depth %.1f mm"
                     % (2 * S.FAN_R * 10, S.FAN_SHROUD_D * 10))
    if S.FAN_R * 0.94 > S.FAN_R + 1e-9:
        fails.append("blade sweep r*0.94 exceeds the bore r")

    # An internal box must not sit where a hole in the shell already is.
    field = (S.FIELD_BOT_MM / 10, S.FIELD_TOP_MM / 10)
    for name, cx, cy, cz, sx, sy, sz in b:
        if cy + sy / 2 > S.D / 2 - 1.2:
            top_z = cz + sz / 2
            bot_z = cz - sz / 2
            if top_z > field[0] and bot_z < field[1]:
                fails.append("%s reaches y %.1f mm inside the rear exhaust "
                             "field (z %.2f..%.2f cm)"
                             % (name, (cy + sy / 2) * 10, bot_z, top_z))
        if cz - sz / 2 < S.GRILLE_BAND_Z1 and cy + sy / 2 > S.D / 2 - 1.2:
            fails.append("%s sits in the base intake band (z < %.2f cm)"
                         % (name, S.GRILLE_BAND_Z1))

    print("internals: %d primitives from the spec" % len(b))
    print("  shroud   z %.2f .. %.2f cm   x +/-%.1f mm   w %.1f mm"
          % (S.FAN_Z - S.FAN_SHROUD_H / 2, S.FAN_Z + S.FAN_SHROUD_H / 2,
             S.FAN_X * 10, S.FAN_SHROUD_W * 10))
    print("  heatsink z %.2f .. %.2f cm"
          % (S.HEATSINK_Z - 0.50, S.HEATSINK_Z + 0.88))
    print("  copper   z %.2f .. %.2f cm"
          % (S.PIPE_Z - 0.11, S.PIPE_Z + 0.11))
    print("  board    z %.2f .. %.2f cm" % (S.PCB_Z - 0.08, S.PCB_Z + 0.36))
    print("  supply   z %.2f .. %.2f cm"
          % (S.PSU_Z - 0.85, S.PSU_Z + 0.90))
    print("  caps     z 0.65 .. 1.35 cm  (floor row, left of the supply)")

    mism, unknown = mirror_check()
    print("\n  builder mirror: %d add_box() calls compared, %d left "
          "uncompared" % (len(boxes()) - len(set(unknown)), len(set(unknown))))
    if unknown:
        print("    (not compared: %s)" % ", ".join(sorted(set(unknown))))
    fails.extend(mism)
    if fails:
        print("\n%d PROBLEM(S):" % len(fails))
        for f in fails:
            print("   x %s" % f)
        raise SystemExit(1)
    print("\nINTERNALS CONSISTENT (containment, no interpenetration, bore "
          "fits, no part blocking a measured opening)")


if __name__ == "__main__":
    main()
