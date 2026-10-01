"""The one gate for the rear field: the panel must be BOTH intact and open.

Two measurements of this panel have each been wrong on their own, in
opposite directions, and both were reported as passes.

The ray_cast family asks "is the hole centre deeper than the skin". It
returns 0% because the skin's own faces sit a few thousandths of a millimetre
off the plane, 100% because a ray through a hole also crosses the panel's
inner face, and a drifting number in between depending on where the sample
landed relative to the bridge. The 37.4% and 72.7% figures came from it.

The hole-centre test asks "does a face of the outer skin cover the centre of
this hole". It has no threshold and cannot be argued with - a 1.42 mm hole
cannot contain a whole triangle, so an open hole has no face over its middle.
That is the right question, and it reported 100% open on a build that had
lost 3.7 mm of its top and 80% of its skin. A panel that is not there is
trivially a panel with no hole centres covered, and the test cannot tell that
from a perforated panel.

So the answer is the conjunction, and neither half is sufficient:

    the envelope must be intact  AND  the hole centres must be uncovered

A build that satisfies only the first is shut. A build that satisfies only the
second has been cut away. This prints both and refuses to pass unless both
hold, which is the whole point: the two failures were indistinguishable for
four commits because nothing ever asked for them at the same time.

    blender --background --factory-startup --python tools/rear_field.py
"""
import os
import sys
from collections import defaultdict

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))

import mac_studio_spec as S  # noqa: E402

BLEND = os.path.join(ROOT, "blender", "mac_studio.blend")

# The panel's outer skin is a plane at y = -D/2. The boolean leaves its faces
# within a few thousandths of a millimetre of it, so the selection has to allow
# that much. It must NOT be loose: at 500 um the selection swallows the side
# panels' corner fillets and the skin "covers" 205% of the band, which is
# impossible, and the reading is void.
TOL = float(os.environ.get("TOL", "0.0008"))

# How far around a hole centre to look for a covering face. Half the radius
# (0.355 mm) is well inside a 0.71 mm hole and well outside a triangle, so a
# hit here means the skin genuinely spans the hole.
PROBE = S.UPPER_HOLE_R * 0.5

DESIGN_HOLES = 2760
DESIGN_OPEN = 3.14159265 * S.UPPER_HOLE_R ** 2 / S.UPPER_PITCH ** 2


def check_envelope():
    """Is the shell still the size the spec says?"""
    body = bpy.data.objects.get("Body")
    if body is None:
        return None
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    lo = [1e9] * 3
    hi = [-1e9] * 3
    for v in me.vertices:
        co = (v.co[0], v.co[1], v.co[2])
        for a in range(3):
            if co[a] < lo[a]:
                lo[a] = co[a]
            if co[a] > hi[a]:
                hi[a] = co[a]
    ev.to_mesh_clear()
    got = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
    want = (S.W, S.D, S.H_TOTAL)
    return got, want, hi, lo


def check_open():
    """Is any hole centre covered by a face of the outer skin?"""
    me = bpy.data.objects["Body"].data
    y = -S.D / 2.0
    grid = defaultdict(list)
    skin = 0
    for p in me.polygons:
        if abs(p.center.y - y) < TOL:
            skin += 1
            grid[(int(p.center.x / 0.05), int(p.center.z / 0.05))].append(
                (p.center.x, p.center.z))

    def covered(px, pz, r):
        for i in range(int((px - r) / 0.05), int((px + r) / 0.05) + 1):
            for j in range(int((pz - r) / 0.05), int((pz + r) / 0.05) + 1):
                for (x, z) in grid.get((i, j), ()):
                    if (x - px) ** 2 + (z - pz) ** 2 <= r * r:
                        return True
        return False

    # one row through the middle of the field, every pitch, and the rows above
    # and below it: 41 x 3 = 123 probes across the panel's full width.
    zc = (S.UPPER_Z0 + S.UPPER_Z1) / 2.0
    probes = []
    for dz in (-S.UPPER_PITCH_Z, 0.0, S.UPPER_PITCH_Z):
        for k in range(-20, 21):
            probes.append((k * S.UPPER_PITCH, zc + dz))
    blocked = sum(1 for (x, z) in probes if covered(x, z, PROBE))
    return len(probes), blocked, skin


def main():
    if not os.path.exists(BLEND):
        print("no .blend at %s - run the builder first" % BLEND)
        return 1
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    bpy.context.view_layer.update()

    print("=" * 66)
    print("REAR FIELD GATE - both halves must hold")
    print("=" * 66)

    print()
    print("1. ENVELOPE - is the shell still the size the spec says?")
    env = check_envelope()
    if env is None:
        print("   no Body in the .blend")
        return 1
    got, want, hi, lo = env
    env_ok = True
    for axis, g, w in zip("XYZ", got, want):
        d = (g - w) * 10.0
        ok = abs(d) <= 1.0
        env_ok = env_ok and ok
        print("   %s  %.3f cm  want %.3f cm  delta %+6.3f mm  %s"
              % (axis, g, w, d, "ok" if ok else "OUT"))
    print("   spans x %+.3f..%+.3f  y %+.3f..%+.3f  z %+.3f..%+.3f"
          % (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))
    print("   -> %s" % ("intact" if env_ok else
                        "DAMAGED. A build that fails here is not a perforated"
                        " panel, it is a broken one."))

    print()
    print("2. OPENNESS - does a face of the outer skin cover any hole centre?")
    total, blocked, skin = check_open()
    open_pct = 100.0 * (1 - blocked / total)
    print("   %d probes across 3 rows, one every %.2f mm"
          % (total, S.UPPER_PITCH * 10))
    print("   skin faces in the plane: %d" % skin)
    print("   hole centres still covered: %d / %d" % (blocked, total))
    print("   -> %.1f%% open against a design of %.1f%%"
          % (open_pct, 100 * DESIGN_OPEN))
    open_ok = blocked == 0

    print()
    print("3. VERDICT")
    if env_ok and open_ok:
        print("   PASS - the shell is intact and the field is open.")
        return 0
    if env_ok:
        print("   SHUT - the panel is intact and has no holes in it. Every one of")
        print("          the %d hole centres is still covered by the outer skin."
              % blocked)
        return 1
    if not open_ok:
        print("   VOID - the field reads open only because most of the panel"
              " is gone.")
        print("          This is what a passing hole count looks like on a"
              " broken shell.")
        return 1
    print("   DAMAGED - the shell lost material AND the field is shut.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
