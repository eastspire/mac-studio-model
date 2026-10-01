"""Render the Mac Studio model from multiple views.

Loads the .blend produced by build_mac_studio.py, then places one camera per
view. Distance is derived from the model bounding sphere and the lens FOV
instead of hand-tuned numbers, so re-framing survives geometry edits.

usage:  blender --background --python render_views.py -- [out_dir] [samples]
"""

import math
import os
import sys

import bpy
from mathutils import Vector

# The canonical .blend lives next to the build script, which is where
# build_mac_studio.py writes it. This used to point at the repo root,
# where a second, older .blend sat: 97 objects, no RearField, no
# perforated field at all - the pre-fix machine. Every render and the
# published GLB were therefore built from the broken model while the
# gates read the correct one, and the two never disagreed out loud.
BLEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "mac_studio.blend"))
OUT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", sys.argv[sys.argv.index("--") + 1])
    if "--" in sys.argv
    else os.path.join(os.path.dirname(__file__), "..", "renders")
)
# Samples come from the environment. The old line indexed sys.argv for "--"
# twice on one line, and sys.argv.index RAISES when there is no "--" - which
# is every invocation without a passthrough separator, so the script could not
# be run the obvious way. Blender eats a bare trailing word on --python as a
# flag, so an env var is also the only channel that survives.
SAMPLES = int(os.environ.get("SAMPLES", "48"))

# Studio furniture, not part of the product. Excluded from framing and from
# any bounding-box measurement — bounce cards are 40cm wide and would swamp it.
EXCLUDE = {"Floor", "BounceL", "BounceR"}

# name, azimuth(deg), elevation(deg), lens(mm), target z-fraction, hide floor
# azimuth 270 deg = -Y = front of the machine
#
# Elevations are low on purpose. Apple's own product and hardware shots are
# near eye level, and a 12-degree downward tilt foreshortens the rear panel
# enough to hide the three-zone structure (upper perforation / port band /
# lower perforation) that a side-by-side comparison is checking for. Keep the
# elevation views explicit rather than folding a tilt into the three-quarter.
# azimuth, elevation, lens, z-focus, hide-floor, [zoom]
#
# Sign convention: +Y is the FRONT (2x USB-C, SDXC, status LED) and -Y is the
# REAR (the I/O row, the exhaust field, the power button), so
#   az  90 -> camera on +Y, looking at the FRONT
#   az 270 -> camera on -Y, looking at the REAR
#
# "01_front" and "03_rear" were swapped here exactly as they were in
# ortho_measure.py, so every published image was labelled with the wrong face:
# 01_front.png showed the rear elevation and vice versa. The three-quarter and
# hero angles are unaffected in the sense that they show the whole machine, but
# the flat and closeup views are face-specific and were all mirrored.
# THE AZIMUTHS HERE WERE WRONG, and the site published them. 244, 246 and 232
# are three-quarter angles: +Y is the front and -Y the rear, so a rear shot is
# az 270, and these four were rendering the machine's left flank while
# docs/index.html captioned them "Rear field", "Perforation macro", "Rear at eye
# level" and "Rear ports". Whoever made the PNGs by hand got it right, or
# nobody looked; the script could not have produced them.
VIEWS = [
    ("01_front", 90.0, 4.0, 62.0, 0.5, False),
    ("02_side", 180.0, 3.0, 62.0, 0.5, False),
    ("03_rear", 270.0, 4.0, 62.0, 0.5, False),
    ("04_hero", 35.0, 34.0, 58.0, 0.45, False),
    ("05_top", 90.0, 78.0, 62.0, 0.5, False),
    # A genuine underside view needs a steep elevation. At el -62 the camera
    # is still well above the horizon, so it shows the base band edge-on
    # rather than the perforated bottom cover - and the bottom cover is the
    # intake, so this shot is the only one that shows it.
    ("06_bottom", 90.0, -78.0, 62.0, 0.5, True),
    ("07_front_closeup", 90.0, 2.0, 90.0, 0.28, False),
    ("08_rear_closeup", 270.0, 4.0, 90.0, 0.45, False),
    # Dead-level rear elevation, matching the framing of Apple's own hardware
    # diagram so the two can be compared region for region.
    ("12_rear_flat", 270.0, 0.0, 70.0, 0.5, False),
    # Tight on the port row. The site gallery links to this as "Rear ports"
    # (docs/index.html), but it was never in VIEWS - the PNG and the published
    # JPEG were made by hand and no script could regenerate them, so the image
    # silently outlived the model it depicted. tools/publish_assets.py now
    # fails on any render not listed here, which is how this surfaced.
    ("21_rear_ports", 270.0, 2.0, 100.0, 0.16, False, 0.20),
    # Low three-quarter view hugging the base band. This is the only angle that
    # shows the perforations: from straight below the holes are edge-on, and
    # from eye level the band is a 1.6 cm strip hidden behind the machine.
    # distance is in body-heights, so anything under ~0.5 crops to a handful of
    # holes and reads as "barely perforated".
    ("09_grille_band", 268.0, -14.0, 99.0, 0.62, False),
    # Macro on the band itself (zoom 0.42 dollies in ~2.4x). The full-width
    # shot cannot resolve 1.2 mm holes on a 19.7 cm body — each hole lands at
    # ~10 px and the whole band reads as smooth metal.
    ("10_grille_macro", 270.0, -10.0, 99.5, 0.14, False, 0.42),
    # Straight-on the band's face, framed by hand: the auto-fit camera always
    # frames the whole 19.7 cm body, so a 1.6 cm strip is ~4% of the frame and
    # the holes vanish into it. This one looks square at the band from 6 cm,
    # low and to the front-right, where the perforations face the lens.
    ("11_grille_front", 270.0, -6.0, 99.5, 0.16, False, 0.16),
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


def place_camera(name, az, el, lens, target, radius, margin=1.18, zoom=1.0):
    cam_data = bpy.data.cameras.new(name)
    cam_data.lens = lens
    cam_data.sensor_width = 36.0
    cam = bpy.data.objects.new(name, cam_data)
    bpy.context.collection.objects.link(cam)

    # distance that fits the bounding sphere in the *narrower* image axis
    half_fov = math.atan(0.5 * cam_data.sensor_width / lens)   # horizontal
    half_fov_v = math.atan(half_fov * 1125.0 / 1500.0)          # vertical (4:3)
    # zoom < 1 dollies in past the bounding sphere: the sphere is derived from
    # the whole model, so a small feature (a 1.2 mm grille hole) is unresolvable
    # at fit distance no matter what `lens` says.
    dist = radius * margin * max(zoom, 1e-3) / math.sin(min(half_fov, half_fov_v))

    az_r, el_r = math.radians(az), math.radians(el)
    cam.location = Vector((
        target[0] + dist * math.cos(el_r) * math.cos(az_r),
        target[1] + dist * math.cos(el_r) * math.sin(az_r),
        target[2] + dist * math.sin(el_r),
    ))
    direction = (Vector(target) - cam.location).normalized()
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return cam


def main():
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    scene = bpy.context.scene
    lo, hi = model_bounds()
    size = hi - lo
    center = (lo + hi) / 2.0
    radius = size.length / 2.0
    print("MODEL size %.3f %.3f %.3f  center %s  radius %.2f"
          % (size.x, size.y, size.z, tuple(round(v, 3) for v in center), radius))

    scene.render.engine = "CYCLES"
    scene.cycles.samples = SAMPLES
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1500
    scene.render.resolution_y = 1125
    scene.render.image_settings.file_format = "PNG"

    floor = bpy.data.objects.get("Floor")
    os.makedirs(OUT_DIR, exist_ok=True)

    # ONLY=name,name lets one view be re-shot without paying for all of them.
    only = os.environ.get("RENDER_ONLY", "").strip()
    wanted = set(w.strip() for w in only.split(",")) if only else None

    for name, az, el, lens, zf, hide_floor, *rest in VIEWS:
        if wanted is not None and name not in wanted:
            continue
        if floor:
            floor.hide_render = hide_floor
        # optional trailing zoom: <1 dollies in for macro detail shots
        zoom = rest[0] if rest else 1.0
        target = (center.x, center.y, lo.z + size.z * zf)
        cam = place_camera("CAM_" + name, az, el, lens, target, radius, zoom=zoom)
        scene.camera = cam
        scene.render.filepath = os.path.join(OUT_DIR, name + ".png")
        bpy.ops.render.render(write_still=True)
        print("RENDERED %s  cam@%s d=%.1fcm"
              % (name, tuple(round(v, 1) for v in cam.location),
                 (cam.location - Vector(target)).length))
    print("RENDER_ALL_OK")


if __name__ == "__main__":
    main()
