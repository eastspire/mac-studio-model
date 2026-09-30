"""Geometry self-check: port row spacing, bay containment, silhouette flatness.

Run after any port-layout edit. Catches the classes of error that render fine
but read wrong: transposed connector shapes, connectors overlapping or nearly
touching, and anything sitting outside the recessed bay band.
"""
import bpy
import mathutils
from mathutils import Vector

M = mathutils.Vector

# The canonical .blend, written by build_mac_studio.py next to it. There was a
# second, stale copy at the repo root (97 objects, no RearField) and this
# resolved to it, so the verifier measured a different machine from the
# one every other tool read.
_HERE = os.path.dirname(os.path.abspath(__file__))
BLEND = os.path.join(_HERE, "mac_studio.blend")
BBOX_TOL = 1e-4


def world_bbox(o):
    pts = [o.matrix_world @ M(c) for c in o.bound_box]
    return (min(p.x for p in pts), max(p.x for p in pts),
            min(p.y for p in pts), max(p.y for p in pts),
            min(p.z for p in pts), max(p.z for p in pts))


def group_ports():
    """Collapse a socket's wall/back/tongue sub-meshes into one entry.

    Both the rear row and the front panel are sockets, and they are named
    differently on purpose: the rear is "Port_<name>" and the front is
    "Front_<name>". Accept both prefixes, or the front row silently vanishes
    from the report and every front check reads "missing".
    """
    g = {}
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        # only the two socket rows: rear "Port_<name>", front "Front_<name>".
        # "Front_USBC_1" is a socket; "Foot_1" and "VentBore_2" are not, and
        # letting them through would make the front-row centre checks fail on
        # geometry that is not a connector.
        if not (o.name.startswith("Port_")
                or (o.name.startswith("Front_")
                    and not o.name.startswith("Front_LED"))):
            continue
        base = o.name
        for suf in ("_w_top", "_w_bot", "_w_l", "_w_r", "_back",
                    "_tongue", "_shell", "_pin", "_lip"):
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
    bpy.ops.wm.open_mainfile(filepath=BLEND)
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

    # 4. every rear port must be vertically centred in the bay band.
    # These are the measured band, not the model constants: 27%..47% of the
    # 9.5 cm height, from Apple's rear hardware diagram. Kept as literals
    # because this script deliberately reads the built .blend on its own and
    # does not import the builder — a stale import would hide a wrong build.
    zlo, zhi = 9.5 * 0.27, 9.5 * 0.47
    zc = (zlo + zhi) / 2.0
    for k in order:
        b = rear[k]
        mid = (b[4] + b[5]) / 2.0
        fails += check("%s centred in bay" % k, abs(mid - zc) <= 0.75,
                       "mid %.2f vs bay centre %.2f" % (mid, zc))
        fails += check("%s inside bay height" % k, b[4] >= zlo - 0.1 and b[5] <= zhi + 0.1,
                       "z %.2f..%.2f" % (b[4], b[5]))

    # 5. front row positions, measured from Apple's hw_front diagram.
    # Image-left is model +X (the diagram shows the machine from in front),
    # and the measured centres were 16.5%, 24.0%, 37.7% and 83.5% of the panel
    # width. Allow 0.35 cm of slack for the diagram's own perspective.
    front_want = {
        "Front_USBC_1": 6.60,
        "Front_USBC_2": 5.12,
        "Front_SDXC": 2.42,
        "Front_Headphone": -6.60,
    }
    for k, want in front_want.items():
        if k not in front:
            fails += check("%s present" % k, False, "missing")
            continue
        b = front[k]
        mid = (b[0] + b[1]) / 2.0
        fails += check("%s at measured x" % k, abs(mid - want) <= 0.35,
                       "%.2f (want %.2f)" % (mid, want))

    # the M5 Max has no front status LED — Touch ID is on the underside
    leds = [o for o in bpy.data.objects if o.name.startswith("Front_LED")]
    fails += check("no front status LED", not leds,
                   "%d found" % len(leds))
    print("\nFRONT row:")
    for k in sorted(front, key=lambda k: -front[k][0]):
        b = front[k]
        print("    %-24s x %6.2f..%6.2f  w %.2f  h %.2f"
              % (k, b[0], b[1], b[1] - b[0], b[5] - b[4]))

    # 6. the port bay must be a SHALLOW aluminium step, not a black pocket.
    #
    # This check was originally "no face in the bay may be aluminium" — the
    # wrong direction. Apple's rear diagram reads 6% / 0% / 9% dark across the
    # 55-70% band, i.e. the band is solid metal; the model's black-painted bay
    # measured 74% / 59% / 66% there and read as a slot. So assert the
    # opposite: the bay floor is mostly metal, and the only dark faces belong
    # to the connector mouths, which are separate objects.
    body = bpy.data.objects["Body"]
    mats = [m.name for m in body.data.materials]
    alu = mats.index("Aluminium_Silver") if "Aluminium_Silver" in mats else 0
    bay_depth = 0.18
    y_lo, y_hi = 9.85 - bay_depth - 0.02, 9.85 - 0.02
    zlo, zhi = 9.5 * 0.27 - 0.05, 9.5 * 0.47 + 0.05
    inside = [p for p in body.data.polygons
              if y_lo < p.center.y < y_hi and abs(p.center.x) < 8.05
              and zlo < p.center.z < zhi]
    dark = [p for p in inside if p.material_index != alu]
    share = len(dark) / max(1, len(inside)) * 100
    fails += check("rear bay floor is aluminium, not a black pocket",
                   share < 25.0, "%.0f%% of %d faces non-metal" % (share, len(inside)))

    # 7. the underside is solid: no ventilation mouths down there
    vents = [o for o in bpy.data.objects
             if o.name.startswith(("VentBore_", "VentCavity_", "VentLip_"))]
    fails += check("no ventilation intakes on the underside", not vents,
                   "%d found" % len(vents))

    print("\n%s (%d failures)" % ("PORTS_OK" if not fails else "PORTS_FAIL", fails))
    return fails


if __name__ == "__main__":
    main()
