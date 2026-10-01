"""Gate on the front panel being CUT, measured on the built .blend.

This is the check d5fd74e believed it had. It shipped a face census - sum the
area of the shell's faces over the port strip and compare it with the strip's
area - and the census said CUT, because the boolean leaves the skin fragmented
into thousands of small faces and the strip's total came out below the strip's
area. Fragmented is not open: the same geometry covered 88-97% of each port's
footprint and a ray down the middle of every port still stopped on metal.

So this asserts on RAYS, which is what "open" means, and reports the shallowest
and deepest open reading beside the percentage, so a regression shows up as a
number moving rather than as a picture that happens to look wrong.

  blender --background --python blender/check_front_cut.py -- [other.blend]

The path argument is what makes the gate falsifiable: run it against the
revision that shipped the bug and it must FAIL. An earlier version ignored the
argument, so pointing it at the pre-fix model printed a confident PASS - a
gate that has only ever been run against a good build has never been tested
at all, and it cannot tell a real pass from a check that measured nothing.
"""
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
# anything after "--" on Blender's own command line, else the built .blend
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
BLEND = argv[0] if argv else os.path.join(HERE, "mac_studio.blend")
if not os.path.isfile(BLEND):
    print(f"no such .blend: {BLEND}")
    sys.exit(2)
IO_Z = 2.35
D_HALF = 9.85
WALL = 0.15
# The cutter is the port OVERSIZED by 0.10 cm on every side and bevelled by
# 0.05, so the aperture in the skin is (w + 0.20) x (h + 0.20) with a 0.5 mm
# chamfered lip. That lip is real geometry - a machined port has one - so the
# samples stay INSIDE the port's own rectangle and never touch it. Sampling
# over the cutter's rectangle and calling the lip "capped" is how this check
# first reported 6-13% blocked on a panel that is open:
#
#     USBC_1   80.5% open, 15.5% on the skin, 4.1% no hit
#
# and every "on the skin" figure was a single 2.5 mm column at the very edge -
# the bevel, sampled at a step coarser than the bevel is wide.
FRONT_PORTS = [
    ("USBC_1", -6.626, 0.26, 0.850),
    ("USBC_2", -5.148, 0.27, 0.850),
    ("SDXC", -2.447, 2.700, 0.270),
]
STEP = 0.02                 # cm; an eighth of the SDXC slot's 2.7 mm height

# A point is CAPPED when the ray meets the SHELL at the skin - the failure
# d5fd74e shipped. Two other things sit legitimately just inside an opening and
# must not be counted as a lid:
#
#   1.0 mm  the socket's walls (_wt/_wb/_wl/_wr), which add_socket() builds
#           INSIDE the port's own footprint, wall by wall, at y_mouth - 0.10
#           with a 0.045 cm wall. That is what a socket IS.
#   2.4 mm  the tongue (_tg) and the back plate (_bk).
#
# An earlier version measured "any metal in the way" and called 38-43% of every
# correctly-built port capped. A gate that cannot tell a socket from a lid is
# measuring itself, and its output reads exactly like a finding - so the name
# test below is load-bearing, not cosmetic.
CAP_MM = 0.6
MAX_CAPPED_FRACTION = 0.02

bpy.ops.wm.open_mainfile(filepath=BLEND)
scene = bpy.context.scene
deps = bpy.context.evaluated_depsgraph_get()
body = next((o for o in scene.objects
             if o.type == "MESH" and (o.name == "Body" or o.name.startswith("Body_"))),
            None)
if body is None:
    print("the shell mesh was not found in", BLEND)
    sys.exit(2)


def cast(x, z):
    """(depth_mm, what_stopped_the_ray); depth None where the ray got right in."""
    hit, loc, _n, _i, ob, _m = scene.ray_cast(
        deps, Vector((x, D_HALF + 3.0, z)), Vector((0.0, -1.0, 0.0)), distance=40.0)
    if not hit:
        return None, None
    return (D_HALF - loc.y) * 10.0, ob.name


def is_capped(depth, name):
    """A cap is the panel's own skin at the port. A socket is not a cap."""
    if depth is None:
        return False
    on_panel = name == "Body" or name.startswith("Body_")
    return on_panel and depth < CAP_MM


print(f"front panel openness, {STEP * 10:.1f} mm grid over each PORT's own "
      f"footprint")
print(f"model: {os.path.relpath(BLEND, os.path.dirname(HERE))}")
print(f"(the skin is at y = {D_HALF}, the wall is {WALL * 10:.1f} mm)")
print("a point is CAPPED when the ray meets the shell's own skin there. The")
print("socket's walls sit 1.0 mm in and its tongue 2.4 mm in, and both are")
print("correct - a socket is supposed to be metal.")
print()
print(f"{'port':8s} {'points':>7s} {'capped':>7s} {'pct':>6s}  "
      f"{'shallowest open':>16s}  {'deepest':>9s}")

fails = []
for name, cx, w, h in FRONT_PORTS:
    total = n_capped = 0
    stopper = None
    shallowest = deepest = None
    x = cx - w / 2
    while x <= cx + w / 2 + 1e-9:
        z = IO_Z - h / 2
        while z <= IO_Z + h / 2 + 1e-9:
            depth, ob = cast(x, z)
            total += 1
            if is_capped(depth, ob):
                n_capped += 1
                if stopper is None:
                    stopper = f"{ob} at {depth:.2f} mm"
            elif depth is not None:
                if shallowest is None or depth < shallowest:
                    shallowest = depth
                if deepest is None or depth > deepest:
                    deepest = depth
            z += STEP
        x += STEP
    frac = n_capped / total if total else 1.0
    fmt = lambda v: f"{v:.2f} mm" if v is not None else "-"   # noqa: E731
    print(f"{name:8s} {total:7d} {n_capped:7d} {100 * frac:5.1f}%  "
          f"{fmt(shallowest):>16s}  {fmt(deepest):>9s}")
    if frac > MAX_CAPPED_FRACTION:
        fails.append(f"{name}: {100 * frac:.1f}% of the port is still capped "
                     f"({stopper})")

# NEGATIVE controls. If either reads open, the model has a hole where it should
# not, and the ports' reading means nothing. These call cast() and NOT
# is_capped(), because the question is that the ray hits SOMETHING: the LED is a
# separate lens standing 0.7 mm proud of the skin and is supposed to stop it.
print()
for label, x, z in (("LED", 6.619, IO_Z), ("blank panel", 3.2, 5.4)):
    depth, ob = cast(x, z)
    stopped = depth is not None and depth < CAP_MM
    state = (f"solid ({ob} at {depth:.2f} mm)" if stopped
             else "OPEN - a hole where there should be metal")
    print(f"  control {label:12s} {state:44s} {'ok' if stopped else 'UNEXPECTED'}")
    if not stopped:
        fails.append(f"control {label} reads {state}")

# POSITIVE control: the rear I/O row has always been cut correctly. If it reads
# capped, the instrument cannot see a cut at all and every port above is
# meaningless. The rear is the -Y face, so the ray starts on the other side.
print()
hit, loc, _n, _i, ob, _m = scene.ray_cast(
    deps, Vector((6.801, -(D_HALF + 3.0), IO_Z)), Vector((0.0, 1.0, 0.0)),
    distance=40.0)
if hit:
    rear_depth = (D_HALF - loc.y) * 10.0
    rear_ok = rear_depth > CAP_MM or not (ob.name == "Body"
                                          or ob.name.startswith("Body_"))
    state = ("open - reached the socket" if rear_ok
             else f"capped ({ob.name} at {rear_depth:.2f} mm)")
    print(f"  control {'rear TB5_1':12s} {state:44s} {'ok' if rear_ok else 'UNEXPECTED'}")
    if not rear_ok:
        fails.append("the rear I/O row reads capped, so this gate cannot see a "
                     "cut and the front result is void")
else:
    print(f"  control {'rear TB5_1':12s} {'no hit at all':44s} UNEXPECTED")
    fails.append("the rear I/O row returned no hit")

print()
if fails:
    for f in fails:
        print("FAIL ", f)
    print()
    print(f"FRONT PANEL NOT OPEN ({len(fails)} problem(s))")
    sys.exit(1)
print("FRONT PANEL OPEN - every port is a real hole through the skin, the solid")
print("controls are solid, and the rear row is still open (the gate can see a cut).")
sys.exit(0)
