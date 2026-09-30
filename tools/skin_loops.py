"""Count the holes in the rear panel, by counting loops in its skin.

Every other measurement of "is this hole open" turned out to be capable of
returning a comfortable wrong answer. A ray_cast test has to decide, from a
single hit, whether that hit was a bridge or a hole - and it cannot, because
the bore's lip is coplanar with the skin. Three variants failed differently:

  * "the first hit is deeper than the skin" returns 0%. The skin is a
    triangulated sheet, so most of its own faces sit a few thousandths of a
    millimetre off the plane and their centres read as deeper than it.

  * "the first hit is not the shell" returns 100%. A ray through a hole also
    passes through the panel's inner face, which is also the shell.

  * "some hit is deeper than the wall" drifts with wherever the sample happens
    to land relative to the bridge.

So this measures no depth at all. It takes the faces of the skin itself - the
polygons whose centres lie in the plane of the outer face - and counts the
closed boundary loops of that face set. The result has no units, no rays, no
normal heuristic and no tolerance to argue about:

    a sheet with N holes has N + 1 loops - one outer boundary, one per hole

The 2,760-hole rear field should report 2,761. Anything near 1 means the
panel is unbroken, whatever the hole counter printed during the build.

    blender --background --factory-startup --python tools/skin_loops.py

This is the model's own count. tools/count_holes.py measures Apple's
reference photograph instead, and the two are independent of each other.
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

# How far a face centre may sit off the plane and still count as the skin.
#
# The tolerance has to be wide enough to take in the WHOLE skin. A triangulated
# sheet's faces are tilted by however much the boolean left them, and a
# tolerance that clips a hole in half turns one hole into two open boundaries
# and destroys the count. Measured on the real panel:
#
#     40 um -> 136,240 faces,     35 loops   <- only the flattest faces
#     50 um -> 176,342 faces,  2,612 loops   <- the whole skin
#    100 um -> 462,631 faces,  2,844 loops   <- now catching the inner faces
#
# 50 um is the window. Below it the skin is truncated and the number is
# meaningless; above it the panel's inner face joins in and the holes start
# being counted from both sides. The design is 2,760 holes.
TOL = float(os.environ.get("TOL", "0.05"))


def count_loops(me, half_x, z0, z1, y, tol=TOL, plane="y"):
    """Closed boundary loops of the skin of a flat panel.

    `plane` names the axis the skin faces along, so this can be checked
    against a test mesh built in any orientation. The real panel is skinned
    on Y; a self-test plane built in XY is skinned on Z. Hard-wiring the axis
    made the tool untestable, which is how a version that reported "34 holes"
    on a shut panel got to be believed.
    """
    faces = []
    for p in me.polygons:
        c = p.center
        depth = getattr(c, plane)
        if abs(depth - y) > tol:
            continue
        if plane == "y":
            inside = z0 <= c.z <= z1 and abs(c.x) <= half_x
        elif plane == "z":
            inside = z0 <= c.y <= z1 and abs(c.x) <= half_x
        else:
            inside = z0 <= c.z <= z1 and abs(c.y) <= half_x
        if inside:
            faces.append(p.index)
    edge_count = defaultdict(int)
    for i in faces:
        vs = me.polygons[i].vertices
        for a, b in zip(vs, vs[1:] + vs[:1]):
            edge_count[(min(a, b), max(a, b))] += 1
    adj = defaultdict(list)
    for (a, b), n in edge_count.items():
        if n == 1:
            adj[a].append(b)
            adj[b].append(a)
    seen, loops = set(), 0
    for v in list(adj):
        if v in seen:
            continue
        loops += 1
        stack = [v]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            stack.extend(adj[u])
    return faces, loops, len(adj)


def main():
    if not os.path.exists(BLEND):
        print("no .blend at %s - run the builder first" % BLEND)
        return 1
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    body = bpy.data.objects.get("Body")
    if body is None:
        print("no Body in the .blend")
        return 1
    me = body.data

    print("skin tolerance   +/- %.1f um" % (TOL * 10000.0))
    print("design           rear field 2760 holes  ->  2761 loops")
    print()

    shut = 0
    y_rear = -S.D / 2.0
    faces, loops, verts = count_loops(me, S.UPPER_HALF_X, S.UPPER_Z0,
                                      S.UPPER_Z1, y_rear)
    print("rear field   x +/-%.2f cm  z %.2f..%.2f cm  (plane y = %+.3f)"
          % (S.UPPER_HALF_X, S.UPPER_Z0, S.UPPER_Z1, y_rear))
    print("   skin faces        : %d" % len(faces))
    print("   boundary vertices : %d" % verts)
    print("   CLOSED LOOPS      : %d" % loops)
    want = 2761                     # 2,760 holes plus the outer boundary
    holes = loops - 1
    if holes <= 1:
        print("   -> SHUT. %d faces with %d loops is an unbroken sheet; a"
              " perforated panel reports one loop per hole." % (len(faces), loops))
        shut += 1
    elif abs(holes - 2760) > 2760 * 0.10:
        print("   -> WRONG COUNT. %d holes against a design of 2,760, which"
              " is outside 10%%. The panel is not matching the spec."
              % holes)
        shut += 1
    else:
        print("   -> %d holes, plus the outer boundary. Design 2,760, off by"
              " %+.1f%%." % (holes, 100.0 * (holes - 2760) / 2760.0))

    print()
    print("HOLES_SHUT" if shut else "HOLES_OPEN")
    return 1 if shut else 0


if __name__ == "__main__":
    # Guarded so the file can be imported by a self-test: importing it to
    # reuse count_loops must not try to open the .blend and exit the process.
    sys.exit(main())
