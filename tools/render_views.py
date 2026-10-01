"""Render the standard views from the saved .blend, without rebuilding it.

The build takes about eighteen minutes - 5,000-odd prisms through an EXACT
boolean in batches - and everything after it is a render. Rebuilding just to
look at the result is most of the cost of iterating on anything visual, so
this loads the .blend the build wrote and renders that.

The camera setup is imported from the builder rather than copied, so a change
to VIEWS applies to both. That import does not run main(): the builder
guards its entry point, and this only needs the tables and the camera
helper.

    blender --background --factory-startup --python tools/render_views.py
"""
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))

import build_mac_studio as B  # noqa: E402

BLEND = os.path.join(ROOT, "blender", "mac_studio.blend")


def main():
    if not os.path.exists(BLEND):
        print("no .blend at %s - run the builder first" % BLEND)
        return 1
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    sc = bpy.context.scene
    body = bpy.data.objects.get("Body")

    sc.render.engine = "CYCLES"
    sc.cycles.samples = int(os.environ.get("SAMPLES", "48"))
    sc.cycles.use_denoising = True
    sc.render.resolution_x = int(os.environ.get("WIDTH", "1500"))
    sc.render.resolution_y = int(os.environ.get("HEIGHT", "1125"))
    sc.render.image_settings.file_format = "PNG"

    # Blender 4.x defaults to AgX, an HDR tone mapper built to ROLL OFF
    # CONTRAST. It compresses the difference between a lit metal panel and the
    # shadow inside a 1.4 mm perforation until they read as the same value.
    # Measured with AgX in place: 87% of the pixels sat between 20 and 116,
    # and the panel and all of its holes were inside that one band, with a
    # local spread of 1.0 out of 255. The geometry was perfect the whole time -
    # every bore is real and a ray passes through it. AgX was erasing it.
    #
    # Apple's product photography is a direct tone map. A perforation is
    # 1.5 mm of black anodised bore and it has to be allowed to go black
    # against lit aluminium.
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = float(os.environ.get("EXPOSURE", "0.0"))
    sc.view_settings.gamma = 1.0

    only = os.environ.get("ONLY")
    want = set(only.split(",")) if only else None
    os.makedirs(B.OUT_DIR, exist_ok=True)
    print("rendering %d views at %dx%d, %d samples, from %s"
          % (len(B.VIEWS), sc.render.resolution_x, sc.render.resolution_y,
             sc.cycles.samples, os.path.basename(BLEND)))

    for name, kind, az, el, dist in B.VIEWS:
        if want and name not in want:
            continue
        # TARGETS is keyed by VIEW NAME, and the lookup below used the view's
        # `kind` instead - "front", "rear", "cutaway" rather than
        # "07_front_closeup". Every closeup silently fell back to the body
        # centre, so the two closeups framed the whole machine from 17 cm and
        # the cutaway framed the shell it was supposed to hide. Look up by
        # name, which is what the table holds.
        target = B.TARGETS.get(name, B.TARGETS.get(kind, (0.0, 0.0, B.H_TOTAL / 2.0)))
        if kind == "cutaway":
            # Hide the shell so the internals read. RearField is a cutter and
            # is deleted by the build, so guard rather than assume.
            if body:
                body.hide_render = True
            for o in sc.objects:
                if o.name == "RearField":
                    o.hide_render = True
        cam = B.place_camera("CAM_" + name, az, el, dist, target)
        # place_camera links through bpy.context.collection, which under
        # --background points at a default collection that does not exist:
        # the link silently does nothing, scene.camera stays None, and the
        # render comes out as an empty frame with no error anywhere. The .blend
        # this loads has no collections at all, so link the camera explicitly
        # and say so if it still is not in the scene.
        if cam.name not in sc.objects:
            sc.collection.objects.link(cam)
        if cam.name not in sc.objects:
            print("CAMERA_NOT_LINKED %s - the frame will be blank" % name)
            continue
        # Linking into the scene is not enough. Blender builds the render from
        # the VIEW LAYER's object list, and a camera linked after the .blend was
        # loaded does not appear there, so it is absent from every frame even
        # though sc.camera names it. Force a view-layer update.
        bpy.context.view_layer.update()
        if cam.name not in bpy.context.view_layer.objects:
            print("CAMERA_NOT_IN_VIEW_LAYER %s - the frame will be blank" % name)
            continue
        sc.camera = cam
        # The bounce cards stand at x = +/-34 cm, just outside the 19.7 cm
        # chassis, and a side view puts the camera at 46 cm - outside them. A
        # solid card between the camera and the machine hides the whole
        # subject: measured, a ray from the rear camera's position hits
        # BounceL before anything else. They are there to put a soft gradient on
        # the aluminium, so keep them in the light paths and take them out of
        # the camera's.
        for card in ("BounceL", "BounceR"):
            o = bpy.data.objects.get(card)
            if o:
                o.visible_camera = False
        # THE BOTTOM VIEW WAS BLACK BECAUSE THE BOTTOM IS PAINTED LIKE A
        # CAVITY. The underside's 98 faces carry Cavity_Black, whose base
        # colour is 0.012 - a matte void. That is the right material for the
        # inside of a shell and the wrong one for its exterior, and no amount
        # of light fixes it: a 1,800 W source and every ray path of the floor
        # plane turned off still produced a black plate.
        #
        # The floor plane did have to go, for a separate reason. It is 200 cm
        # across at z = 0 and the bottom camera sits 39 cm below it looking up,
        # so from underneath it fills the frame; hiding it from the camera is
        # not enough, every ray path has to be off or it still casts shadow.
        #
        # The real repair is in the builder, where the exterior faces get the
        # cavity's index. This is patched here as well so the saved .blend and
        # the render agree; a rebuild makes this redundant.
        if kind == "bottom":
            body = bpy.data.objects.get("Body")
            alu_idx = next((i for i, m in enumerate(body.data.materials)
                            if m and m.name == "Aluminium_Silver"), 0) if body else 0
            if body:
                me = body.data
                fixed = 0
                for p in me.polygons:
                    # The exterior faces sit at z = 0.00 exactly, and the cavity
                    # cutter's bottom cap reaches down to the same plane, so the
                    # selection has to be by position alone. Writing
                    # material_index is not enough on its own: Cycles reads the
                    # mesh through its evaluated copy, and without update() the
                    # render used the indices the file was loaded with. That is
                    # why the repaint appeared to do nothing while the rays
                    # still reported Cavity_Black underneath.
                    if p.center.z < 0.06 and abs(p.center.x) < 9.9 \
                            and abs(p.center.y) < 9.9 \
                            and p.material_index != alu_idx:
                        p.material_index = alu_idx
                        fixed += 1
                me.update()
                print("BOTTOM_REPAINT %d faces -> slot %d (%s)"
                      % (fixed, alu_idx,
                         me.materials[alu_idx].name if alu_idx < len(me.materials) else "?"))
            fl = bpy.data.objects.get("Floor")
            if fl:
                fl.visible_camera = False
                fl.visible_diffuse = False
                fl.visible_glossy = False
                fl.visible_transmission = False
                fl.visible_shadow = False
            ld = bpy.data.lights.new("UnderKey", "AREA")
            ld.energy = 900.0
            ld.size = 34.0
            lo = bpy.data.objects.new("UnderKey", ld)
            sc.collection.objects.link(lo)
            lo.location = (0.0, -4.0, -14.0)
            # +90 degrees, not -90. An area light emits along its local -Z, and
            # rotating by -90 about X sends that to -Y: the light was shining at
            # the side wall from nine centimetres below the floor, which is why
            # 900 W, 1,800 W and 6,000 W all produced the same black plate. The
            # power was never the variable; the direction was.
            lo.rotation_euler = (math.radians(90.0), 0.0, 0.0)
            lo.visible_camera = False
        else:
            ud = bpy.data.objects.get("UnderKey")
            if ud:
                bpy.data.objects.remove(ud, do_unlink=True)
            fl = bpy.data.objects.get("Floor")
            if fl:
                fl.visible_camera = True
                fl.visible_diffuse = True
                fl.visible_glossy = True
                fl.visible_transmission = True
                fl.visible_shadow = True
        sc.render.filepath = os.path.join(B.OUT_DIR, name + ".png")
        try:
            bpy.ops.render.render(write_still=True)
        except Exception as exc:
            print("GPU_FAIL %s (%s) -> CPU retry" % (name, exc))
            sc.cycles.device = "CPU"
            bpy.ops.render.render(write_still=True)
        print("RENDERED %s" % sc.render.filepath)
        if kind == "cutaway":
            if body:
                body.hide_render = False
            for o in sc.objects:
                if o.name == "RearField":
                    o.hide_render = False
    print("RENDER_DONE")
    return 0


sys.exit(main())
