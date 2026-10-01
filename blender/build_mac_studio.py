"""Mac Studio (2026, M5 Max) 1:1 model — headless bpy build.

Official specs (https://www.apple.com/mac-studio/specs/, checked 2026-09-30;
Apple Support 128107 for the 2026 machine):
    Height  3.7 in (9.5 cm)      Weight 6.0 lb (2.7 kg)
    Width   7.7 in (19.7 cm)     Rear:  4x Thunderbolt 5 (USB-C), 10GbE,
    Depth   7.7 in (19.7 cm)            AC inlet, 2x USB-A, HDMI 2.1,
                                        3.5 mm headphone, power button
                                    Front: 2x USB-C, SDXC, status LED

Orientation: -Y = front, +Y = back, +Z = up, origin at the footprint centre on
the table surface. Units are centimetres (scene scale_length = 1.0).

EVERY dimension below except the three overall ones is MEASURED, in
millimetres, off Apple's own flat product photography, and converted to cm.
The measurement tools live in ../tools:

    measure_cc.py        connected-component pass over the rear port row
    measure_front.py     front openings, the status LED, the edge radii
    measure_ref.py       chassis box, gross bands, hole pitch

The conversion is: the chassis is 197 mm wide in every shot, so the pixel-to-mm
scale follows from the chassis bounding box, and anything measured as a
fraction of that box is in millimetres. Re-measure rather than trusting the
comments here — several of the numbers below replaced values that had been
"verified against Apple's diagram" and were still wrong.
"""

import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector

# Blender does NOT put the script's own directory on sys.path when it is run
# with `--python <file>`, so `from mac_studio_spec import ...` below failed
# with ModuleNotFoundError and the build never ran - which is why the .blend
# on disk and every render in renders/ were stale artefacts from an earlier
# revision. The paths are derived from __file__ precisely so the script can be
# launched from any working directory; the import has to follow the same rule.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ---------------------------------------------------------------- parameters
# Every measured dimension lives in mac_studio_spec.py and is imported, not
# restated. This file used to carry its own copy of the whole measured block,
# which is how a spec correction could land, pass its own self-test, and still
# not reach the model: the build looked complete and ran, with the old numbers.
# There is now exactly one source of truth, and tools/verify_spec.py measures
# that source against Apple's photographs.
from mac_studio_spec import (            # noqa: E402,F401  (F401: re-exported)
    W, D, H_TOTAL, FOOT_H, BODY_H, R_VERT, R_HORZ,
    FIELD_TOP_MM, FIELD_BOT_MM, UPPER_Z0, UPPER_Z1, UPPER_HALF_X, UPPER_DEPTH,
    UPPER_PITCH_X, UPPER_PITCH_Z, UPPER_STAGGER, UPPER_HOLE_R,
    GRILLE_BAND_Z0, GRILLE_BAND_Z1, GRILLE_PITCH_X, GRILLE_PITCH_Z,
    GRILLE_STAGGER, GRILLE_HOLE_RX, GRILLE_HOLE_RZ, GRILLE_RECESS,
    IO_Z, REAR_PORTS, AC_INLET_X, AC_INLET_W, AC_INLET_H,
    HEADPHONE_X, HEADPHONE_R, POWER_BTN_X, POWER_BTN_R, ICON_Z,
    POWER_BTN_GAP_W, POWER_BTN_GLYPH_R, POWER_BTN_GLYPH_W,
    POWER_BTN_GLYPH_A0, POWER_BTN_GLYPH_A1,
    ICON_TB_X, ICON_ETH_X, ICON_USB_X, ICON_HDMI_X, ICON_HP_X,
    FRONT_PORTS, LED_X, LED_R, FOOT_XY, FOOT_R,
    ARC_SEG,
    FAN_Z, FAN_X, FAN_R, FAN_SHROUD_W, FAN_SHROUD_D, FAN_SHROUD_H,
    SPINE_W, SPINE_Z0, SPINE_Z1, SPINE_D, SPINE_BREAK_Z0, SPINE_BREAK_Z1,
    SPINE_BREAK_HALF_X,
    HEATSINK_Z, PCB_Z, WALL, PIPE_Z, PSU_Z, SPEAKER_Z,
    io_row_check,
)
import mac_studio_spec as S              # noqa: E402  (the glyph tables)

# Output paths. These are derived from this file's own location rather than
# from the working directory, because Blender is routinely launched from
# elsewhere (`blender --background --python .../build_mac_studio.py`) and a
# relative path would then write the .blend and the renders somewhere nobody
# looks. _HERE is computed above, before the spec import, for sys.path.
OUT_DIR = os.path.join(_HERE, "..", "renders")
BLEND = os.path.join(_HERE, "mac_studio.blend")

problems = io_row_check()
if problems:
    raise SystemExit("measured spec is self-inconsistent:\n  " +
                     "\n  ".join(problems))
# ------------------------------------------------------------------ materials
def make_mat(name, base, metallic, rough, emit=None, emit_strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = rough
    if emit is not None:
        # Blender 4.x renamed the emission sockets.
        for key in ("Emission Color", "Emission"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = (*emit, 1.0)
                break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emit_strength
    m.diffuse_color = (*base, 1.0)
    return m


def build_materials():
    return {
        # Anodised silver aluminium. Apple's shell is a metal, and the giveaway
        # that a render is CG is a body that reads as white plastic: that means
        # the base colour is too bright for the environment and the roughness
        # too high for the form. Measured off the product shots, the panel sits
        # around 78-84% grey in the lit areas, so the reflectance here is set
        # well below white and the environment supplies the rest.
        "alu": make_mat("Aluminium_Silver", (0.560, 0.566, 0.578), 1.0, 0.205),
        # The recessed field floor and the base band read a shade darker than
        # the outer skin because they are in their own shadow.
        "grille": make_mat("Grille_DarkAlu", (0.115, 0.118, 0.122), 0.70, 0.44),
        "cavity": make_mat("Cavity_Black", (0.012, 0.012, 0.014), 0.0, 0.72),
        "port": make_mat("Port_Black", (0.055, 0.056, 0.060), 0.0, 0.40),
        "rubber": make_mat("Foot_Rubber", (0.035, 0.035, 0.038), 0.0, 0.86),
        "led": make_mat("Status_LED", (0.92, 0.94, 0.97), 0.0, 0.18,
                        emit=(0.92, 0.95, 1.00), emit_strength=2.4),
        # Engraved silkscreen: filled with a dark grey lacquer.
        "silk": make_mat("Silkscreen", (0.085, 0.086, 0.090), 0.0, 0.55),
        # Internals.
        "fan": make_mat("Fan_Plastic", (0.045, 0.045, 0.048), 0.0, 0.55),
        "pcb": make_mat("PCB_Green", (0.030, 0.085, 0.048), 0.0, 0.62),
        "alu_raw": make_mat("Aluminium_Raw", (0.400, 0.404, 0.412), 1.0, 0.42),
        "copper": make_mat("Heatpipe_Copper", (0.72, 0.45, 0.28), 1.0, 0.24),
        "chip": make_mat("Silicon", (0.020, 0.020, 0.024), 0.25, 0.22),
        "memory": make_mat("DRAM", (0.075, 0.076, 0.082), 0.0, 0.50),
        "insul": make_mat("Insulation", (0.130, 0.128, 0.120), 0.0, 0.78),
    }


# ------------------------------------------------------------------ geometry
def rounded_rect(hx, hy, r, seg=ARC_SEG, edge_sub=4):
    """CCW point ring of a rounded rectangle.

    Every straight edge is subdivided: without that a flat panel is one huge
    quad and auto-smoothed normals across it band visibly. The corner arc
    centres are inset by r — using the edge midpoint instead pushes the whole
    path outward by exactly r and inflates the bounding box.
    """
    r = max(0.02, min(r, hx - 0.02, hy - 0.02))
    corners = ((hx - r, hy - r, 0.00), (-hx + r, hy - r, 0.25),
               (-hx + r, -hy + r, 0.50), (hx - r, -hy + r, 0.75))
    arcs = []
    for cx, cy, start in corners:
        pts = []
        for i in range(seg + 1):
            a = (start + 0.25 * i / seg) * 2.0 * math.pi
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        arcs.append(pts)

    ring = []
    for i in range(4):
        ring.extend(arcs[i])
        p0 = arcs[i][-1]
        p1 = arcs[(i + 1) % 4][0]
        for s in range(1, edge_sub + 1):
            t = s / (edge_sub + 1.0)
            ring.append((p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t))
    return ring


def report_stage(body, stage):
    """Log the shell's envelope after each cut.

    Every build in this project's history has ended with the audit reporting
    X short by 1.5 mm and Z short by 3.5 mm, and every fix for it has been a
    guess at which boolean was responsible. This makes the question
    answerable in one run: if the envelope is right after build_body and
    wrong after the field, the field did it, and there is no need to
    speculate about the band.

    Not a gate. It prints; tools/audit_bbox.py is the gate.
    """
    mw = [body.matrix_world @ v.co for v in body.data.vertices]
    if not mw:
        print("  %-14s EMPTY (%d verts)" % (stage, 0))
        return
    print("  %-14s %7d verts  x %+7.3f..%+7.3f  y %+7.3f..%+7.3f  "
          "z %+6.3f..%+6.3f" % (
              stage, len(mw),
              min(v.x for v in mw), max(v.x for v in mw),
              min(v.y for v in mw), max(v.y for v in mw),
              min(v.z for v in mw), max(v.z for v in mw)))
    return mw


def boolean_diff(body, cutter, label="Cut"):
    """Apply an EXACT boolean difference and drop the cutter.

    BOTH MESHES MUST BE TRIANGLES, and the cutter is the one that matters
    here. The lofted shell's caps are large non-planar n-gons and EXACT
    mis-resolves their winding - skipping the shell's triangulation lets the
    boolean "succeed" and then merge the cutter's outer half into the shell,
    the bbox growing by the cutter's overhang instead of shrinking.

    The cutter is a list of n-gon prisms: two n-gon caps and n quads each.
    EXACT mis-resolves those caps the same way, and with 3,069 of them the
    errors are not a few bad faces - the shell came back at 43,620 vertices
    and 3.93 cm3, with 1,420 stray vertices sitting 0.5 mm PROUD of the
    original skin in the field's z range. The hole bores were being kept
    instead of removed, and the prisms' own side walls became the shell.

    A prism's caps are flat, so they triangulate cleanly. `tessface` with a
    low error keeps the ring's centre vertex dead centre; a fan is enough
    because a regular n-gon is convex.
    """
    triangulate_caps(body)
    triangulate_caps(cutter)
    bpy.context.view_layer.objects.active = body
    for o in bpy.context.selected_objects:
        o.select_set(False)
    body.select_set(True)
    mod = body.modifiers.new(label, "BOOLEAN")
    mod.operation, mod.object, mod.solver = "DIFFERENCE", cutter, "EXACT"
    bpy.ops.object.modifier_apply(modifier=label)
    bpy.data.objects.remove(cutter, do_unlink=True)
    return body


def cut_from_body(body, name, cx, cy, cz, sx, sy, sz, bevel=0.0, mats=None):
    """Boolean a rounded box out of the shell — a real recess, not a decal."""
    cutter = add_box("_cut_" + name, cx, cy, cz, sx, sy, sz,
                     (mats or {}).get("cavity") or bpy.data.materials["Cavity_Black"],
                     bevel=bevel)
    return boolean_diff(body, cutter, "Cut_" + name)


def paint_bore_black(obj, y_lo, y_hi, half_x, z_lo, z_hi, slot=1):
    """Paint the INSIDE of a perforation with the cavity material.

    The bore walls come out of the boolean wearing the SHELL's material
    index, so every hole is polished aluminium inside and out. Nothing in the
    geometry is wrong - the bores are real, they are the right size, and a ray
    passes straight through - but a hole whose walls are the same metal as the
    panel around it is invisible under a studio light. Measured: 35,828 bore
    faces at y = -98.0 mm, every one of them Aluminium_Silver, against 120,349
    faces of the outer skin at -98.5 mm also Aluminium_Silver. A 256-sample
    render with denoising off, at 1400 px, came back with a local luminance
    spread of 1.0 out of 255 across the whole field.

    A real Mac Studio's perforations are dark: the walls are anodised, and
    they are in shadow for most of their depth. That is what makes the field
    read as perforated at all.

    The bore is identified by position rather than by normal. Its faces sit
    in a thin shell part-way through the panel's thickness, between the outer
    skin and the inner wall, and nothing else in that band belongs to a hole.
    A normal test would catch the bore but also the skin, since a bore's wall
    and the panel's face are both nearly perpendicular to the view.

    Only the y band of the bore is touched, so the panel's own faces at the
    skin and at the inner wall keep the aluminium.
    """
    for p in obj.data.polygons:
        c = p.center
        if (y_lo < c.y < y_hi and abs(c.x) < half_x
                and z_lo < c.z < z_hi):
            p.material_index = slot
    return obj


def paint_recess_black(obj, y_lo, y_hi, x_extent, z_lo, z_hi, slot=1):
    """Force every face inside a recess to the cavity material.

    A boolean difference flips the cutter's faces to become the recess walls,
    but they keep the SHELL's material index. Select by volume, not by normal:
    a recess's back wall points into the recess, same as its side walls.
    """
    for p in obj.data.polygons:
        c = p.center
        if (y_lo < c.y < y_hi and abs(c.x) < x_extent
                and z_lo < c.z < z_hi):
            p.material_index = slot
    return obj


def triangulate_caps(obj):
    """Make the whole mesh triangles, once.

    Guard on polygon sizes, not on `data.loop_triangles` — that cache is lazily
    filled, so its length is unreliable before the first tessellation.
    """
    if not obj.data.polygons or all(len(p.vertices) == 3 for p in obj.data.polygons):
        return
    mod = obj.modifiers.new("Tri", "TRIANGULATE")
    mod.quad_method = mod.ngon_method = "BEAUTY"
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier="Tri")


def fillet_inset(z, z_lo, z_hi):
    """Horizontal fillet: 0 in the straight band, R_HORZ at the very edge."""
    if z <= z_lo + R_HORZ:
        t = (z_lo + R_HORZ) - z
        return R_HORZ - math.sqrt(max(0.0, R_HORZ ** 2 - t ** 2))
    if z >= z_hi - R_HORZ:
        t = z - (z_hi - R_HORZ)
        return R_HORZ - math.sqrt(max(0.0, R_HORZ ** 2 - t ** 2))
    return 0.0


# -------------------------------------------------------------- grille masks
def base_mask(px, py, half_x, half_y, z=None):
    """The base band wraps the perimeter, but NOT through the corners.

    It is visible on the front panel in Apple's front product shot, not just
    around the back. An earlier build keyed this on the rear panel and left
    the front's lower edge as bare metal.

    The corner arcs are excluded because the band's prisms there point
    diagonally out of the machine, and a 2.5 mm prism at 45 degrees shears
    the corner off rather than boring through it.

    There is no z test here. It used to be `z < FOOT_H + R_HORZ`, to keep the
    walk off the bottom fillet, and it silently became a no-op: build_grilles
    raises the walk to exactly that height, so nothing was ever excluded by it
    and the only thing keeping the band off the fillet was the walk's start
    z. The test belongs where the decision is made.
    """
    fx = abs(px) > (half_x - R_VERT)
    fy = abs(py) > (half_y - R_VERT)
    if fx and fy:
        return 0.0                      # on a corner arc
    return 1.0


def field_mask(px, py, half_x, half_y, z=None):
    """The upper field is a plain RECTANGLE on the REAR panel.

    Sign convention, which is the whole bug this function used to have: in
    this model +Y is the FRONT face (the front sockets are at y = +D/2) and
    -Y is the rear, where the ports and the exhaust grille are. So the rear
    panel is py < 0, and the test must reject py > 0.

    The previous version tested `py <= 0.0: return 0.0`, which kept only
    py > 0 - the front. The consequence was quiet and total: the perforated
    field was built across the FRONT panel and the rear was left bare. The
    object was still called "RearField" and the build log still printed a
    plausible hole count, and the front render came back with dark horizontal
    bands that Apple's front panel does not have.

    Keyed on geometry, not arc length. On a rounded square the rear panel and
    each side span the same range of the other axis, so a single-axis test
    lights up the side panels and leaves the back bare - which is what the
    earlier arc-length version did.
    """
    if py >= 0.0:
        return 0.0                      # front half: no field
    if abs(px) <= UPPER_HALF_X:
        return 1.0
    t = (abs(px) - UPPER_HALF_X) / max(1e-6, half_x - UPPER_HALF_X)
    if t >= 1.0:
        return 0.0
    return 1.0 - t * t * (3.0 - 2.0 * t)


def grille_inset(z, mask):
    """How far the skin is stepped back at height z, to carry a vent field.

    IT RETURNS ZERO, AND THAT IS THE POINT. A vented panel on this machine is
    a flat field of holes, not a punched plate set into a groove: Apple's
    product photographs show the perforations flush with the surrounding
    metal, and the machining that makes 4,000+ of them cannot leave a 0.75 mm
    step around the panel anyway.

    The step was here to give the prisms somewhere to start, and it cost the
    whole perforation field. The loft pulled the entire cross-section in by
    `recess` - front face and all - so the skin the holes had to break through
    was never the surface anyone sees:

        measured, z 42.2..90.3 mm   outermost metal  y = -98.50 mm
        measured, same z            hole floor      y = -97.83 mm

    The prisms started on the floor at -97.75 and cut inward, so they opened
    a cavity UNDER an intact skin. The area sweep read 16.5% and 42,914 of
    62,920 rays still hit Body. Widening the prism could not fix it: the
    material it needed to remove was not on the path.

    With no step, the walk sits on the real skin and the prism crosses the
    wall from outside, which is the only geometry that has ever produced a
    genuinely open hole here.
    """
    return 0.0


# ------------------------------------------------------------------ the body
def build_body(mats):
    """Lofted rounded box, then hollowed so the internals are visible.

    The perforations are genuine recesses in the loft rather than boolean cuts.
    A boolean fights back three separate ways here: a cutter tangent to the
    skin cuts nothing, one buried inside cuts nothing, and one proud of the skin
    leaves the difference behind as new geometry that inflates the bounding box
    by the overshoot (measured: +1.16 mm). None of those is visible from the
    vertex count alone.
    """
    z_lo, z_hi = FOOT_H, H_TOTAL
    levels = []
    steps = 8
    for i in range(steps + 1):                       # bottom fillet
        levels.append(z_lo + R_HORZ * (1.0 - math.cos(math.pi / 2 * i / steps)))
    for i in range(4):                               # base band
        levels.append(GRILLE_BAND_Z0 + (GRILLE_BAND_Z1 - GRILLE_BAND_Z0) * i / 3.0)
    for i in range(9):                               # upper field
        levels.append(UPPER_Z0 + (UPPER_Z1 - UPPER_Z0) * i / 8.0)
    for i in range(steps + 1):                       # top fillet
        levels.append(z_hi - R_HORZ * (1.0 - math.cos(math.pi / 2 * i / steps)))
    levels = sorted(set(round(v, 4) for v in levels))

    verts, faces, mats_per_face = [], [], []
    hx, hy = W / 2.0, D / 2.0

    for z in levels:
        base_d = fillet_inset(z, z_lo, z_hi)
        ux0, uy0 = hx - base_d, hy - base_d
        prof = rounded_rect(ux0, uy0, R_VERT - base_d)
        in_band = GRILLE_BAND_Z0 - 1e-6 <= z <= GRILLE_BAND_Z1 + 1e-6
        mask_fn = base_mask if in_band else field_mask
        for px, py in prof:
            m = mask_fn(px, py, ux0, uy0, z)
            d = base_d + grille_inset(z, m)
            # The recess moves the REAR surface INWARD ALONE. Scaling both
            # axes by (half - d) pulled the whole cross-section in with it, so
            # in the field's z range the chassis came out 1.5 mm narrower than
            # the spec on both sides: x +/-97.75 instead of +/-98.50, and the
            # audit has been reporting that as a boolean regression ever since.
            #
            # A vented panel is a step in the REAR face. The sides, front and
            # top are not vented and must stay at the full half-width, so x
            # takes only `base_d` and y takes the whole `d`.
            x = px / ux0 * (hx - base_d)
            y = py / uy0 * (hy - d)
            verts.append((x, y, z))

    n = len(rounded_rect(hx, hy, R_VERT))
    for li in range(len(levels) - 1):
        a, b = li * n, (li + 1) * n
        for i in range(n):
            j = (i + 1) % n
            faces.append((a + i, a + j, b + j, b + i))
            mats_per_face.append(0)

    faces.append(tuple(range(n - 1, -1, -1)))            # bottom cap
    mats_per_face.append(1)
    faces.append(tuple(range((len(levels) - 1) * n, len(levels) * n)))
    mats_per_face.append(0)

    me = bpy.data.meshes.new("Body")
    me.from_pydata(verts, [], faces)
    me.validate()
    for m in (mats["alu"], mats["cavity"]):
        me.materials.append(m)
    for poly, mi in zip(me.polygons, mats_per_face):
        poly.material_index = mi
    me.update()

    obj = bpy.data.objects.new("Body", me)
    bpy.context.collection.objects.link(obj)
    auto_smooth(obj, math.radians(38))
    return obj


def hollow_body(body, mats):
    """Turn the solid loft into a real shell with a 1.5 mm wall.

    Without this the body is a solid block and the internals are invisible
    except through the perforations — which is not what the machine is, and
    makes a cutaway view useless.

    The prisms that make the perforations cross this wall and stop inside the
    cavity, with a span chosen so neither cap lands on a face. See
    build_grilles() for the measurements; it is the reason the holes come out
    open at all, and hollowing before them is what lets the span work.
    """
    wall = 0.15
    # The cutter must sit INSIDE the skin, leaving `wall` of aluminium on
    # every face. It used to be sized (W - 2*wall) * 2 - 2*R_VERT, i.e. twice
    # the chassis width, so it passed straight through both side walls - and
    # through the front and back as well, since the same doubling applied on
    # Y. The result was a shell with no front and no rear skin: rays fired
    # from +Y landed on the AC inlet, the logic board and the heatsink, and
    # the front render came back showing the machine's insides.
    #
    # Note the units: W, D and H_TOTAL are in CENTIMETRES and the helper
    # takes centimetres, so the inset is a straight subtraction. The *2 was
    # never needed - the lofted profile is already W across.
    cut_x = W - 2 * wall
    cut_y = D - 2 * wall
    cut_z = (H_TOTAL - 0.18) - (FOOT_H + 0.22)
    inner = add_box("_cut_cavity", 0.0, 0.0, (FOOT_H + 0.22 + H_TOTAL - 0.18) / 2.0,
                    cut_x, cut_y, cut_z,
                    bpy.data.materials["Cavity_Black"],
                    bevel=max(R_VERT - wall, 0.01))
    if inner.dimensions.x > W or inner.dimensions.y > D:
        print("  WARNING: cavity cutter %.1f x %.1f mm exceeds the chassis"
              % (inner.dimensions.x * 10, inner.dimensions.y * 10))
    boolean_diff(body, inner, "Hollow")
    print("  hollowed: %d verts  (wall %.2f mm, cutter %.1f x %.1f mm)"
          % (len(body.data.vertices), wall * 10, cut_x * 10, cut_y * 10))

    # THE EXTERIOR MUST NOT WEAR THE CAVITY'S MATERIAL. A boolean difference
    # hands the cutter's faces to the result, and the cutter here is
    # Cavity_Black at base colour 0.012 - correct for the inside of a shell,
    # wrong for its outside. The underside came out with 98 faces wearing it,
    # so `06_bottom` rendered a matte black plate: no ventilation band, no
    # feet, no edge, and no amount of light would have changed it, since
    # 1,800 W and every ray path of the floor plane disabled still read black.
    #
    # The exterior is identified by position, because it is the simpler of
    # the two to name: a face is exterior if it is within `wall` of the
    # chassis's outer surface, and interior if it is deeper than that. The
    # underside needs the margin - the cavity cutter's bottom cap reaches
    # down to z = 0, so a strict test at FOOT_H leaves the base in the void.
    me = body.data
    fixed = 0
    for p in me.polygons:
        c = p.center
        exterior = (
            abs(c.x) > W / 2.0 - wall - 0.02
            or abs(c.y) > D / 2.0 - wall - 0.02
            or c.z > H_TOTAL - wall - 0.02
            or c.z < FOOT_H + 0.02
        )
        if exterior and p.material_index != 0:
            p.material_index = 0
            fixed += 1
    if fixed:
        me.update()
        print("  repainted %d exterior faces off Cavity_Black -> "
              "Aluminium_Silver" % fixed)
    return body


# --------------------------------------------------------- object primitives
def auto_smooth(obj, angle):
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    try:
        bpy.ops.object.shade_auto_smooth(angle=angle)          # 4.2+
    except Exception:
        try:
            bpy.ops.object.shade_smooth_by_angle(angle=angle)  # 4.1
        except Exception:
            bpy.ops.object.shade_smooth()


def simple_mesh(name, verts, faces, mat, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    me.materials.append(mat)
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    if smooth:
        auto_smooth(obj, math.radians(50))
    return obj


def add_box(name, cx, cy, cz, sx, sy, sz, mat, bevel=0.0, rot=None):
    """A box, positioned and optionally rotated about its OWN centre.

    `rot` must be passed to the primitive, not assigned afterwards. These
    helpers end with `transform_apply`, which bakes location/rotation/scale
    into the mesh and leaves the object's origin at the world origin - so a
    later `obj.rotation_euler = ...` spins the baked world-space mesh about
    (0,0,0) and throws the part clean off the machine. That is not a
    hypothetical: the fan blades and the heat pipes were both built this way,
    and the heat pipes ended up 63 mm below the table, taking the whole model's
    height to 158 mm.
    """
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx, cy, cz),
                                    rotation=rot or (0.0, 0.0, 0.0))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if bevel > 0.0:
        # A bevel wider than half the shortest side self-intersects, and EXACT
        # then silently fails to cut. Clamp it.
        bevel = min(bevel, 0.45 * min(abs(sx), abs(sy), abs(sz)))
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 3
        mod.limit_method = "ANGLE"
    obj.data.materials.append(mat)
    return obj


def add_cylinder(name, cx, cy, cz, r, h, mat, verts=48, axis="Z", smooth=True,
                 rot=None):
    """A cylinder, optionally rotated about its own centre. See add_box for
    why the rotation has to arrive here rather than being assigned after."""
    base = {"Z": (0, 0, 0), "Y": (math.pi / 2, 0, 0),
            "X": (0, math.pi / 2, 0)}[axis]
    use = rot if rot is not None else base
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts, radius=r, depth=h, location=(cx, cy, cz), rotation=use
    )
    obj = bpy.context.active_object
    obj.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    obj.data.materials.append(mat)
    if smooth:
        auto_smooth(obj, math.radians(40))
    return obj


def add_cylinder_between(name, a, b, r, mat, verts=20):
    """A cylinder spanning the two points, centred on its own midpoint.

    The rotation is given to the primitive so it is applied about the part's
    own centre; assigning `rotation_euler` after the fact would orbit the
    already-baked world-space mesh around the world origin instead.
    """
    a, b = Vector(a), Vector(b)
    d = b - a
    mid = (a + b) / 2.0
    rot = d.to_track_quat("Z", "Y").to_euler()
    return add_cylinder(name, mid.x, mid.y, mid.z, r, d.length, mat,
                        verts=verts, rot=rot)


def add_tube(name, cx, cy, cz, r_out, r_in, h, mat, verts=40, axis="Z"):
    """A hollow cylinder — the shape a fan shroud or a speaker cone wants."""
    verts_l, faces = [], []
    for rr in (r_out, r_in):
        for z in (-h / 2.0, h / 2.0):
            for k in range(verts):
                a = 2 * math.pi * k / verts
                verts_l.append((cx + rr * math.cos(a), cy + rr * math.sin(a), cz + z))
    bo, to, bi, ti = 0, verts, 2 * verts, 3 * verts
    for k in range(verts):
        k2 = (k + 1) % verts
        faces.append((bo + k, bo + k2, to + k2, to + k))        # outer wall
        faces.append((bi + k2, bi + k, ti + k, ti + k2))        # inner wall
        faces.append((bo + k2, bo + k, bi + k, bi + k2))        # bottom ring
        faces.append((to + k, to + k2, ti + k2, ti + k))        # top ring
    obj = simple_mesh(name, verts_l, faces, mat, smooth=True)
    if axis == "Y":
        obj.rotation_euler = (math.pi / 2, 0, 0)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


# ---- open fraction ------------------------------------------------------
# Measured by tools/ground_truth_open.py against the BUILT .blend, not
# against the spec's analytic surface. That distinction is the whole point:
# the surface the spec describes and the surface the loft produces are not
# always the same object, and a check that derives its rays from the spec
# agrees with the spec even when the panel is sealed.
#
# Current: 0 of 21,600 rays through the rear field reach the cavity. The
# perforation tubes are built (3,069 in the field, 3,128 in the base band)
# and carry the bore walls, but nothing subtracts them from the shell, so the
# metal is unbroken. Three boolean approaches were built and measured:
#
#   * four-ring tube as cutter     2.8% open, shell intact
#   * solid prism, WALL - recess   1.8% open, shell intact
#   * solid prism, WALL + recess   100% open, Body reduced to 0 vertices
#
# The first is not a cutter: a tube's section is an annulus, so the
# difference leaves the bore's core alone. The second leaves a ring of uncut
# outer skin 0.85 mm proud of the bore. The third opens the panel but the
# walk is on a rounded rectangle, so at the corners the prism juts sideways
# into the side panels and the top and takes the chassis with it.
#
# The open version needs the prism to follow the LOCAL surface normal and the
# LOCAL wall thickness, which means build_body has to hand its per-row wall
# depth to build_grille_field instead of that function taking a constant.

# ------------------------------------------------------- perforated fields
def build_grille_panel(mats, name, z_lo, z_hi, depth, pitch_x, pitch_z,
                       hole_r, stagger=0.0, span_from_floor=0.0, seg=10,
                       max_holes=40000):
    """A rectangular field of prisms on the FLAT REAR PANEL.

    A separate function from build_grille_field, which walks a rounded
    perimeter and is right for the base band and wrong here. See
    field_walk() for what the perimeter version did to this panel.

    The normal is -Y at every point, so there is no mask, no corner arc and
    no possibility of a prism pointing sideways out through the side walls.
    The prism runs `span_from_floor` .. `+depth` along +Y, which is into the
    machine from the rear face.
    """
    nring = seg
    ring = [(math.cos(2.0 * math.pi * k / nring),
             math.sin(2.0 * math.pi * k / nring)) for k in range(nring)]

    span = z_hi - z_lo
    rows = max(1, int(span / pitch_z) + 1)
    cols = max(1, int(2.0 * min(S.UPPER_HALF_X, W / 2.0 - R_VERT) / pitch_x))
    x0 = -(cols - 1) * pitch_x / 2.0
    y_face = -D / 2.0

    verts, faces = [], []
    placed = 0
    for row in range(rows):
        z0 = z_lo + span - row * pitch_z
        off = (stagger * pitch_x * 0.5) if (stagger and row % 2) else 0.0
        for col in range(cols):
            if placed >= max_holes:
                break
            px = x0 + col * pitch_x + off
            if abs(px) > (W / 2.0 - R_VERT):
                continue
            base = len(verts)
            for od in (span_from_floor, span_from_floor + depth):
                for ox, oy in ring:
                    verts.append((px + ox * hole_r, y_face + od, z0 + oy * hole_r))
            for k in range(nring):
                k2 = (k + 1) % nring
                faces.append((base + k, base + k2,
                              base + nring + k2, base + nring + k))
            faces.append(tuple(base + k for k in range(nring)))
            faces.append(tuple(base + nring + k for k in range(nring - 1, -1, -1)))
            placed += 1

    print("  %s: %d holes, %d rows x %d cols, pitch %.3f cm, hole %.3f cm"
          % (name, placed, rows, cols, pitch_x, 2.0 * hole_r))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    # cut_in_batches reads the hole count and the per-hole face count off the
    # object, so they have to be carried on it. nring + 2 for a solid prism.
    obj["hole_faces"] = nring + 2
    obj["holes"] = placed
    return obj, placed


def build_grille_field(mats, name, z_lo, z_hi, recess, depth, pitch, hole_r,
                       mask_fn, seg=8, row_pitch=None, stagger=0.0,
                       max_holes=40000, hole_rz=None, span_from_floor=0.0):
    """Punch a lattice of round hole tubes into a recessed field.

    `recess` and `depth` are separate and are not interchangeable:
      * `recess` - how far grille_inset() stepped the SKIN back, i.e. where
        the mouth of the hole sits. It places the walk.
      * `depth`  - how much metal is LEFT under that skin, i.e. how long the
        tube has to be to reach the cavity. It crosses the wall.

    A tube that stops short leaves a lip of skin in front of every hole, and
    one that overshoots pokes past the shell and inflates the bounding box.
    Passing the recess as the depth is the subtle one: the two numbers are
    both small, so it produces a correct-looking tube in the wrong place
    rather than an error, and only a swept ray-cast notices.

    The path is the profile at the GROOVE FLOOR, taken from the body's own
    rounded_rect so the two cannot drift.

    Holes are walked by ARC LENGTH and INTERPOLATED along each segment. The
    walk has to interpolate, because rounded_rect leaves each flat face as a
    handful of long segments: snapping to the nearest vertex instead put the
    whole 0.186 cm pitch onto ~4 positions per row, 3.35 cm apart.

    Column pitch and row pitch are separate, and the stagger is a FRACTION of
    the column pitch rather than a half-pitch offset. The measured lattices are
    neither square nor half-staggered: the rear field's rows sit 16% further
    apart than its columns and each alternate row is offset by a fifth of the
    pitch, while the base band is a plain square grid. A single `pitch` used
    for both axes, with a hard-coded half-pitch offset, drifts visibly across a
    171 mm field even though it looks right over the first few centimetres.
    """
    row_pitch = pitch if row_pitch is None else row_pitch
    if hole_rz is None or abs(hole_rz - hole_r) < 1e-9:
        ring = [(math.cos(2 * math.pi * k / seg), math.sin(2 * math.pi * k / seg))
                for k in range(seg)]
    else:
        # obround: a rounded rectangle whose corner radius is the half-height,
        # so the long sides come out flat and the ends semicircular - which is
        # what the photograph shows, and an ellipse only approximates it
        ring = rounded_rect(max(hole_r - hole_rz, 1e-4), hole_rz, hole_rz,
                            seg=max(3, seg // 2), edge_sub=1)
    nring = len(ring)

    # The walk has to sit on the RECESSED skin, and the tube has to be as long
    # as the metal LEFT under it. Those are two different numbers, so they are
    # two parameters: `recess` places the mouth, `depth` crosses the metal.
    # For a while one argument did both jobs, and because the two happen to be
    # small and similar it built a plausible-looking tube in the wrong place
    # rather than failing.
    # The walk sits on the REAL skin. It used to be pulled in by `recess` to
    # match a groove that grille_inset() used to cut into the loft; that groove
    # is gone, and following it is what put every prism 0.75 mm inboard of the
    # surface, so no hole ever broke through. `recess` is kept in the
    # signature because the spec still names it and callers pass it - it is
    # now documentation of the hole's depth, not a displacement.
    hx, hy = W / 2.0, D / 2.0
    perim = rounded_rect(hx, hy, R_VERT, seg=24, edge_sub=160)
    acc = [0.0]
    for i in range(1, len(perim)):
        ax, ay = perim[i - 1]
        bx, by = perim[i]
        acc.append(acc[-1] + math.hypot(bx - ax, by - ay))
    # Close the walk, so the final stretch of the perimeter has a real length
    # in acc. Without this the last segment is unaddressable and point_at()
    # cannot interpolate through it.
    acc.append(acc[-1] + math.hypot(perim[0][0] - perim[-1][0],
                                    perim[0][1] - perim[-1][1]))
    total = acc[-1]

    def point_at(s):
        """The point at arc length s along the closed walk, interpolated.

        Interpolating is the whole fix. This used to return perim[lo] - the
        nearest VERTEX - so every hole snapped to one of the walk's corners
        instead of landing where the pitch said it should. rounded_rect
        subdivides the corner arcs finely but leaves each flat face as a
        handful of long segments, so the field's 0.186 cm pitch resolved to
        only ~4 holes per row, 3.35 cm apart, and a 0.02 cm ground-truth
        sweep measured 1.1% open against a 54.2% design.

        That is also why the hole COUNT looked plausible (3,069) while the
        face was sealed: the walk did emit them, the mask rejected the ones
        that landed on the front and the sides, and what survived was a
        sparse scatter of real holes on an otherwise solid panel. The count
        was never evidence that the lattice was laid out - only the swept
        open fraction is, which is why it is measured that way here.
        """
        if s <= 0.0:
            px, py = perim[0]
            nx_, ny_ = perim[1]
            dx, dy = nx_ - px, ny_ - py
            ln = math.hypot(dx, dy) or 1.0
            return px, py, dx / ln, dy / ln
        if s >= acc[-1]:
            ax_, ay_ = perim[-1]
            bx_, by_ = perim[0]
            dx, dy = bx_ - ax_, by_ - ay_
            ln = math.hypot(dx, dy) or 1.0
            return ax_, ay_, dx / ln, dy / ln
        # hi is bounded by the perim, not by acc: acc carries one extra entry
        # for the closing segment, so len(acc) - 2 can be len(perim), and
        # perim[lo + 1] then walks off the end.
        lo, hi = 0, len(perim) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if acc[mid] < s:
                lo = mid + 1
            else:
                hi = mid
        px, py = perim[lo]
        nxt = (lo + 1) % len(perim)
        nx_, ny_ = perim[nxt]
        dx, dy = nx_ - px, ny_ - py
        # The tangent stays the SEGMENT's direction. Recomputing it from the
        # interpolated point to the next vertex would shorten it by (1 - f) and
        # bend the normal, which tilts the hole mouths on the flat faces.
        ln = math.hypot(dx, dy) or 1.0
        seg = (acc[lo + 1] - acc[lo]) if lo + 1 < len(acc) else 0.0
        f = 0.0 if seg <= 0.0 else min(1.0, max(0.0, (s - acc[lo]) / seg))
        return px + dx * f, py + dy * f, dx / ln, dy / ln

    span = z_hi - z_lo
    rows = max(1, int(span / row_pitch) + 2)
    row_dz = row_pitch

    verts, faces = [], []
    placed = 0
    for row in range(rows):
        z0 = z_lo + span - row * row_dz
        s = (stagger * pitch) if (stagger and row % 2) else 0.0
        while s < total:
            px, py, tx, ty = point_at(s)
            # z is passed so base_mask can exclude the bottom fillet, where the
            # walk's horizontal normal is the wrong direction for a prism.
            # Both masks accept it; only base_mask uses it.
            if mask_fn(px, py, hx, hy, z0) < 0.5:
                s += pitch
                continue
            if placed >= max_holes:
                break
            rx, ry = -ty, tx                       # outward normal
            base = len(verts)
            # A hole is a SOLID PRISM along the NORMAL: nring side faces and
            # two caps, no inner wall.
            #
            # It is a prism, not a tube, because it is a CUTTER. Subtracting a
            # tube leaves its bore's core untouched - a tube's section is an
            # annulus, so the difference mills a square channel and leaves the
            # metal in the middle standing. Measured 2.8% open. A prism fills
            # the cross-section, so the difference removes the skin.
            #
            # `span_from_floor` is where the prism STARTS, measured along the
            # walk's normal (rx, ry), and `depth` is how far it runs. On this
            # walk the normal points inward, so a positive od crosses the wall.
            #
            # Starting on the walk is the point: build_grille_field has already
            # placed the walk on the recessed skin, and starting anywhere
            # outside it puts the prism's cap proud of the aluminium, where
            # EXACT keeps it. Measured - a 5,312-vertex lid at y = -100.2 mm
            # over a skin at -98.5 mm, and the open fraction read 38.2% of a
            # panel that was still shut.
            rz = hole_r if hole_rz is None else hole_rz
            for od in (span_from_floor, span_from_floor + depth):
                for ox, oy in ring:
                    verts.append((px + tx * (ox * hole_r) + rx * od,
                                  py + ty * (ox * hole_r) + ry * od,
                                  z0 + oy * rz))
            for k in range(nring):
                k2 = (k + 1) % nring
                faces.append((base + k, base + k2,
                              base + nring + k2, base + nring + k))
            # the two caps, as n-gons. Winding matters: EXACT resolves the
            # difference from the cutter's facing, and a prism whose caps face
            # the wrong way is treated as the complement.
            faces.append(tuple(base + k for k in range(nring)))
            faces.append(tuple(base + nring + k for k in range(nring - 1, -1, -1)))
            placed += 1
            s += pitch

    obj = simple_mesh(name, verts, faces, mats["grille"], smooth=False)
    # A hole is nring side faces plus two caps. cut_in_batches() reads this
    # off the object rather than inferring it: "whichever even number divides
    # the face count" picks 16 for the band, which slices every batch
    # mid-hole.
    obj["holes"] = placed
    obj["nring"] = nring
    obj["hole_faces"] = nring + 2
    print("  %s: %d holes, %d rows, pitch %.3f cm, hole %.3f x %.3f cm"
          % (name, placed, rows, pitch, hole_r,
             hole_r if hole_rz is None else hole_rz))
    return obj


def build_grilles(mats, body=None, span=0.0):
    """The two ventilation features: the wrap-around base band and the single
    large rear field.

    THIS RUNS AFTER hollow_body(), ON A REAL SHELL, and `span` is how far
    each prism reaches from the skin before it stops. The span has to cross
    the wall AND keep going, and both ends of that were arrived at by
    measurement rather than by reasoning.

    A prism that ends ON the wall has its far cap in the cavity wall's plane,
    and EXACT reads a cap that finishes on a face as a pocket rather than a
    hole: 0.8% open, 62,408 of 62,920 rays still hitting metal, around a
    319,484-vertex shell that was otherwise exact. The panel looked perfect
    and was solid.

    0.2 mm past the wall opens it, and the overshoot reaches the top cap -
    the field's top row sits 1.2 mm below it - so z came back 5.98..90.0 mm
    instead of 0..95.0. Bracketing the wall, 0.1 mm either side, gave 25.4%
    open and z 5.98..74.3: the top two rows went with the cap.

    Cutting into the SOLID loft first, before hollowing, was the other
    direction and it fails differently: no cap has a face to land on, but
    hollowing then removes the cavity through the bores and the holes close
    again. 0.0% on a panel rays had been passing straight through.

    So the span is the wall plus most of a centimetre of empty cavity. The cap
    is unambiguously inside the air, and the prism never reaches far enough to
    touch the heatsink, the fan shrouds or the logic board on the far side.

    Winding turned out not to matter - both cap orders behave identically,
    which is worth knowing because "the whole shell replaced by a fragment"
    is what sent this down a winding hunt first.
    """
    if body is None:
        raise RuntimeError(
            "build_grilles needs the Body to cut against. The prisms alone are "
            "geometry sitting in the metal: a ray down the middle of a hole "
            "hits Body at the same distance as one through the bridge beside "
            "it, so a build that prints a hole count proves nothing about "
            "whether the panel is open. See tools/ground_truth_open.py.")
    if span <= 0.0:
        raise RuntimeError("build_grilles needs a positive span; got %r" % span)

    # PRISM START - UNVERIFIED HYPOTHESIS, and the comment is deliberately not
    # written as a conclusion. The previous build left the rear field 100%
    # blocked: at every one of 41 hole centres on the middle row there is still
    # a face of the outer skin within 0.35 mm, and a 1.42 mm hole cannot
    # contain a whole triangle, so those holes are not open. The 327,754 bore
    # faces at y = -98.0 mm are real but sit 0.5 mm behind an intact skin.
    #
    # The obvious suspect was the cutter's front cap sitting exactly in the
    # plane of the outer face, y = -98.5 mm, since a boolean with a
    # coplanar cap is a degenerate case. Testing it on a 4 x 4 cm slab with a
    # 0.15 cm wall: 0.0 and -0.02 both cut cleanly, giving exactly 2 boundary
    # loops and 15.985 of 16.000 cm2 of surviving skin. Both readings are what
    # one good hole looks like by area - a single 1.42 mm hole is 0.09% of the
    # face - so the control did NOT reproduce the failure, and the coplanarity
    # is not established as the cause.
    #
    # It stays as -0.02 because starting a cutter outside the target is the
    # correct thing to do regardless, and it costs nothing. Whether it fixes
    # the field is not yet known and must not be assumed: the next build has
    # to be checked with tools/skin_loops.py before anyone repeats any of the
    # numbers that were reported as passes.
    start = -0.02
    # THE BAND'S ROWS RUN ALONG THE VERTICAL WALL, ABOVE THE BOTTOM FILLET.
    #
    # The walk is a horizontal rounded rectangle at a fixed z, so it can only
    # place holes on a wall that is vertical at that height. The band in the
    # spec spans z 0.0 to 7.44 mm - which is where the band is on the real
    # part, wrapping under the machine and up - but the bottom R_HORZ fillet
    # is 3.8 mm deep, so everything below z 5.8 mm is the surface curving
    # away underneath. There the walk's normal is horizontal and the metal is
    # not, and a prism along a normal that leaves the shell is a cutter that
    # cuts whatever is next.
    #
    # Measured, with the walk starting at the spec's z 0.55 mm: Body came
    # back with 98,555 verts spanning z 5.98..89.98 mm, against 3,100
    # spanning the full 0..95.0 before the cut. The bottom cap, the top cap
    # and every side wall between them were gone. What survived was the two
    # panels carrying the grilles - both 100% open, which is the only reason
    # the build still looked like a perforated machine.
    #
    # So the rows start where the fillet ends and the row COUNT is preserved,
    # which puts the band's top edge above the spec's 7.44 mm. That is a real
    # disagreement with the photograph, and the honest reading is that the
    # band's lower rows sit on the fillet, following it round, rather than on
    # a vertical wall - and a horizontal walk cannot express that at all. It
    # is the one part of the ventilation that is not modelled honestly yet.
    band_z0 = FOOT_H + R_HORZ
    band_z1 = band_z0 + 8 * GRILLE_PITCH_Z
    print("  band  rows z %.3f..%.3f cm (fillet ends at %.3f; the spec puts "
          "the band at 0..%.3f)"
          % (band_z0, band_z1, band_z0, GRILLE_BAND_Z1))
    band = build_grille_field(
        mats, "BaseGrille",
        band_z0, band_z1,
        GRILLE_RECESS, span, GRILLE_PITCH_X, GRILLE_HOLE_RX,
        mask_fn=base_mask, seg=8, row_pitch=GRILLE_PITCH_Z,
        stagger=GRILLE_STAGGER, hole_rz=GRILLE_HOLE_RZ,
        span_from_floor=start)

    # The REAR FIELD is a rectangle on a flat panel, so it gets its own
    # builder rather than the perimeter walk. The perimeter's rear half
    # includes both side walls - field_mask()'s `py < 0` cannot tell a side
    # from a back - so the prisms were fired sideways into the sides and the
    # rear face was left solid at every x. build_grille_panel's normal is
    # -Y everywhere, so this cannot happen.
    field, n_field = build_grille_panel(
        mats, "RearField",
        UPPER_Z0 + 0.10, UPPER_Z1 - 0.10,
        span, UPPER_PITCH_X, UPPER_PITCH_Z, UPPER_HOLE_R,
        stagger=UPPER_STAGGER, span_from_floor=start, seg=10)

    # THE CUT. Everything above places 6,197 prisms; none of it opens
    # anything. A prism that is not subtracted from the shell is a lump of
    # geometry buried in metal, and a ray through the middle of a hole meets
    # Body at exactly the distance it would through the bridge beside it.
    #
    # The prism is the drill; the bore's walls are what the boolean leaves
    # behind, so the lattice object is deleted rather than kept to sit
    # inside its own cut.
    #
    # CUT IN BATCHES. Handing EXACT one 122,760-face cutter made it fail
    # open, and it did not fail loudly: the shell came back as a fragment of
    # the rear wall with the whole chassis gone, and the bbox audit reported
    # that as a 3.5 mm shortfall in Z rather than as the catastrophe it was.
    # Chunks keep every intersection local.
    print("  cutting the base band out of the shell ...")
    cut_in_batches(body, band, "BaseGrille")
    report_stage(body, "after_band")
    print("  cutting the rear field out of the shell ...")
    cut_in_batches(body, field, "RearField")
    report_stage(body, "after_field")

    # THE BORES GO DARK. The boolean hands the hole walls the shell's own
    # material, so a perforation whose walls are polished aluminium is
    # invisible - measured 1.0/255 of local contrast across the whole field at
    # 256 samples with denoising off. The bore is a thin shell part-way
    # through the 1.5 mm panel, and the band below is where it measures.
    mid = WALL * 0.5
    paint_bore_black(body, -D / 2.0 + mid - 0.06, -D / 2.0 + mid + 0.06,
                     UPPER_HALF_X + 0.15,
                     UPPER_Z0 + 0.05, UPPER_Z1 - 0.05)
    painted = sum(1 for p in body.data.polygons
                  if p.material_index == 1
                  and -D / 2.0 < p.center.y < -D / 2.0 + WALL + 0.02
                  and UPPER_Z0 < p.center.z < UPPER_Z1
                  and abs(p.center.x) < UPPER_HALF_X)
    print("  rear field: %d bore faces painted dark" % painted)
    report_stage(body, "painted")
    return band, field


def cut_in_batches(body, lattice, label, batch=400):
    """Subtract `lattice` from `body`, then delete it.

    The face stride and the hole count come off the object itself
    (`hole_faces`, `holes`). They are not guessable: a hole is `nring + 2`
    faces for a solid prism, and nring differs per field and is not what
    `seg` implies - the band builds an obround ring, so one hole is 26 faces,
    not the 34 seg=8 suggests. Guessing it as "whatever even number divides
    the face count" picked 16 and sliced every batch mid-hole.
    """
    stride = int(lattice.get("hole_faces", 0))
    placed = int(lattice.get("holes", 0))
    if stride < 5 or placed < 1:
        raise RuntimeError(
            "cut_in_batches: %s carries no lattice shape (hole_faces=%r "
            "holes=%r) - it has to come from build_grille_field"
            % (label, stride, placed))
    nbatch = (placed + batch - 1) // batch
    print("    %s: %d holes x %d faces, %d batches"
          % (label, placed, stride, nbatch))
    for k in range(nbatch):
        lo, hi = k * batch, min(placed, (k + 1) * batch)
        boolean_diff(body, slice_mesh(lattice, lo * stride, hi * stride,
                                       "_cut_" + label),
                     "Cut_%s_%d" % (label, k))
    bpy.data.objects.remove(lattice, do_unlink=True)
    print("    %s: done" % label)
    return body


def slice_mesh(obj, first, last, name):
    """A standalone mesh object holding obj's polys [first, last)."""
    me = bpy.data.meshes.new(name)
    remap = {}
    new_verts = []
    polys = []
    for p in obj.data.polygons[first:last]:
        ring = []
        for vi in p.vertices:
            if vi not in remap:
                remap[vi] = len(new_verts)
                new_verts.append(obj.data.vertices[vi].co.copy())
            ring.append(remap[vi])
        polys.append(tuple(ring))
    me.from_pydata([tuple(v) for v in new_verts], [], polys)
    # Guard the material copy. This used to index [0] unconditionally, which
    # is fine for the base band - it carries the aluminium slot - and an
    # IndexError for a cutter that carries none, which is what a freshly built
    # rectangular field is. The cutter is deleted on the next line anyway, so
    # what it looks like never matters; only that it has faces to intersect.
    for mat in obj.data.materials:
        me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    ob.matrix_world = obj.matrix_world.copy()
    bpy.context.scene.collection.objects.link(ob)
    return ob


# ------------------------------------------------------------------- sockets
def add_socket(name, x, z, w, h, y_mouth, mats, depth=0.30, wall=0.05, inward=1.0):
    """A rectangular connector socket: bright metal walls, dark back, tongue.

    Built wall-by-wall rather than as one dark box — that is what makes a
    connector read as a socket instead of a painted-on cutout.

    `inward` is +1 when the body extends toward +Y and -1 when it extends
    toward -Y. Getting this backwards builds the socket outside the enclosure
    and inflates the bounding box.
    """
    shell, cav = mats["alu"], mats["cavity"]
    yc = y_mouth + inward * depth / 2.0
    add_box(name + "_wt", x, yc, z + h / 2 - wall / 2, w, depth, wall, shell)
    add_box(name + "_wb", x, yc, z - h / 2 + wall / 2, w, depth, wall, shell)
    add_box(name + "_wl", x - w / 2 + wall / 2, yc, z, wall, depth, h - 2 * wall, shell)
    add_box(name + "_wr", x + w / 2 - wall / 2, yc, z, wall, depth, h - 2 * wall, shell)
    add_box(name + "_bk", x, y_mouth + inward * (depth - 0.03), z, w, 0.05, h, cav)
    add_box(name + "_tg", x, y_mouth + inward * depth * 0.55, z, w * 0.58, 0.09,
            h * 0.34, shell, bevel=0.02)


def add_round_socket(name, x, z, r, y_mouth, mats, depth=0.30, inward=1.0):
    shell, cav = mats["alu"], mats["cavity"]
    yc = y_mouth + inward * depth / 2.0
    add_cylinder(name + "_sh", x, yc, z, r, depth, shell, verts=40, axis="Y")
    add_cylinder(name + "_bk", x, y_mouth + inward * (depth - 0.04), z, r * 0.88,
                 0.05, cav, verts=40, axis="Y")
    add_cylinder(name + "_pn", x, y_mouth + inward * depth * 0.62, z, r * 0.16,
                 0.14, shell, verts=16, axis="Y")


def cloverleaf_outline(lobes=3, lobe_r=0.42, offset=0.52, samples=180):
    """Radial outline of the IEC C8 "cloverleaf" AC inlet.

    Union of one central disc and `lobes` discs on a ring. Sampled as a radius
    per angle, which is exact here because the shape is star-shaped about its
    centre. An earlier build cut a 1.05 x 0.60 cm rectangle instead, on a part
    that measures 22.0 x 16.4 mm.
    """
    pts = []
    for i in range(samples):
        a = 2 * math.pi * i / samples
        ux, uy = math.cos(a), math.sin(a)
        best = lobe_r
        for k in range(lobes):
            ka = 2 * math.pi * k / lobes + math.pi / 2.0
            cx, cy = offset * math.cos(ka), offset * math.sin(ka)
            d = cx * ux + cy * uy
            disc = lobe_r ** 2 - (offset ** 2 - d * d)
            if disc > 0.0:
                best = max(best, d + math.sqrt(disc))
        pts.append((best * ux, best * uy))
    return pts


def add_ac_inlet(name, x, z, w, h, y_face, body, mats, depth=0.42, inward=1.0):
    """Cut and build the three-lobed mains inlet.

    `inward` is the direction the socket body runs away from the face, in
    the model's +Y/-Y sense. Every depth below is written as `y_face +
    inward * d` rather than `y_face - d`: hardcoding the sign put the whole
    inlet 4.5 mm OUTSIDE the rear panel once y_face became negative, and
    the pins stuck out to y = -103 mm against a -98.5 mm skin.
    """
    def y_at(d):
        return y_face + inward * d

    outline = cloverleaf_outline(
        lobe_r=h * 0.30, offset=w * 0.30)
    n = len(outline)
    verts, faces = [], []
    for y in (y_at(-0.10), y_at(depth)):
        for ox, oz in outline:
            verts.append((x + ox, y, z + oz))
    for k in range(n):
        k2 = (k + 1) % n
        faces.append((k, k2, n + k2, n + k))       # side wall
    faces.append(tuple(range(n - 1, -1, -1)))     # outer cap (discarded)
    faces.append(tuple(range(n, 2 * n)))          # inner cap -> inlet floor
    cutter = simple_mesh("_cut_" + name, verts, faces, mats["cavity"])
    boolean_diff(body, cutter, "Cut_" + name)

    # The inlet body: a dark shroud set back inside the opening, with three
    # bright pins in a triangle and a dark centre earth pin.
    yc = y_at(depth * 0.55)
    add_cylinder(name + "_shroud", x, yc, z, w * 0.30, depth * 0.7,
                 mats["cavity"], verts=40, axis="Y")
    for k in range(3):
        a = 2 * math.pi * k / 3.0 + math.pi / 2.0
        px = x + offset_of(w) * math.cos(a)
        pz = z + offset_of(w) * math.sin(a)
        add_cylinder(name + "_pin%d" % k, px, y_at(depth * 0.72), pz, 0.105,
                     0.30, mats["alu"], verts=20, axis="Y")
    add_cylinder(name + "_earth", x, y_at(depth * 0.80), z, 0.115, 0.24,
                 mats["alu"], verts=20, axis="Y")


def offset_of(w):
    return w * 0.30


# ---------------------------------------------------------------- rear panel
def build_rear_io(mats, body):
    """Rear connectors, cut into the panel at the measured positions.

    The rear panel is at +Y. A rear view puts model +X on the image's LEFT, so
    the measured image-x maps through x = W/2 - x_img; REAR_PORTS is already in
    model space.

    The connectors sit FLUSH in the panel — there is no milled bay. The real
    rear is one flat aluminium face with the connectors let into it and a row of
    engraved icons above. The previous build cut a 15.2 x 1.9 cm pocket across
    the middle of the panel, which does not exist on this machine.
    """
    # The rear panel is at y = -D/2. This used to read D/2, which built the
    # entire I/O row - AC inlet, six Thunderbolt, HDMI, Ethernet, two USB-A,
    # the headphone jack, the power button and the engraved icons - on the
    # FRONT face, above the two USB-C and the SDXC slot. The machine then had
    # two port rows and no rear at all.
    #
    # Sign convention, stated once because getting it backwards has now cost
    # two separate bugs: +Y is the FRONT (USB-C, SDXC, status LED) and -Y is
    # the REAR (the I/O row and the exhaust field).
    y_face = -D / 2.0
    # the socket mouth sits just inside the skin
    y_mouth = y_face + 0.10

    for name, x, w, h in REAR_PORTS:
        cut_from_body(body, "Rear_" + name, x, y_face + 0.20, IO_Z,
                      w + 0.20, 0.60, h + 0.20, bevel=0.05, mats=mats)
        paint_recess_black(body, y_face - 0.58, y_face + 0.02,
                           abs(x) + w / 2.0 + 0.12, IO_Z - h / 2.0 - 0.12,
                           IO_Z + h / 2.0 + 0.12)
        # `inward` is the direction the socket body runs, in model +Y/-Y.
        # The rear face is at -Y, so inward is +1.
        add_socket("Port_" + name, x, IO_Z, w, h, y_mouth, mats,
                   depth=0.34, wall=0.045, inward=+1.0)

    # The rear sockets pass inward=+1, meaning their bodies run toward +Y
    # (inward, away from the -Y skin), so the inlet's depths go +Y too.
    add_ac_inlet("Port_ACInlet", AC_INLET_X, IO_Z, AC_INLET_W, AC_INLET_H,
                 y_face, body, mats, inward=+1.0)

    # 3.5 mm headphone jack.
    add_cylinder("_cut_headphone", HEADPHONE_X, y_face + 0.20, IO_Z,
                 HEADPHONE_R + 0.10, 0.60, mats["cavity"], verts=40, axis="Y")
    boolean_diff(body, bpy.data.objects["_cut_headphone"], "Cut_Headphone")
    add_round_socket("Port_Headphone", HEADPHONE_X, IO_Z, HEADPHONE_R, y_mouth,
                     mats, depth=0.34, inward=+1.0)

    build_power_button(mats, body, y_face, inward=+1.0)
    build_rear_icons(mats, y_face)
    return body


def build_power_button(mats, body, y_face, inward=1.0):
    """The power button: a shallow debossed circle carrying the power glyph.

    This is a power button, NOT a Touch ID sensor. Apple's own specs page for
    this machine lists no biometrics hardware, the mark engraved on the panel
    is the IEC power symbol, and the X-ray cutaway shows no fingerprint
    sensor. Naming it Touch ID imported a feature the product does not have.

    Measured outer diameter 8.6 mm (the connected-component pass reports the
    3.9 mm power glyph, which is a different feature entirely).

    `inward` is the direction into the case. The deboss, the ring and the
    glyph are all placed with `y_face + inward * d`; writing them as
    `y_face - d` left the button's ring 1.3 mm outside the rear skin and put
    the model's depth at 199 mm.
    """
    def y_at(d):
        return y_face + inward * d

    # Deboss: a shallow dish, so the button catches a different highlight than
    # the surrounding panel — which is the only thing that makes it read.
    cut_from_body(body, "PowerButton", POWER_BTN_X, y_at(0.05), IO_Z,
                  POWER_BTN_R * 2, 0.30, POWER_BTN_R * 2, bevel=0.02, mats=mats)
    add_cylinder("PowerButton_ring", POWER_BTN_X, y_at(0.115), IO_Z,
                 POWER_BTN_R - POWER_BTN_GAP_W / 2.0, POWER_BTN_GAP_W, mats["alu"],
                 verts=64, axis="Y")
    # The glyph: an open arc plus the vertical stroke. The arc's radius and the
    # gap's width used to be written here as 0.52 * POWER_BTN_R and 0.05, i.e.
    # restated constants that nothing compared against anything.
    # tools/touchid_probe.py measured the photograph instead: the dark is an
    # annulus at 1.50..2.25 mm and the gap is 0.30 mm. The offline renderer was
    # meanwhile drawing a FILLED disc of radius 0.52 R and a 0.6 mm ring, so the
    # two files disagreed about the same button and the disagreement showed up
    # as a port-row dark-share error. Both now read the spec.
    add_arc_decal("PowerButton_glyph_arc", POWER_BTN_X, IO_Z, POWER_BTN_GLYPH_R,
                  POWER_BTN_GLYPH_R - POWER_BTN_GLYPH_W / 2.0,
                  POWER_BTN_GLYPH_A0, POWER_BTN_GLYPH_A1,
                  y_at(-0.005), mats["silk"], thickness=POWER_BTN_GLYPH_W)
    add_box("PowerButton_glyph_bar", POWER_BTN_X, y_at(-0.005),
            IO_Z + POWER_BTN_R * 0.30,
            POWER_BTN_GLYPH_W, 0.02, POWER_BTN_R * 0.46, mats["silk"])


def add_arc_decal(name, x, z, r, width, a0, a1, y, mat, thickness=0.05,
                  samples=48):
    """A flat annular sector lying on a panel — glyph strokes."""
    verts, faces = [], []
    for i in range(samples + 1):
        a = math.radians(a0 + (a1 - a0) * i / samples)
        c, s = math.cos(a), math.sin(a)
        verts.append((x + (r - width / 2) * c, y, z + (r - width / 2) * s))
        verts.append((x + (r + width / 2) * c, y, z + (r + width / 2) * s))
    for i in range(samples):
        b = i * 2
        faces.append((b, b + 1, b + 3, b + 2))
    return simple_mesh(name, verts, faces, mat)


def add_polygon_decal(name, x, z, pts, y, mat, scale=1.0):
    """A flat polygon lying on a panel, from 2-D points in the XZ plane."""
    verts = [(x + px * scale, y, z + pz * scale) for px, pz in pts]
    faces = [tuple(range(len(verts)))]
    return simple_mesh(name, verts, faces, mat)


def add_stroke_decal(name, x0, z0, x1, z1, halfw, y, mat, caps=True):
    """A flat band of the given half-width from one point to another.

    `caps` adds a disc at each end, which is what the offline rasteriser's
    capsule test draws. Without them the two disagree by half a stroke width at
    every joint - invisible in a render, but it moves the measured bounding box
    the acceptance test compares against Apple's photograph.
    """
    dx, dz = x1 - x0, z1 - z0
    L = math.hypot(dx, dz)
    if L < 1e-9:
        return None
    ux, uz = dx / L, dz / L
    px, pz = -uz * halfw, ux * halfw
    obj = add_polygon_decal(name, 0.0, 0.0,
                            [(x0 + px, z0 + pz), (x1 + px, z1 + pz),
                             (x1 - px, z1 - pz), (x0 - px, z0 - pz)],
                            y, mat, scale=1.0)
    if caps:
        for k, (ex, ez) in enumerate(((x0, z0), (x1, z1))):
            add_disc_decal("%s_cap%d" % (name, k), ex, ez, halfw, y, mat)
    return obj


def add_disc_decal(name, x, z, r, y, mat, verts=28):
    pts = [(r * math.cos(2.0 * math.pi * i / verts),
            r * math.sin(2.0 * math.pi * i / verts)) for i in range(verts)]
    return add_polygon_decal(name, x, z, pts, y, mat, scale=1.0)


def build_rear_icons(mats, y_face):
    """The engraved icon row above the connectors.

    Apple's rear photo shows, left to right in model space: the Thunderbolt
    bolt over the USB-C group, the Ethernet mark over the RJ45, the USB trident
    over the USB-A pair, the word HDMI over the HDMI port and the headphone
    mark over the jack, all at 60.3 mm from the top, i.e. ICON_Z.

    Nothing about the marks is decided here. ICON_GLYPHS in the spec carries
    the geometry, measured off apple_hw_back.jpg with tools/glyph_grid.py, and
    tools/compare_render.py rasterises the same list so the model and the
    checked image cannot disagree. That matters because the previous version
    kept its own coordinates and its own shapes: the offsets were 7.9 mm out
    for four of the five, the Ethernet mark was four upward chevrons with no
    dots instead of two outward chevrons with three, the trident ended in a
    square instead of a circle, the bolt was twice the size it should be, and
    "HDMI" was a font nobody here could measure.
    """
    y = y_face + 0.004
    silk = mats["silk"]

    for name, parts in sorted(S.ICON_GLYPHS.items()):
        cx = S.ICON_GLYPH_X[name]
        for i, part in enumerate(parts):
            tag = "Icon_%s_%02d" % (name, i)
            kind = part[0]
            if kind == "poly":
                add_polygon_decal(tag, cx, ICON_Z,
                                  [(px, pz) for px, pz in part[1]],
                                  y, silk, scale=1.0)
            elif kind == "stroke":
                _, x0, z0, x1, z1, halfw = part
                add_stroke_decal(tag, cx + x0, ICON_Z + z0, cx + x1, ICON_Z + z1,
                                 halfw, y, silk)
            elif kind == "disc":
                _, px, pz, r = part
                add_disc_decal(tag, cx + px, ICON_Z + pz, r, y, silk)
            elif kind == "arc":
                # The headphone headband. compare_render.glyph_mask has
                # rasterised arcs since the glyph was re-measured, but this
                # dispatcher had no arm for them and raised ValueError on the
                # first one - so the build died before writing the .blend and
                # the headphone mark existed in the checked image and nowhere
                # else. One table, every consumer able to read all of it.
                _, px, pz, r, hw, a0, a1 = part
                add_arc_decal(tag, cx + px, ICON_Z + pz, r, hw, a0, a1, y, silk)
            else:
                raise ValueError("unknown icon primitive %r" % (kind,))


# add_text_decal() used to live here, to set the "HDMI" wordmark as a Blender
# text object. It is gone with the rest of the old icon code: a font's metrics
# are not something this project can measure against a photograph, so the
# wordmark is strokes in the spec like every other glyph.


# --------------------------------------------------------------- front panel
def build_front_io(mats, body):
    """Front: 2x USB-C, the SDXC slot and the status LED.

    The front is at -Y and a front view puts model +X on the image's RIGHT, so
    the measured image-x maps through x = x_img - 98.5. FRONT_PORTS is already
    in model space: the ports sit on the -X side and the LED on the +X side.

    The SDXC slot measures 27.0 x 2.7 mm. The previous build used 13.0 x 3.4,
    which is less than half the real opening.
    """
    # The FRONT panel is at y = +D/2. This duplicated the rear's y_face, so
    # the two I/O rows were cut into the same face - the rear row first, then
    # the front row straight over it.
    y_face = D / 2.0
    # the socket mouth sits just inside the skin; the body runs further
    # inward, i.e. toward -Y
    y_mouth = y_face - 0.10

    for name, x, w, h in FRONT_PORTS:
        cut_from_body(body, "Front_" + name, x, y_face + 0.20, IO_Z,
                      w + 0.20, 0.60, h + 0.20, bevel=0.05, mats=mats)
        paint_recess_black(body, y_face - 0.02, y_face + 0.58,
                           abs(x) + w / 2.0 + 0.12, IO_Z - h / 2.0 - 0.12,
                           IO_Z + h / 2.0 + 0.12)
        # The socket's mouth sits just inside the panel and the body runs
        # further inward. The front face is at +Y, so inward is -1; the rear
        # face is at -Y, so the rear row passes +1. Getting this backwards put
        # every socket's back plate 2.4 mm outside the skin and the depth at
        # 203 mm against Apple's 197.
        add_socket("Front_" + name, x, IO_Z, w, h, y_mouth, mats,
                   depth=0.34, wall=0.045, inward=-1.0)

    # Status LED: a 2.7 mm white lens standing slightly proud of the panel.
    # The previous build bored a 3.5 mm headphone jack here — right position,
    # wrong feature, and a black hole where the real part has a light.
    add_cylinder("StatusLED", LED_X, y_face + 0.02, IO_Z, LED_R, 0.10,
                 mats["led"], verts=48, axis="Y")
    return body


# -------------------------------------------------------------- the underside
def build_bottom_cover(mats):
    """The removable bottom cover, and the intake perforated across it.

    This is not a styling detail. Apple says the machine has "over 4,000
    perforations on the back and bottom of the enclosure" (newsroom,
    2022-03-08) — the bottom is a named intake face, not bare metal. iFixit
    confirms it from the other end: the bottom cover is the only external
    serviceable part (4x T10 8 mm under an adhesive screw pad) and it is
    opened by "insert the point of a spudger in one of the bottom cover's
    ventilation holes" (iFixit 165048).

    The cover is therefore a separate plate under the extrusion, perforated
    with the same obround lattice as the base band, and the four feet stand
    on it.
    """
    return add_box("BottomCover", 0.0, 0.0, FOOT_H / 2.0,
                   W - 2 * R_VERT, D - 2 * R_VERT, FOOT_H, mats["alu"],
                   bevel=0.06)


def build_bottom_intake(mats):
    """A lattice of intake holes across the bottom cover, drilled upward.

    Apple's "over 4,000 perforations on the back and bottom" is the only
    published count and it covers BOTH faces, so the split between them is not
    published - and the rear field (3,038) plus the base band (3,104) already
    exceed 4,000 on their own, so the count cannot be used to derive this
    face's size either. It is placed to read as a real intake and is labelled
    as the design choice it is, exactly as the fan bore already is.
    """
    ring = rounded_rect(max(GRILLE_HOLE_RX - GRILLE_HOLE_RZ, 1e-4),
                        GRILLE_HOLE_RZ, GRILLE_HOLE_RZ, seg=4, edge_sub=1)
    nring = len(ring)
    half_x = W / 2.0 - R_VERT - 0.30
    half_y = D / 2.0 - R_VERT - 0.30
    depth = GRILLE_RECESS
    verts, faces = [], []
    placed = 0
    cols = int(2 * half_x / GRILLE_PITCH_X)
    rows_n = int(2 * half_y / GRILLE_PITCH_X)
    for iy in range(rows_n):
        for ix in range(cols):
            x = -half_x + ix * GRILLE_PITCH_X
            y = -half_y + iy * GRILLE_PITCH_X
            base = len(verts)
            # Two rings extruded UP from the cover's outer face into the
            # enclosure. A hole is a tube along its own normal; building the
            # ring in the (x, y) plane and pushing it along +Z is the same
            # construction as build_grille_field, rotated to face down.
            for oz in (0.0, depth):
                for ox, oy in ring:
                    verts.append((x + ox * GRILLE_HOLE_RX,
                                  y + oy * GRILLE_HOLE_RZ,
                                  FOOT_H + oz))
            for k in range(nring):
                k2 = (k + 1) % nring
                faces.append((base + k, base + k2,
                              base + nring + k2, base + nring + k))
                faces.append((base + nring + k, base + nring + k2,
                              base + k2, base + k))
            placed += 1
    obj = simple_mesh("BottomIntake", verts, faces, mats["grille"], smooth=True)
    print("  BottomIntake: %d holes, pitch %.3f cm" % (placed, GRILLE_PITCH_X))
    return obj


def build_bottom_details(mats):
    """Four rubber feet standing on the perforated bottom cover.

    The round control is the power button on the rear panel, modelled in
    build_power_button; there is nothing else on the underside.
    """
    for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        add_cylinder("Foot_%d" % (i + 1), sx * FOOT_XY, sy * FOOT_XY,
                     FOOT_H + 0.10, FOOT_R, 0.20, mats["rubber"])


# ------------------------------------------------------------------ internals
def build_internals(mats):
    """The inside of the machine, from Apple's X-ray photography.

    reference/hk/hw_elements_fans_xray.jpg and hw_elements_case_xray.jpg are
    rear cutaways with the case ghosted. Read as fractions of the 95 mm height
    they give the stack, top to bottom:

      * two blower shrouds, z 8.9 .. 5.0, each ~80 mm wide, split by a narrow
        centre gap and filling nearly the whole width — this is the single
        largest mass in the machine and it is what the rear grille feeds
      * the finned heatsink immediately under them, z 5.0 .. 4.5
      * the copper heat-pipe / board plane, z 4.5 .. 4.1, spanning the width
      * the logic board and its components, z 4.1 .. 2.3
      * the power supply at the bottom right, z 2.3 .. 0.9, with the copper
        coil that shows as a bright disc in the X-ray; connectors bottom left
      * the perforated base band wrapping the bottom edge

    An earlier revision put the fans at z 6.15, the heatsink at 3.60 and the
    power supply at z 3.0. That stacks everything too low and leaves the whole
    bottom third of the case empty, when the PSU and speaker belong down at the
    intake they feed.
    """
    wall_top = H_TOTAL - 0.30
    fan_z = FAN_Z
    fan_r = FAN_R
    for k, sx in enumerate((-1, 1)):
        cx = sx * FAN_X
        # shroud: a rounded rectangular duct with a round bore.  Centred on the
        # measured axis, not lifted: FAN_Z/FAN_SHROUD_H are already set so the
        # top face lands just under the top cover's inner face.
        add_box("Fan%d_shroud" % (k + 1), cx, 0.0, fan_z,
                FAN_SHROUD_W, FAN_SHROUD_D, FAN_SHROUD_H, mats["fan"], bevel=0.35)
        add_tube("Fan%d_bore" % (k + 1), cx, 0.0, fan_z, fan_r, fan_r - 0.22,
                 FAN_SHROUD_H * 0.96, mats["cavity"], verts=64)
        add_cylinder("Fan%d_hub" % (k + 1), cx, 0.0, fan_z, fan_r * 0.30, 1.30,
                     mats["fan"], verts=32, axis="Z")
        # impeller blades, swept around the hub. The blade angle is handed to
        # the primitive: add_box ends with transform_apply, so assigning
        # rotation_euler afterwards would spin the baked world-space mesh
        # about the origin and fling the blade right across the case.
        blades = 11
        for b in range(blades):
            a = 2 * math.pi * b / blades
            bx, by = cx + (fan_r * 0.58) * math.cos(a), (fan_r * 0.58) * math.sin(a)
            add_box("Fan%d_blade%02d" % (k + 1, b), bx, by, fan_z,
                    fan_r * 0.72, 0.16, 1.00, mats["fan"], bevel=0.04,
                    rot=(0.0, 0.0, a + 0.55))

    # The centre spine between the two fan bays, and the cross-member that
    # interrupts it. Measured off the X-ray: a bright bar with a hard edge on
    # both sides of the case centreline, 3.3 mm wide, running the full height
    # of the fan bay. The earlier build left this whole region empty, which is
    # the most visible thing missing from a front cutaway.
    add_box("Centre_spine", 0.0, 0.0, (SPINE_Z0 + SPINE_Z1) / 2,
            SPINE_W, SPINE_D, SPINE_Z1 - SPINE_Z0, mats["alu_raw"], bevel=0.04)
    add_box("Spine_crossmember", 0.0, 0.0, (SPINE_BREAK_Z0 + SPINE_BREAK_Z1) / 2,
            SPINE_BREAK_HALF_X * 2, SPINE_D * 0.72,
            SPINE_BREAK_Z1 - SPINE_BREAK_Z0, mats["fan"], bevel=0.06)

    # Heatsink mass directly under the fans: a finned aluminium block.
    hs_z = HEATSINK_Z
    add_box("Heatsink_base", 0.0, 0.0, hs_z, 16.8, 12.6, 0.50, mats["alu_raw"])
    for i in range(32):
        fy = -5.9 + i * 0.37
        add_box("Heatsink_fin%02d" % i, 0.0, fy, hs_z + 0.48, 16.4, 0.16, 0.80,
                mats["alu_raw"])
    # the package under the fin stack
    add_box("SoC_package", 0.0, 0.0, hs_z - 0.36, 4.6, 4.6, 0.28, mats["chip"])

    # The copper heat pipe / board plane that crosses the whole machine here.
    add_box("HeatPipe_plane", 0.0, 0.0, PIPE_Z, 17.6, 14.4, 0.22, mats["copper"])

    # Logic board, full width.
    pcb_z = PCB_Z
    add_box("LogicBoard", 0.0, 0.0, pcb_z, 18.2, 15.6, 0.16, mats["pcb"])
    # memory packages either side of the SoC
    for k, sx in enumerate((-1, 1)):
        add_box("Memory_%d" % (k + 1), sx * 3.9, 0.0, pcb_z + 0.22, 4.2, 2.6, 0.28,
                mats["memory"])
    # two SSD modules, removable, on the board
    for k, sy in enumerate((-1, 1)):
        add_box("SSD_%d" % (k + 1), -5.2, sy * 3.4, pcb_z + 0.20, 4.0, 2.2, 0.24,
                mats["insul"], bevel=0.05)

    # Power supply, bottom right, with the copper coil that reads as a bright
    # disc in the rear X-ray.
    add_box("PSU", 5.90, 1.4, PSU_Z, 5.6, 9.4, 1.70, mats["fan"], bevel=0.12)
    add_cylinder("PSU_coil", 5.90, -3.6, PSU_Z + 0.10, 1.15, 1.40,
                 mats["copper"], verts=32, axis="Z")
    add_box("PSU_cap", 5.90, 3.4, PSU_Z + 0.20, 5.0, 2.0, 1.40,
            mats["insul"], bevel=0.10)

    # The row of tall electrolytics.  These were on the logic board at
    # z pcb_z+0.60, which put their tops at 4.65 cm: through the copper plane
    # at 3.95 and into the heatsink base at 4.75.  Both are legal Blender
    # objects and nothing complained.  The X-ray puts the row where it
    # actually is - a line of cylinders standing on the floor frame, spanning
    # the lower middle of the case just left of the supply, z 0.6..1.3 cm.
    for k in range(7):
        add_cylinder("Cap_%d" % (k + 1), -6.0 + k * 1.3, -2.0, 1.00,
                     0.30, 0.70, mats["alu_raw"], verts=20, axis="Z")
    # heat pipe: a copper tube running from the PSU up into the heatsink, which
    # is what the X-ray shows looping on the right.
    pipe_pts = [(5.90, -4.0, PSU_Z + 1.20), (5.90, -5.4, PIPE_Z + 0.40),
                (4.20, -6.0, PIPE_Z + 0.35), (1.90, -5.6, PIPE_Z + 0.20),
                (0.00, -4.6, hs_z - 0.10), (0.00, -2.2, hs_z + 0.05)]
    for i in range(len(pipe_pts) - 1):
        add_cylinder_between("HeatPipe%d" % i, pipe_pts[i], pipe_pts[i + 1],
                             0.20, mats["copper"], verts=20)

    # Speaker and the front I/O harness, bottom left.
    add_box("Speaker", -6.6, -5.4, SPEAKER_Z, 2.6, 2.2, 1.10,
            mats["fan"], bevel=0.12)
    add_box("FrontIO", -6.6, 3.2, SPEAKER_Z + 0.20, 3.4, 5.0, 0.80,
            mats["insul"], bevel=0.10)

    # The internal frame the boards bolt to.
    for sx in (-1, 1):
        add_box("Frame_side%d" % (sx > 0), sx * 8.95, 0.0, 4.0, 0.5, 15.0, 7.4,
                mats["alu_raw"])
    add_box("Frame_floor", 0.0, 0.0, 0.52, 17.4, 15.0, 0.22,
            mats["alu_raw"])
    return True


# -------------------------------------------------------------------- studio
def build_studio(scene):
    """A generated studio environment.

    At roughness 0.2 the shell is close to a mirror, and a constant world
    background gives it nothing to reflect — the body then reads as matte white
    plastic, which is the single loudest tell that a render is CG. A gradient
    sky with a bright overhead band is what makes the aluminium read as metal.
    """
    world = bpy.data.worlds.new("Studio")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 1.0
    grad = nt.nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "EASING"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.28
    ramp.color_ramp.elements[0].color = (0.16, 0.17, 0.20, 1.0)   # floor bounce
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = (0.98, 0.99, 1.00, 1.0)   # sky
    mid = ramp.color_ramp.elements.new(0.50)
    mid.color = (0.46, 0.48, 0.53, 1.0)
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (math.radians(90), 0, 0)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    # The Mapping node's Vector is an INPUT socket, not an output. Linking a
    # node's output into it raises "Same input/output direction of sockets" and
    # aborts the build, which is how a studio environment that has been in
    # this file for a long time became the last thing standing between the
    # model and a saved .blend.
    nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], grad.inputs["Vector"])
    nt.links.new(grad.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])

    bpy.ops.mesh.primitive_plane_add(size=200.0, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "Floor"
    floor.data.materials.append(make_mat("Floor", (0.62, 0.62, 0.63), 0.0, 0.42))

    def area(name, loc, rot, size, power):
        bpy.ops.object.light_add(type="AREA", location=loc, rotation=rot)
        o = bpy.context.active_object
        o.name = name
        o.data.size = size
        o.data.energy = power
        return o

    area("Key", (-26, -30, 34), (math.radians(46), 0, math.radians(-40)), 40, 420)
    area("Fill", (30, -20, 20), (math.radians(66), 0, math.radians(56)), 34, 120)
    area("Rim", (6, 30, 30), (math.radians(-52), 0, math.radians(8)), 30, 230)
    area("Top", (0, 0, 40), (0, 0, 0), 34, 130)
    # grazing light into the rear connectors so they are not a black bar
    area("RearBayFill", (2, 34, 16), (math.radians(74), 0, math.radians(184)), 12, 200)

    for name, loc, rot, sx, sy in (
        ("BounceL", (-34, 4, 16), (math.radians(90), 0, math.radians(90)), 40, 26),
        ("BounceR", (34, 4, 16), (math.radians(90), 0, math.radians(-90)), 40, 26),
    ):
        bpy.ops.mesh.primitive_plane_add(size=1.0, location=loc, rotation=rot)
        card = bpy.context.active_object
        card.name = name
        card.scale = (sx, sy, 1.0)
        card.data.materials.append(make_mat("Bounce", (0.95, 0.95, 0.96), 0.0, 0.60))
        card.visible_shadow = False


# --------------------------------------------------------------------- cameras
# Azimuth is measured in the world XY plane: 0 puts the camera on +X, 90 on
# +Y, 180 on -X, 270 on -Y. The convention is +Y = FRONT and -Y = REAR, so the
# view NAMES below needed the angles to match it and did not - `03_rear` was
# asked for at 180 degrees, which is the LEFT side, and every frame was a
# rotation away from the one it claimed to be. Measured, from the camera
# positions this table produces:
#
#     az=0    -> +X, the right side
#     az=90   -> +Y, the front
#     az=180  -> -X, the left side
#     az=270  -> -Y, the rear
#
# So the front is 90, the rear is 270, and a side view is 0 or 180.
VIEWS = [
    ("01_front", "front", 90.0, 2.0, 46.0),
    ("02_side", "side", 0.0, 2.0, 46.0),
    ("03_rear", "rear", 270.0, 2.0, 46.0),
    ("04_hero", "3q", 235.0, 16.0, 44.0),
    ("05_top", "top", 200.0, 88.0, 44.0),
    ("06_bottom", "bottom", 20.0, -88.0, 44.0),
    # The closeups are framed by LENS AND DISTANCE TOGETHER, and they were
    # wrong by a wide margin. An 85 mm lens 9 cm from the subject sees 3.8 cm
    # across, and the chassis is 19.7 cm wide and 9.5 cm tall - so the frame
    # was smaller than the subject and a 10-degree elevation threw it out of
    # shot entirely. Measured, a 9-ray grid across `09_grille_macro`: four
    # rays hit nothing at all, and the rest struck the body between z 26.7 and
    # 66.0 mm, so the top half of every closeup was empty background.
    #
    # The macro wants a frame about 12 cm across, which at 85 mm is 55 cm of
    # distance - or a shorter lens. 50 mm from 28 cm gives 10 cm, which covers
    # a dozen hole columns at a 1.86 mm pitch and keeps the bores resolvable
    # at render resolution.
    ("07_front_closeup", "front", 90.0, 4.0, 24.0),
    ("08_rear_closeup", "rear", 270.0, 4.0, 24.0),
    ("09_grille_macro", "rear", 270.0, 0.0, 28.0),
    ("10_cutaway", "cutaway", 235.0, 14.0, 42.0),
]

TARGETS = {
    # Closeup camera targets. +Y is the front (USB-C, SDXC, LED) and -Y is the
    # rear (the I/O row and the exhaust field); these were all on +Y, so the
    # "rear closeup" framed the front.
    "07_front_closeup": (-5.9, D / 2.0, IO_Z),
    "08_rear_closeup": (2.0, -D / 2.0, IO_Z),
    "09_grille_macro": (0.0, -D / 2.0, 6.6),
    "10_cutaway": (0.0, 0.0, H_TOTAL / 2.0),
}


def place_camera(name, az, el, dist, target):
    az_r, el_r = math.radians(az), math.radians(el)
    cam_data = bpy.data.cameras.new(name)
    # The lens follows from the DISTANCE and HOW MUCH THE FRAME HAS TO COVER.
    # It used to be a bare `85 if dist < 20 else 62`, which is a portrait lens
    # at a macro distance: 85 mm at 9 cm sees 3.8 cm across, the chassis is
    # 19.7 cm wide, and the subject falls out of shot. Measured, a 9-ray grid
    # across `09_grille_macro`: four rays hit nothing at all and the rest
    # struck the body below the field.
    #
    # Blender's sensor is 36 mm wide, so a frame W cm across at distance D
    # needs f = 18 * D / W. The widths are chosen per view, and the clamp
    # keeps the result inside a range that does not distort.
    half = W / 2.0 if dist >= 40.0 else (6.0 if dist >= 20.0 else 5.0)
    cam_data.lens = max(24.0, min(120.0, 18.0 * dist / half))
    cam = bpy.data.objects.new(name, cam_data)
    bpy.context.collection.objects.link(cam)
    # bpy.context.collection is not always the scene's collection - under
    # --background it can be a default that does not exist, and the link above
    # then does nothing at all: no camera in the scene, scene.camera stays
    # None, and the render is an empty frame with no error to explain it.
    # Link to the scene explicitly and fall back only if that is missing too.
    if name not in bpy.context.scene.objects:
        bpy.context.scene.collection.objects.link(cam)
    cam.location = Vector((
        dist * math.cos(el_r) * math.cos(az_r) + target[0],
        dist * math.cos(el_r) * math.sin(az_r) + target[1],
        dist * math.sin(el_r) + target[2],
    ))
    direction = (Vector(target) - cam.location).normalized()
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return cam


# ------------------------------------------------------------------------ main
def evaluated_bbox(skip=("Floor", "BounceL", "BounceR")):
    deps = bpy.context.evaluated_depsgraph_get()
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.name in skip:
            continue
        ev = obj.evaluated_get(deps)
        for corner in ev.bound_box:
            wc = ev.matrix_world @ Vector(corner)
            for i in range(3):
                lo[i] = min(lo[i], wc[i])
                hi[i] = max(hi[i], wc[i])
    return lo, hi, hi - lo


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "CENTIMETERS"
    scene.unit_settings.scale_length = 1.0

    mats = build_materials()
    body = build_body(mats)
    report_stage(body, "lofted")
    hollow_body(body, mats)
    report_stage(body, "hollowed")

    # The prisms cross the wall and stop well INSIDE the cavity, so neither
    # cap coincides with a face. See build_grilles() for the measurements
    # behind every one of these numbers.
    build_grilles(mats, body, WALL + 0.45)
    report_stage(body, "grilles")

    build_rear_io(mats, body)
    report_stage(body, "rear_io")
    build_front_io(mats, body)
    build_bottom_cover(mats)
    build_bottom_intake(mats)
    build_bottom_details(mats)
    report_stage(body, "bottom_io")
    build_internals(mats)
    build_studio(scene)

    lo, hi, size = evaluated_bbox()
    print("=" * 60)
    print("BBOX_MIN_CM  %.4f %.4f %.4f" % tuple(lo))
    print("BBOX_MAX_CM  %.4f %.4f %.4f" % tuple(hi))
    print("BBOX_SIZE_CM %.4f %.4f %.4f" % tuple(size))
    for axis, got, want in zip("XYZ", size, (W, D, H_TOTAL)):
        print("  %s  got %.4f cm  want %.4f cm  delta %+.3f mm"
              % (axis, got, want, (got - want) * 10.0))
    print("=" * 60)

    os.makedirs(OUT_DIR, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    if os.environ.get("SKIP_RENDER") == "1":
        print("BUILD_OK (render skipped)")
        return

    scene.render.engine = "CYCLES"
    scene.cycles.samples = int(os.environ.get("SAMPLES", "48"))
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1500
    scene.render.resolution_y = 1125
    scene.render.image_settings.file_format = "PNG"

    # Blender 4.x defaults to AgX, which is an HDR tone mapper whose entire
    # job is to ROLL OFF CONTRAST - it compresses the gap between a lit metal
    # panel and the shadow inside a 1.4 mm perforation until the two are the
    # same value. Measured with AgX in place: geometrically perfect bores, a
    # ray passing straight through every one of them, and a render with a
    # local luminance spread of 1.0 out of 255 across the whole field. The
    # 87% of pixels between 20 and 116 were the panel and all of its holes
    # together, in one indistinguishable band.
    #
    # Apple's product photography is a direct tone map. A perforation is
    # 1.5 mm of black anodised bore, and it has to be allowed to go black
    # against lit aluminium. AgX will not let it.
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0

    for name, kind, az, el, dist in VIEWS:
        # TARGETS is keyed by VIEW NAME. Looking it up by `kind` instead meant
        # every closeup fell back to the body centre and framed the whole
        # machine from 17 cm.
        target = TARGETS.get(name, TARGETS.get(kind, (0.0, 0.0, H_TOTAL / 2.0)))
        if kind == "cutaway":
            # Hide the near half of the shell so the internals read.
            body.hide_render = True
            for o in scene.objects:
                if o.name in ("RearField",):
                    o.hide_render = True
        cam = place_camera("CAM_" + name, az, el, dist, target)
        scene.camera = cam
        path = os.path.join(OUT_DIR, name + ".png")
        scene.render.filepath = path
        try:
            bpy.ops.render.render(write_still=True)
            print("RENDERED %s" % path)
        except Exception as exc:
            print("GPU_FAIL %s (%s) -> CPU retry" % (name, exc))
            scene.cycles.device = "CPU"
            bpy.ops.render.render(write_still=True)
            print("RENDERED %s" % path)
        if kind == "cutaway":
            body.hide_render = False
            for o in scene.objects:
                if o.name in ("RearField",):
                    o.hide_render = False

    print("BUILD_OK")


if __name__ == "__main__":
    main()
