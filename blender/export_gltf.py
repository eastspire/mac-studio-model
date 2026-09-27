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
BLEND = os.path.abspath(os.path.join(HERE, "..", "mac_studio.blend"))
DEFAULT_OUT = os.path.abspath(os.path.join(HERE, "..", "docs", "mac-studio.glb"))

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else DEFAULT_OUT

# Studio furniture must not ship: the viewer supplies its own environment.
STUDIO = {"Floor", "BounceL", "BounceR"}

bpy.ops.wm.open_mainfile(filepath=BLEND)
scene = bpy.context.scene

# keep only the product
for obj in list(scene.objects):
    if obj.name in STUDIO or obj.type == "LIGHT" and obj.name == "LEDglow":
        bpy.data.objects.remove(obj, do_unlink=True)

# cameras/lights the renderer added are not needed by the viewer either
for obj in list(scene.objects):
    if obj.type in {"CAMERA", "LIGHT"}:
        bpy.data.objects.remove(obj, do_unlink=True)

bpy.ops.object.select_all(action="SELECT")

# normalise: the build works in centimetres, three.js wants metres
for obj in scene.objects:
    if obj.type != "MESH":
        continue
    obj.scale = tuple(c * 0.01 for c in obj.scale)
    obj.location = tuple(c * 0.01 for c in obj.location)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
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
)

size = os.path.getsize(OUT)
tris = sum(len(o.data.loop_triangles) for o in scene.objects if o.type == "MESH")
print("EXPORTED %s  %.2f MB" % (OUT, size / 1048576))
print("meshes=%d  tris=%d" % (
    len([o for o in scene.objects if o.type == "MESH"]), tris))
for o in scene.objects:
    if o.type == "MESH":
        print("  %-26s %6d tris" % (o.name, len(o.data.loop_triangles)))
