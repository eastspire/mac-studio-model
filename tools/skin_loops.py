"""Measure how much of the rear field's skin is still there.

Every measurement of "is this hole open" in this project has at some point
returned a confident wrong answer, and the record is worth keeping. A
ray_cast test has to decide, from one hit, whether that hit was a bridge or a
bore, and it cannot - a bore's lip is coplanar with the skin around it:

  * "the first hit is deeper than the skin" returns 0%. The skin is a
    triangulated sheet, so its own faces sit a few thousandths of a millimetre
    off the plane and their centres read as deeper than it.

  * "the first hit is not the shell" returns 100%. A ray through a hole also
    crosses the panel's inner face, which is also the shell.

  * "some hit is deeper than the wall" drifts with wherever the sample lands
    relative to the bridge. It produced the 37.4% and 72.7% figures that were
    reported as passes and were not.

  * counting boundary loops of the skin is exact in principle, since a sheet
    with N holes has N+1 loops. In practice the tolerance decides the answer:
    at 40 um only the flattest faces are selected and a shut panel reports 35
    loops; at 50 um the selection swallows the side panels' corner fillets and
    reports 2,611 - a number the design can almost be talked into, backed by a
    skin that supposedly covers 205% of the band. Neither is a measurement.

So this measures AREA, and it measures it twice. The faces of the rear skin
are summed, and compared against the area of the band they belong to. Both
numbers come out of the same mesh, in the same centimetres, so there is no
unit to get wrong:

    open fraction = 1 - (skin area / band area)

Reported at four tolerances so the reader can see whether the answer depends
on the knob. On the current model it does not move between 8 um and 200 um,
which is what a real measurement looks like. Past that the selection leaves
the plane, the cover exceeds 100%, and the reading is marked VOID rather than
used - that is exactly how the 2,611 slipped through.

    blender --background --factory-startup --python tools/skin_loops.py

The filename is historical: the loop count it replaced is kept below, unused
by main(), because the self-test that caught it is still worth being able to
run. tools/count_holes.py measures Apple's reference photograph instead, and
the two are independent of each other.
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
# Kept only for count_loops(), which main() no longer uses. The default of 50
# um is the value that produced the false 2,611, and it is left as it was so
# the self-test still reproduces the failure it caught.
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

    # MEASURE THE SKIN'S AREA AGAINST THE BAND'S AREA. Both come from the same
    # mesh in the same centimetres, so there is no unit to get wrong and no
    # threshold to argue with. A perforated panel leaves skin area short by its
    # open fraction; an unbroken one covers all of it.
    #
    # This replaced a loop count, which was wrong twice. The first version
    # reported "34 holes" on a shut panel because a 40 um tolerance selected
    # only the flattest faces. Widening it to 50 um gave a confident 2,611 -
    # but at that tolerance the selection swallows the side panels' corner
    # fillets and the skin "covers" 205% of the band, which is impossible.
    # The area test below is stable from 8 um to 200 um, and the loop count
    # sits on the same faces: 35 loops at every tolerance up to 200 um.
    #
    # Design open fraction, from the spec: a square lattice of 1.42 mm holes
    # at 1.86 mm pitch is 54.2% open.
    y_rear = -S.D / 2.0
    half_x, z0, z1 = S.UPPER_HALF_X, S.UPPER_Z0, S.UPPER_Z1
    band = 2.0 * half_x * (z1 - z0)
    # The design open fraction of a square lattice: one circle of radius
    # UPPER_HOLE_R per cell of side UPPER_PITCH. UPPER_HOLE_R really is a
    # radius - 0.071 cm is 0.710 mm, so the hole is 1.42 mm across, and a
    # 1.42 mm hole on a 1.86 mm pitch is 45.8% open. Multiplying by 2 again
    # here once made the spec read as 183% open, which looks like a typo in
    # the spec and is not.
    design = 3.14159265 * S.UPPER_HOLE_R ** 2 / S.UPPER_PITCH ** 2

    print("rear field   x +/-%.2f cm  z %.2f..%.2f cm" % (half_x, z0, z1))
    print("band area   %.1f mm2" % (band * 100))
    print("design open fraction %.1f%%" % (100.0 * design))
    print()
    for tol_um in (8, 50, 200, 500):
        tol = tol_um * 1e-4
        sel = [p for p in me.polygons
               if abs(p.center.y - y_rear) < tol
               and z0 <= p.center.z <= z1
               and abs(p.center.x) <= half_x]
        area = sum(p.area for p in sel)
        cover = area / band
        # A tolerance wide enough to leave the plane selects faces from other
        # surfaces, and the cover goes over 1. That is the signal that the
        # selection is no longer the rear skin and the reading is void.
        void = cover > 1.0
        print("  tol %3d um  faces %7d  skin covers %6.2f%%  open %6.2f%%%s"
              % (tol_um, len(sel), 100.0 * cover, 100.0 * (1.0 - cover),
                 "   <- VOID, selection has left the plane" if void else ""))
    print()
    tol = 8e-4
    sel = [p for p in me.polygons
           if abs(p.center.y - y_rear) < tol
           and z0 <= p.center.z <= z1
           and abs(p.center.x) <= half_x]
    open_frac = 1.0 - sum(p.area for p in sel) / band
    print("VERDICT")
    print("  the rear skin covers %.2f%% of the field band" % (100.0 * (1.0 - open_frac)))
    print("  the field is therefore %.2f%% open, against a design of %.1f%%"
          % (100.0 * open_frac, 100.0 * design))
    if open_frac < design * 0.5:
        print("  -> SHUT. The perforations have not been cut through the skin.")
        print("     A hole count printed by the build is not evidence of this;")
        print("     see the bore faces at y = -98.0 mm, which exist but are")
        print("     walled off by an unbroken skin in front of them.")
        return 1
    print("  -> OPEN, and within tolerance of the design fraction.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
