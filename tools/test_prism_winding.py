"""Does an EXACT boolean treat this prism as a solid, and which winding?

Three of the four builds so far have failed in ways that look like winding.
The prism is a closed mesh with two n-gon caps, and EXACT decides inside from
outside using the surface normal. If the caps face the wrong way the
difference resolves the complement, and the symptom is unmistakable: the
cutter's own reach shows up as a bite taken out of the target, on a shell
that was intact before.

So this is a controlled test on a known solid, not on the model: build one
prism, subtract it from a cube, and report whether the cube kept its volume.
Run it before changing the real prisms, because a wrong answer here costs a
five-minute build each time.
"""
import math
import sys

import bpy
from mathutils import Vector

BLEND = "/Users/sqs/code/mac-studio-model/blender/mac_studio.blend"
OUT = "/Users/sqs/.hermes/cache/scratch/winding_test.blend"


def prism(n, span, flip_caps):
    vs = []
    for z in (0.0, span):
        for k in range(n):
            a = 2 * math.pi * k / n
            vs.append((0.30 * math.cos(a), 0.30 * math.sin(a), z))
    fs = []
    for k in range(n):
        k2 = (k + 1) % n
        fs.append((k, k2, n + k2, n + k))          # the side wall
    if flip_caps:
        fs.append(tuple(n + k for k in range(n - 1, -1, -1)))
        fs.append(tuple(k for k in range(n)))
    else:
        fs.append(tuple(k for k in range(n)))
        fs.append(tuple(n + k for k in range(n - 1, -1, -1)))
    me = bpy.data.meshes.new("prism")
    me.from_pydata(vs, [], fs)
    me.validate()
    return bpy.data.objects.new("prism", me)


def volume(ob):
    """Signed volume via the divergence theorem, from the mesh itself."""
    me = ob.data
    v = 0.0
    for p in me.polygons:
        vs = [me.vertices[i].co for i in p.vertices]
        for i in range(1, len(vs) - 1):
            a, b, c = vs[0], vs[i], vs[i + 1]
            v += a.dot(b.cross(c)) / 6.0
    return v


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene

    bpy.ops.mesh.primitive_cube_add(size=2.0)
    cube = bpy.context.object
    cube.name = "Target"
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=True)
    before = volume(cube)
    print("target volume %.4f" % before)

    results = {}
    for flip in (False, True):
        for span, loc_z in ((3.0, -1.5), (5.0, -2.5), (1.5, -0.75)):
            bpy.ops.wm.read_factory_settings(use_empty=True)
            sc = bpy.context.scene
            bpy.ops.mesh.primitive_cube_add(size=2.0)
            cube = bpy.context.object
            bpy.ops.object.transform_apply(location=True, rotation=False,
                                           scale=True)
            v0 = volume(cube)

            p = prism(10, span, flip)
            sc.collection.objects.link(p)
            p.location = (0.0, 0.0, loc_z)

            bpy.context.view_layer.objects.active = cube
            for o in bpy.context.selected_objects:
                o.select_set(False)
            cube.select_set(True)
            mod = cube.modifiers.new("Cut", "BOOLEAN")
            mod.operation, mod.object, mod.solver = "DIFFERENCE", p, "EXACT"
            bpy.ops.object.modifier_apply(modifier=mod.name)

            v1 = volume(cube)
            dg = bpy.context.evaluated_depsgraph_get()
            hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, Vector((0, 0, -5)),
                                                   Vector((0, 0, 1)))
            through = ("through" if not hit
                       else "hit %s at z=%.2f" % (ob.name, loc.z))
            # The prism's volume INSIDE a 2.0 cube: a 3.0 prism centred on it
            # contributes 2.0, a 5.0 one 2.0, a 1.5 one 1.5.
            inside = math.pi * 0.30 ** 2 * min(span, 2.0)
            delta = v0 - v1
            ok = abs(delta - inside) < inside * 0.15
            print("flip=%-5s span=%.1f  removed %.4f, expected %.4f  %s"
                  % (flip, span, delta, inside, "OK" if ok else "WRONG"))
            print("         ray down the axis: %s" % through)
            results[(flip, span)] = ok

    print()
    good = [k for k, ok in results.items() if ok]
    if good:
        print("CORRECT: %s" % (good,))
        return 0
    print("no combination removed the prism's own volume")
    return 1


main()
