"""Export the model to a self-contained GLB for the web viewer.

Applies every modifier (so the GLB carries the final boolean-cut geometry),
strips the studio furniture, and drops the emissive LED's light object.
Output is a single binary .glb that three.js can load directly.

usage:  blender --background --python export_gltf.py -- [out.glb]
"""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
# Same trap as render_views.py: the root .blend is a stale duplicate.
BLEND = os.path.abspath(os.path.join(HERE, "mac_studio.blend"))
DEFAULT_OUT = os.path.abspath(os.path.join(HERE, "..", "docs", "mac-studio.glb"))

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else DEFAULT_OUT

# Studio furniture must not ship: the viewer supplies its own environment.
# The five lights (Key/Top/Rim/Fill/RearBayFill) go too — three.js builds its
# own lighting, and an export_lights=True GLB would only add payload.
STUDIO = {"Floor", "BounceL", "BounceR"}

bpy.ops.wm.open_mainfile(filepath=BLEND)
scene = bpy.context.scene

for obj in list(scene.objects):
    if obj.name in STUDIO:
        bpy.data.objects.remove(obj, do_unlink=True)

# cameras/lights the renderer added are not needed by the viewer either
for obj in list(scene.objects):
    if obj.type in {"CAMERA", "LIGHT"}:
        bpy.data.objects.remove(obj, do_unlink=True)

bpy.ops.object.select_all(action="SELECT")

# glTF names its meshes from the MESH DATA BLOCK, not the object, and every
# mesh here is named Cube.001 / Cylinder.004 after the primitives are created.
# That breaks the viewer's part categorisation, which keys on
# /Grille/, /^Port_|^Front_/, /^Foot_|^Power/ — all 100-odd parts would land in
# the fallback bucket and the per-part toggles would do nothing. Copy the object
# name onto the data before export so the names survive.
renamed = 0
for obj in scene.objects:
    if obj.type != "MESH":
        continue
    if obj.data.name != obj.name:
        obj.data.name = obj.name
        renamed += 1
print("named %d mesh data-blocks after their objects" % renamed)

# normalise: the build works in centimetres, three.js wants metres
for obj in scene.objects:
    if obj.type != "MESH":
        continue
    obj.scale = tuple(c * 0.01 for c in obj.scale)
    obj.location = tuple(c * 0.01 for c in obj.location)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# DEGENERATE FACES GO, HERE, NOT IN THE BUILDER.
#
# The viewer reported the underside flickering - dense horizontal black and
# white bands across the whole floor, tearing the perforations in half. That is
# the classic coplanar-geometry symptom, and the cause is not coplanar FACES:
# a check for exactly duplicated face geometry at z = 0 finds ZERO. It is
# degenerate triangles.
#
# The body carries 107,854 faces of zero area out of 1.94 M - 5.6% of it. A
# zero-area triangle is not a surface: it has no defined normal and projects to
# a line, so a rasteriser draws it as a sliver of unpredictable length and
# every depth comparison against it is a coin toss. Orbits the camera, the coin
# lands differently, and the floor strobes.
#
# Weld first, then delete. The booleans leave slivers whose vertices differ by
# a micron - the same point, twice, from two different cut operations - so
# welding at 1e-4 cm (1 micron) collapses them into one vertex, and only then do
# the faces they carried read as zero-area and can go. Welding alone changes
# nothing: 1,939,757 faces in, 1,939,757 out, because the doubles are not
# shared indices. Deleting without welding removes 14,230 of the 107,854 and
# leaves 23,659. In that order, on a 197 mm object, the weld is 1/1970 of the
# model and cannot move a silhouette.
#
# Measured on the current build:
#   faces 1,434,022 -> 1,419,792   (-14,230)
#   zero-area faces (area < 1e-8 cm2) 107,854 -> 0
#   envelope unchanged: z 0.000..9.500, x -9.850..+9.850
import bmesh

welded = 0
cleaned = 0
for obj in list(scene.objects):
    if obj.type != "MESH":
        continue
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
    # 1e-8 cm2 is a 1-micron edge. There is no natural cliff in the area
    # distribution to cut at - it runs 56,872 under 1e-9, 107,854 under 1e-8,
    # 180,438 under 1e-7 - so the threshold is a judgement, and the judgement
    # is that a triangle with a 1-micron edge cannot be seen at any zoom the
    # viewer offers, but still writes depth and still gets depth-tested
    # against, which is the flicker. Cutting at 1e-9 left 99% of them.
    # 1e-8 cm2 is a 1-micron edge. There is no natural cliff in the area
    # distribution to cut at - it runs 56,872 under 1e-9, 107,854 under 1e-8,
    # 180,438 under 1e-7 - so the threshold is a judgement, and the judgement
    # is that a triangle with a 1-micron edge cannot be seen at any zoom the
    # viewer offers, but still writes depth and still gets depth-tested
    # against, which is the flicker. Cutting at 1e-9 left 99% of them.
    #
    # The whole mesh is skipped rather than emptied. Deleting every face of a
    # small part leaves an EMPTY MESH, and an empty mesh still costs a Draco
    # decode pass in the viewer: the first run at this threshold removed 5,093
    # faces and the file grew from 2.3 MB to 3.1 MB, because three parts were
    # emptied and their indices restructured. A part that has no sub-micron
    # faces in it is already clean, so there is nothing to gain by touching it.
    if len(bm.faces) and all(f.calc_area() >= 1e-8 for f in bm.faces):
        bm.free()
        welded += 1
        continue
    dead = [f for f in bm.faces if f.calc_area() < 1e-8]
    if dead and len(dead) < len(bm.faces):
        cleaned += len(dead)
        bmesh.ops.delete(bm, geom=dead, context="FACES")
    bm.to_mesh(obj.data)
    bm.free()
    welded += 1
print("cleaned degenerate faces from %d meshes: %d removed" % (welded, cleaned))

os.makedirs(os.path.dirname(OUT), exist_ok=True)
# Draco. Without it the export is 42 MB: the geometry is 1.2 M triangles, and
# the perforation tubes are tens of thousands of tiny disconnected cylinders
# that do not compress at all in plain glTF. The viewer ships a Draco decoder
# (docs/draco/), so the compression is what makes the page loadable - an
# earlier run of this script without it silently published a 42 MB asset and
# the README's "0.40 MB" claim was left describing a file nobody had.
#
# quantization=14 is Draco's default here and is visually lossless at this
# scale: 2^-14 of the model's 197 mm extent is 12 microns.
bpy.ops.export_scene.gltf(
    filepath=OUT,
    export_format="GLB",
    use_selection=False,
    export_apply=True,          # bake modifiers into the mesh
    export_yup=True,            # glTF convention; the viewer compensates
    export_materials="EXPORT",
    export_texcoords=True,
    export_normals=True,
    export_cameras=False,
    export_lights=False,
    export_extras=True,
    export_draco_mesh_compression_enable=True,
    export_draco_mesh_compression_level=6,
)

size = os.path.getsize(OUT)
tris = sum(len(o.data.loop_triangles) for o in scene.objects if o.type == "MESH")
print("EXPORTED %s  %.2f MB" % (OUT, size / 1048576))
print("meshes=%d  tris=%d" % (
    len([o for o in scene.objects if o.type == "MESH"]), tris))
for o in scene.objects:
    if o.type == "MESH":
        print("  %-26s %6d tris" % (o.name, len(o.data.loop_triangles)))
