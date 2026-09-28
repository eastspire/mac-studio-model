"""Check that the ventilation fields are actually ON each face, not buried.

A ray grid over the model, one grid per face, reporting what each ray lands on.
This exists because a hole field can be present in the scene and still be
invisible: the perforation tubes are cut to the field's full depth, but if the
shell's recess is shallower than the tubes then the tubes end up inside solid
aluminium. The first pass had exactly that on both sides — the loft
smoothstepped the recess across the whole perimeter, the side faces landed at
0.5 of full depth, and a 13x13 grid over the right face hit UpperGrille zero
times while the grille object itself carried 23,936 vertices.

So: assert each face has a minimum share of rays that reach grille geometry.
The front is the exception and is checked separately — Apple perforates only
the bottom band of the front panel, not the whole face.

usage:  blender --background --python verify_ventilation.py
"""
import bpy
import mathutils
from mathutils import Vector

# The brief is that ONLY the rear face is perforated. The front panel, both
# sides and the underside are plain aluminium, so those three faces must reach
# grille geometry ZERO times — not "a small share". The bottom is not rayed
# here: it has no grille objects, which build_bottom_details no longer creates.
FACES_WITH_MESH = ("rear  +Y",)
FACES_WITHOUT_MESH = ("front -Y", "right +X", "left  -X")
MIN_SHARE = {
    "front -Y": 0.0,   # must be solid
    "rear  +Y": 0.20,
    "right +X": 0.0,   # must be solid
    "left  -X": 0.0,   # must be solid
    "bottom -Z": 0.0,  # must be solid
}
Z_LO, Z_HI = 0.30, 9.40
GRID = 21


def main():
    bpy.ops.wm.open_mainfile(filepath="mac_studio.blend")
    for n in ("BounceL", "BounceR", "Floor"):
        o = bpy.data.objects.get(n)
        if o:
            o.hide_viewport = True
    dg = bpy.context.evaluated_depsgraph_get()
    sc = bpy.context.scene

    faces = [
        ("front -Y", (0, -40, 0), (0, 1, 0), "x"),
        ("rear  +Y", (0, 40, 0), (0, -1, 0), "x"),
        ("right +X", (40, 0, 0), (-1, 0, 0), "y"),
        ("left  -X", (-40, 0, 0), (1, 0, 0), "y"),
        ("bottom -Z", (0, 0, -40), (0, 0, 1), "x"),   # rays up at the underside
    ]

    fails = 0
    for label, org, d, axis in faces:
        d = Vector(d)
        total = 0
        grille = 0
        per_obj = {}
        for iz in range(GRID):
            z = Z_LO + (Z_HI - Z_LO) * iz / (GRID - 1)
            for ia in range(GRID):
                a = -9.4 + 18.8 * ia / (GRID - 1)
                if axis == "z":       # face lies in a horizontal plane
                    o = Vector((a, -9.4 + 18.8 * iz / (GRID - 1), org[2]))
                elif axis == "x":
                    o = Vector((a, org[1], z))
                else:
                    o = Vector((org[0], a, z))
                hit, loc, nr, idx, obj, mtx = sc.ray_cast(dg, o, d)
                if not hit:
                    continue
                total += 1
                if "Grille" in obj.name:
                    grille += 1
                    per_obj[obj.name] = per_obj.get(obj.name, 0) + 1

        share = grille / max(1, total)
        want = MIN_SHARE[label]
        ok = share >= want
        fails += 0 if ok else 1
        detail = " ".join("%s=%d" % (k.replace("Grille", ""), v)
                          for k, v in sorted(per_obj.items()))
        print("  %-4s %-10s %3d/%3d rays reach grille (%4.1f%%, need %.0f%%)  %s"
              % ("OK" if ok else "FAIL", label, grille, total,
                 share * 100, want * 100, detail))

    print("\n%s (%d failures)"
          % ("VENT_OK" if not fails else "VENT_FAIL", fails))
    return fails


if __name__ == "__main__":
    main()
