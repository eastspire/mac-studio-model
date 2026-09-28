"""Orthographic face renders for pixel-diffing against Apple's diagrams.

The auto-framing in render_views fits the object's projected bounding box,
which on a flat-on elevation of a 19.7 x 19.7 x 9.5 cm block picks the wrong
extent and silently reports the chassis at h/w 0.75 instead of 0.48. Every
band measurement taken from such a frame is meaningless, so this module
places an ORTHO camera on an axis and frames the 20 cm cube explicitly.

Ortho also removes perspective foreshortening, so a feature at 16.5% of the
panel width in the render is at 16.5% on the machine.
"""
import bpy
import math
import os
import mathutils
from mathutils import Vector

M = mathutils.Vector
# Half-extent of the ortho frame. The machine is 19.7 cm across, so 10.6 cm
# half-extent leaves a ~4% margin and fills the frame. At the previous 11.0
# the block was fine, but the point of this camera is that the frame maps
# linearly onto the object, so the margin has to be tight and fixed.
RADIUS = 10.6


def look_at(obj, target, direction):
    d = (M(target) - obj.location).normalized()
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def render_face(name, azimuth_deg, out_path, res=(1200, 1200), samples=64,
                elevation_deg=0.0, hide=("Floor", "BounceL", "BounceR",
                                         "Key", "Top", "Rim", "Fill",
                                         "RearBayFill")):
    """Render the machine dead-on from `azimuth_deg` with an ortho camera.

    The frame is square and sized to RADIUS regardless of the machine's
    proportions, so the same call works for the front, rear, sides, top and
    bottom and every result is directly comparable.
    """
    bpy.ops.wm.open_mainfile(filepath="mac_studio.blend")
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False

    for h in hide:
        o = bpy.data.objects.get(h)
        if o:
            o.hide_render = True

    # A flat grey world plus one soft light. The studio rig is aimed at beauty
    # shots from 30-80 cm away, which leaves a dead-on ortho face almost
    # unlit and the perforations invisible; for a measurement pass the lighting
    # only has to be even.
    if not bpy.data.worlds.get("OrthoWorld"):
        w = bpy.data.worlds.new("OrthoWorld")
        w.use_nodes = True
        bg = w.node_tree.nodes["Background"]
        bg.inputs[0].default_value = (0.55, 0.56, 0.58, 1.0)
        bg.inputs[1].default_value = 1.0
    sc.world = bpy.data.worlds["OrthoWorld"]

    ld = bpy.data.lights.new("OrthoFill", "AREA")
    ld.energy, ld.size = 900.0, 40.0
    lo = bpy.data.objects.new("OrthoFill", ld)
    bpy.context.collection.objects.link(lo)
    lo.location = (24.0, 34.0, 30.0)
    lo.rotation_euler = (math.radians(46), 0.0, math.radians(145))

    cd = bpy.data.cameras.new("OrthoCam")
    cd.type = "ORTHO"
    cd.ortho_scale = RADIUS * 2.0
    cam = bpy.data.objects.new("OrthoCam", cd)
    bpy.context.collection.objects.link(cam)

    az, el = mathutils.Euler, None
    a, e = azimuth_deg, elevation_deg
    # camera sits on a sphere of radius 60 cm; ortho makes the distance moot
    cam.location = M((60 * math.cos(math.radians(e)) * math.cos(math.radians(a)),
                      60 * math.cos(math.radians(e)) * math.sin(math.radians(a)),
                      60 * math.sin(math.radians(e)) + 4.75))
    look_at(cam, (0, 0, 4.75), None)
    sc.camera = cam

    sc.render.filepath = out_path
    bpy.ops.render.render(write_still=True)
    print("ORTHO %-14s %s" % (name, out_path))
    return out_path


FACES = {
    "front": 270.0,   # -Y
    "rear": 90.0,     # +Y
    "right": 0.0,     # +X
    "left": 180.0,    # -X
    "top": 90.0,      # +Z (use elevation 90)
    "bottom": 270.0,  # -Z (use elevation -90)
}


def main():
    out = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "renders", "ortho"))
    os.makedirs(out, exist_ok=True)
    for name, az in FACES.items():
        el = 0.0
        if name == "top":
            az, el = 0.0, 90.0
        elif name == "bottom":
            az, el = 0.0, -90.0
        render_face(name, az, os.path.join(out, name + ".png"), elevation_deg=el)


if __name__ == "__main__":
    main()
