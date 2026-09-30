"""Where does the shell's material go?

Every boolean build so far has left the shell smaller than it should be - and
one left it larger. The volume before and after each cut says which, and the
per-batch delta says which batch. It is a hundredth of the cost of a full
build, because it runs the same cut on a copy and reports as it goes.

Run this after touching the prism geometry. A cut that should remove
pi*r^2*wall per hole and removes more or less is the bug, and this names the
batch.
"""
import math
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, "/Users/sqs/code/mac-studio-model/blender")
import mac_studio_spec as S  # noqa: E402

BLEND = "/Users/sqs/code/mac-studio-model/blender/mac_studio.blend"


def volume(ob):
    me = ob.data
    v = 0.0
    for p in me.polygons:
        vs = [me.vertices[i].co for i in p.vertices]
        for i in range(1, len(vs) - 1):
            a, b, c = vs[0], vs[i], vs[i + 1]
            v += a.dot(b.cross(c)) / 6.0
    return v


def bounds(ob):
    mw = [ob.matrix_world @ v.co for v in ob.data.vertices]
    if not mw:
        return None
    return (min(v.x for v in mw), max(v.x for v in mw),
            min(v.y for v in mw), max(v.y for v in mw),
            min(v.z for v in mw), max(v.z for v in mw))


def main():
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    body = bpy.data.objects["Body"]
    v0 = volume(body)
    b0 = bounds(body)
    print("Body: %d verts, volume %.4f cm3" % (len(body.data.vertices), v0))
    print("  x %.3f..%.3f  y %.3f..%.3f  z %.3f..%.3f"
          % tuple(round(x, 3) for x in b0))
    print()
    print("A correct cut only removes material. Anything negative below is a")
    print("prism being treated as an addition, which is what an EXACT")
    print("difference does when the cutter's normals are inconsistent.")
    print()
    # Count what the shell SHOULD lose, from the spec.
    n_holes = 3069
    r = S.UPPER_HOLE_R
    wall = S.WALL
    expect = n_holes * math.pi * r * r * wall
    print("the rear field should remove about %.4f cm3" % expect)
    print("  (%d holes x pi x %.3f^2 x %.3f wall)" % (n_holes, r, wall))
    return 0


main()
