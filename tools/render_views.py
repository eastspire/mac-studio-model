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
