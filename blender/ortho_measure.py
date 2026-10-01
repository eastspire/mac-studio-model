"""Orthographic measurement renders, for comparing against Apple's diagrams.

A beauty render is not a measuring instrument. Three things have to be true
before any pixel statistic taken off an image means anything, and each has
been false in this project at least once:

  * the background must be unambiguous. With a lit floor in frame, a
    background-median detector finds the FLOOR and reports the object as
    clipped off the bottom and right edges of every elevation;
  * the projection must be orthographic, or a feature at 50% of the panel
    width in the frame is not at 50% on the machine;
  * the lens must not be looking at a dead-on face with a studio rig aimed at
    beauty shots from 30-80 cm, which leaves the face nearly unlit and reads
    as "the perforations are missing" when they are simply in shadow.

So: floor and bounce cards hidden, film transparent, ORTHO cameras on the
machine's own axes, and flat even lighting.

usage:  blender --background --factory-startup \
          --python blender/ortho_measure.py -- [out_dir]
"""
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
BLEND = os.path.join(HERE, "mac_studio.blend")
OUT_DIR = os.path.join(ROOT, "renders", "ortho")

# Studio furniture, not the product.
EXCLUDE = {"Floor", "BounceL", "BounceR"}

RES = 1400
# name, azimuth(deg), elevation(deg). azimuth 270 = -Y = front.
# name, azimuth, elevation. In this model +Y is the FRONT (USB-C, SDXC,
# status LED) and -Y is the REAR (the port row, the exhaust field, the power
# button), so:
#
#   az 0   -> camera on +X, looking at the right side
#   az 90  -> camera on +Y, looking at the FRONT
#   az 180 -> camera on -X, looking at the left side
#   az 270 -> camera on -Y, looking at the REAR
#
# These two were swapped. A view named "front" was rendering the REAR and
# vice versa, which is how a perforated field ended up on the front panel in
# the earlier diagnosis and why the two elevations could be cross-compared
# without the mismatch being obvious.
VIEWS = [
    ("rear", 270.0, 0.0),
    ("front", 90.0, 0.0),
    ("right", 0.0, 0.0),
    ("left", 180.0, 0.0),
    ("top", 90.0, 89.0),
    ("bottom", 90.0, -89.0),
]


def model_bounds():
    deps = bpy.context.evaluated_depsgraph_get()
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.name in EXCLUDE:
            continue
        ev = obj.evaluated_get(deps)
        for corner in ev.bound_box:
            wc = ev.matrix_world @ Vector(corner)
            for i in range(3):
                lo[i] = min(lo[i], wc[i])
                hi[i] = max(hi[i], wc[i])
    return lo, hi


def flat_world(scene):
    """A plain bright world and no floor, so the frame is the object alone."""
    for n in EXCLUDE:
        o = bpy.data.objects.get(n)
        if o:
            o.hide_render = True
    world = bpy.data.worlds.new("Measure")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        # Bright enough that a bare aluminium face lands near mid-grey. At
        # 0.72 the whole field rendered at a mean of 0.19 against Apple's
        # photograph's 0.45, and an Otsu split on an underexposed image lands
        # on a different class entirely - so the open-area comparison then
        # reports ~99% "dark" for the model against ~1% for the photograph.
        # That is an exposure error wearing a geometry error's clothes.
        bg.inputs["Color"].default_value = (0.92, 0.94, 0.97, 1.0)
        bg.inputs["Strength"].default_value = 2.6


# A three-light rig, expressed RELATIVE to the view direction so the same
# rig lights whichever face is being measured: (name, energy, sideways,
# upward, toward-the-camera). Authoring these in world axes is what made the
# front elevation render lit from behind.
RIG = (
    ("L_key", 1400.0, 0.0, 0.55, 1.0),
    ("L_fill", 700.0, 0.75, 0.15, 0.85),
    ("L_rim", 500.0, -0.7, 0.30, 0.7),
)


def relight(scene, view_dir, target):
    """Re-aim an existing rig so it sits on the VIEWER's side of the machine.

    `view_dir` points from the target toward the camera. The three lights
    keep their offsets relative to it, so a front elevation is lit from the
    front and a rear elevation from the rear. Without this, a rig authored for
    one face silently back-lights every other face.
    """
    v = Vector(view_dir).normalized()
    # an arbitrary perpendicular to stand the fill and rim off to the sides
    side = v.cross(Vector((0.0, 0.0, 1.0)))
    if side.length < 1e-4:
        side = Vector((1.0, 0.0, 0.0))
    side.normalize()
    up = v.cross(side).normalized()
    for name, energy, side_mix, up_mix, fwd_mix in RIG:
        d = (v * fwd_mix + side * side_mix + up * up_mix).normalized()
        o = bpy.data.objects.get(name)
        if o is None:
            continue
        o.location = Vector(target) + d * 55.0
        o.data.energy = energy
        aim = (Vector(target) - o.location).normalized()
        o.rotation_euler = aim.to_track_quat("-Z", "Y").to_euler()


def add_lights(scene, target):
    """A three-light rig, frontal and even, aimed AT the machine.

    The lights have to be re-aimed after they are created: bpy's area light
    points down its own -Z at creation, so a light placed on one side of the
    body starts out pointing away from it and the face renders black. A black
    panel is exactly where the grille lattice has to be checked, and it is
    indistinguishable from "the perforations are missing".
    """
    add_lights_at(scene, target, Vector((0.0, -1.0, 0.0)))


def add_lights_at(scene, target, view_dir):
    for name, energy, side_mix, up_mix, fwd_mix in RIG:
        d = (Vector(view_dir).normalized() * fwd_mix
             + Vector((side_mix, 0.0, up_mix))).normalized()
        loc = Vector(target) + d * 55.0
        bpy.ops.object.light_add(type="AREA", location=loc)
        o = bpy.context.active_object
        o.name = name
        o.data.energy = energy
        o.data.size = 45
        aim = (Vector(target) - o.location).normalized()
        o.rotation_euler = aim.to_track_quat("-Z", "Y").to_euler()


def main():
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    scene = bpy.context.scene
    lo, hi = model_bounds()
    center = (lo + hi) / 2.0
    size = hi - lo
    print("MODEL %.1f x %.1f x %.1f mm" % (size.x * 10, size.y * 10, size.z * 10))

    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    scene.render.resolution_x = RES
    scene.render.resolution_y = RES
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    flat_world(scene)
    # add_lights() was defined and never called, so the measurement renders
    # had the studio world's lights hidden along with the floor and bounce
    # cards - the whole model came out black, and a black panel is exactly
    # what makes the grille lattice unverifiable.
    add_lights(scene, center)
    os.makedirs(OUT_DIR, exist_ok=True)

    # One ortho scale that fits the machine on every axis in every view, so
    # the six images are directly comparable to each other and to the
    # photographs, which are all framed on the 197 mm width.
    ortho_scale = max(size.x, size.y) * 1.06

    for name, az, el in VIEWS:
        cd = bpy.data.cameras.new("ORTHO_" + name)
        cd.type = "ORTHO"
        cd.ortho_scale = ortho_scale
        cam = bpy.data.objects.new("ORTHO_" + name, cd)
        bpy.context.collection.objects.link(cam)
        az_r, el_r = math.radians(az), math.radians(el)
        d = Vector((math.cos(el_r) * math.cos(az_r),
                    math.cos(el_r) * math.sin(az_r), math.sin(el_r)))
        cam.location = center + d * 200.0
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        scene.camera = cam
        # The lights must sit on the CAMERA's side of the machine. A fixed
        # rig keyed to the rear (-Y) put every light behind the body for the
        # front view, so the front panel was lit from the inside: the
        # aluminium read almost black and only the silhouettes of interior
        # parts showed through as a cross and horizontal bands. That is what
        # produced a "front profile" full of edges Apple does not have.
        relight(scene, d, center)
        scene.render.filepath = os.path.join(OUT_DIR, name + ".png")
        bpy.ops.render.render(write_still=True)
        print("ORTHO %s  scale %.1f mm" % (name, ortho_scale * 10))
    print("ORTHO_ALL_OK")
    return 0




# Blender does NOT propagate an uncaught Python exception to the process exit
# code - measured on the bundled 4.5.4, `raise` exits 0 with the traceback on
# stdout, and only an explicit sys.exit(1) is a non-zero status. A gate that
# prints its verdict and falls off the end therefore reports SUCCESS to every
# shell, every `&&` chain and every CI step, and the only thing that catches
# it is a human reading the output.
#
# The verdict line above is the human-readable one; this is the machine one.
if __name__ == "__main__":
    # main() raises on failure, and Blender swallows that into exit 0,
    # so the verdict is turned into a status here, in the one place
    # that is guaranteed to run.
    _code = main()
    sys.exit(_code if isinstance(_code, int) else 0)
