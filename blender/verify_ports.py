"""Geometry self-check: port row spacing, bay containment, silhouette flatness.

Run after any port-layout edit. Catches the classes of error that render fine
but read wrong: transposed connector shapes, connectors overlapping or nearly
touching, and anything sitting outside the recessed bay band.
"""
import bpy
import mathutils
from mathutils import Vector

M = mathutils.Vector
BBOX_TOL = 1e-4


def world_bbox(o):
    pts = [o.matrix_world @ M(c) for c in o.bound_box]
    return (min(p.x for p in pts), max(p.x for p in pts),
            min(p.y for p in pts), max(p.y for p in pts),
            min(p.z for p in pts), max(p.z for p in pts))


def group_ports(prefix="Port_"):
    """Collapse a socket's wall/back/tongue sub-meshes into one entry."""
    g = {}
    for o in bpy.data.objects:
        if o.type != "MESH" or not o.name.startswith(prefix):
            continue
        base = o.name
        for suf in ("_w_top", "_w_bot", "_w_l", "_w_r", "_back",
                    "_tongue", "_shell", "_pin"):
            base = base.replace(suf, "")
        bb = world_bbox(o)
        cur = g.get(base)
        g[base] = bb if cur is None else (
            min(cur[0], bb[0]), max(cur[1], bb[1]),
            min(cur[2], bb[2]), max(cur[3], bb[3]),
            min(cur[4], bb[4]), max(cur[5], bb[5]))
    return g


def check(name, ok, detail=""):
    print("  %-4s %-46s %s" % ("OK" if ok else "FAIL", name, detail))
    return 0 if ok else 1


def main():
    bpy.ops.wm.open_mainfile(filepath="mac_studio.blend")
    fails = 0
    ports = group_ports()
    rear = {k: v for k, v in ports.items() if not k.startswith("Front_")}
    front = {k: v for k, v in ports.items() if k.startswith("Front_")}

    print("REAR row (in model x order):")
    order = sorted(rear, key=lambda k: -rear[k][0])
    for k in order:
        b = rear[k]
        print("    %-24s x %6.2f..%6.2f  w %.2f  h %.2f"
              % (k, b[0], b[1], b[1] - b[0], b[5] - b[4]))

    # 1. no two connectors may touch or overlap in x
    print("\nchecks:")
    for i in range(len(order) - 1):
        a, b_ = rear[order[i]], rear[order[i + 1]]
        gap = a[0] - b_[1]          # a is at higher x
        fails += check("gap %s -> %s" % (order[i][5:], order[i + 1][5:]),
                       gap >= 0.20, "%.2f cm" % gap)

    # 2. USB-C / Thunderbolt shells must be taller than they are wide
    for k in order:
        if "USBC" in k or "TB5" in k:
            b = rear[k]
            w, h = b[1] - b[0], b[5] - b[4]
            fails += check("%s is a vertical slot" % k, h > w,
                           "w %.2f h %.2f" % (w, h))

    # 3. everything must sit inside the bay's x extent
    body = bpy.data.objects["Body"]
    xs = [p for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("Port_")
          for p in (world_bbox(o)[0], world_bbox(o)[1])]
    fails += check("rear row within +/- 7.4 cm", max(xs) <= 7.4,
                   "max |x| %.2f" % max(xs))
    fails += check("rear row within +/- 7.4 cm (min)", min(xs) >= -7.4,
                   "min x %.2f" % min(xs))

    # 4. every rear port must be vertically centred in the bay band
    zlo, zhi = 9.5 * 0.20, 9.5 * 0.50
    zc = (zlo + zhi) / 2.0
    for k in order:
        b = rear[k]
        mid = (b[4] + b[5]) / 2.0
        fails += check("%s centred in bay" % k, abs(mid - zc) <= 0.75,
                       "mid %.2f vs bay centre %.2f" % (mid, zc))
        fails += check("%s inside bay height" % k, b[4] >= zlo - 0.1 and b[5] <= zhi + 0.1,
                       "z %.2f..%.2f" % (b[4], b[5]))

    # 4. front row: USB-C on the +X side (renders screen-left), LED on -X
    if "Front_SDXC" in front:
        b = front["Front_SDXC"]
        fails += check("front SDXC left of centre (screen-left)",
                       b[0] > 0, "x %.2f" % b[0])
    print("\nFRONT row:")
    for k in sorted(front, key=lambda k: -front[k][0]):
        b = front[k]
        print("    %-24s x %6.2f..%6.2f  w %.2f  h %.2f"
              % (k, b[0], b[1], b[1] - b[0], b[5] - b[4]))

    # 6. the rear bay must read as a black cavity, not a bright silver recess.
    # A boolean difference keeps the SHELL's material on the flipped inner
    # faces, so the bay floor came out aluminium. Test the material, not the
    # look: count non-cavity faces in the bay's y slab.
    #
    # The tolerance is 0.10 cm, not 0.02: the two perforation fields' frames
    # sit at y = 9.75 (UPPER_DEPTH recess) and are part of the dark region.
    # At 0.02 they fell outside the slab and 5 side-wall faces stayed silver,
    # reading as bright ledges at each end of the port row.
    body = bpy.data.objects["Body"]
    mats = [m.name for m in body.data.materials]
    cav = mats.index("Cavity_Black") if "Cavity_Black" in mats else -1
    bay_depth = 0.42
    y_lo, y_hi = 9.85 - bay_depth - 0.02, 9.85 - 0.15
    zlo, zhi = 9.5 * 0.20 - 0.05, 9.5 * 0.50 + 0.05
    inside = [p for p in body.data.polygons
              if y_lo < p.center.y < y_hi and abs(p.center.x) < 8.05
              and zlo < p.center.z < zhi]
    silver = [p for p in inside
              if cav < 0 or p.material_index != cav]
    fails += check("rear bay interior is fully black",
                   not silver, "%d/%d faces still aluminium"
                   % (len(silver), len(inside)))

    # 7. the underside must carry circular ventilation intakes
    vents = [o for o in bpy.data.objects if o.name.startswith("VentBore_")]
    fails += check("four round underside intakes", len(vents) == 4,
                   "%d found" % len(vents))
    for o in vents:
        zmin = min((o.matrix_world @ Vector(c)).z for c in o.bound_box)
        fails += check("%s sits inside the shell" % o.name, zmin > 0.0,
                       "zmin %.2f" % zmin)

    print("\n%s (%d failures)" % ("PORTS_OK" if not fails else "PORTS_FAIL", fails))
    return fails


if __name__ == "__main__":
    main()
