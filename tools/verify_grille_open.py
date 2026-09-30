#!/usr/bin/env python3
"""Ray-cast probe: are the perforations real holes, and on the right faces?

A grille can carry 120,000 vertices, be present in the object list, and still
render as smooth metal. The only assertion that carries meaning is a ray
fired at the panel returning the feature, and it has to be run per face —
a field can be correctly drilled on the rear and buried in solid metal on a
side.

Run inside Blender:
    blender --background --factory-startup \
      --python tools/verify_ventilation.py -- [blend]
"""
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "blender"))

import mac_studio_spec as S  # noqa: E402

# name, (face outward normal), aperture in the spec, minimum share of rays
# that must reach through. The user declared the front and the sides SOLID, so
# their threshold is 0.0 and not a token value.
FACES = {
    "rear":  ((0, 1, 0),  S.UPPER_HALF_X, 0.25, S.UPPER_Z0, S.UPPER_Z1),
    "front": ((0, -1, 0), S.D / 2.0, 0.0, S.UPPER_Z0, S.UPPER_Z1),
    "left":  ((-1, 0, 0), S.D / 2.0, 0.0, S.UPPER_Z0, S.UPPER_Z1),
    "right": ((1, 0, 0), S.D / 2.0, 0.0, S.UPPER_Z0, S.UPPER_Z1),
}
# The wrap-around base band is a different lattice but the same test.
BAND = {
    "rear":  ((0, 1, 0), 0.20),
    "front": ((0, -1, 0), 0.20),
    "left":  ((-1, 0, 0), 0.20),
    "right": ((1, 0, 0), 0.20),
}


def probe(scene, origin, direction, far=0.40):
    """Return the list of surfaces a ray meets within `far` centimetres."""
    hits = []
    p = Vector(origin)
    d = Vector(direction).normalized()
    travelled = 0.0
    for _ in range(12):
        ok, loc, nrm, idx, obj, mtx = scene.ray_cast(
            bpy.context.evaluated_depsgraph_get(), p, d, distance=far)
        if not ok:
            break
        step = (Vector(loc) - p).length
        travelled += step
        if travelled > far:
            break
        hits.append((obj.name, (Vector(loc) - Vector(origin)).length))
        p = Vector(loc) + d * 1e-4
    return hits


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    blend = argv[0] if argv else os.path.join(ROOT, "blender", "mac_studio.blend")
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend))
    scene = bpy.context.scene
    bad = 0

    N = 46
    print("rear perforated field — %d x %d rays per face" % (N, N))
    print("  %-6s %8s %8s %8s  %s" % ("face", "aperture", "min req", "share", "verdict"))
    for face, (n, half, thresh, z0, z1) in sorted(FACES.items()):
        nrm = Vector(n)
        centre = nrm * (S.D / 2.0 if nrm.y else S.W / 2.0)
        centre.z = (z0 + z1) / 2.0
        if face == "rear":
            # sample only inside the field's own half-width
            u_lim = half
        else:
            u_lim = S.D / 2.0 - 1.6
        deep = 0
        total = 0
        for i in range(N):
            for j in range(N):
                u = -u_lim + 2 * u_lim * (i + 0.5) / N
                v = z0 + (z1 - z0) * (j + 0.5) / N
                if nrm.y:
                    p = Vector((u, nrm.y * (S.D / 2.0 + 0.30), v))
                else:
                    p = Vector((nrm.x * (S.W / 2.0 + 0.30), u, v))
                hits = probe(scene, p, -nrm)
                total += 1
                # "reached through" = the first surface is the recessed floor
                # or a hole wall, i.e. the ray got past the skin before the
                # first solid hit
                if hits and hits[0][0] in ("RearField", "BaseGrille", "Body"):
                    # measure how far in: a hole is deeper than the recess floor
                    if hits[0][1] > (S.UPPER_DEPTH if face == "rear"
                                     else S.GRILLE_RECESS) * 0.8:
                        deep += 1
        share = deep / float(total)
        ok = share >= thresh
        bad += 0 if ok else 1
        print("  %-6s %7.2fmm %7.2f%% %7.2f%%  %s"
              % (face, u_lim * 10, thresh * 100, share * 100,
                 "ok" if ok else "FAIL"))

    print("\nbase band — %d rays per face" % (40 * 40))
    for face, (n, thresh) in sorted(BAND.items()):
        nrm = Vector(n)
        deep = total = 0
        for i in range(40):
            for j in range(40):
                u = -7.0 + 14.0 * (i + 0.5) / 40
                v = S.GRILLE_BAND_Z0 + 0.1 + (S.GRILLE_BAND_Z1 - 0.2) * (j + 0.5) / 40
                if nrm.y:
                    p = Vector((u, nrm.y * (S.D / 2.0 + 0.30), v))
                else:
                    p = Vector((nrm.x * (S.W / 2.0 + 0.30), u, v))
                hits = probe(scene, p, -nrm)
                total += 1
                if hits and hits[0][1] > S.GRILLE_RECESS * 0.8:
                    deep += 1
        share = deep / float(total)
        ok = share >= thresh
        bad += 0 if ok else 1
        print("  %-6s min %.0f%%  got %5.1f%%  %s"
              % (face, thresh * 100, share * 100, "ok" if ok else "FAIL"))

    print("\n%s" % ("VENTILATION OK" if bad == 0
                    else "VENTILATION FAILED on %d face(s)" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
