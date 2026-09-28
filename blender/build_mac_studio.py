"""Mac Studio (2024/2025/2026, aluminum) 1:1 model — headless bpy build.

Official specs (https://www.apple.com/mac-studio/specs/, fetched 2026-09-27):
    Height  3.7 in (9.5 cm)
    Width   7.7 in (19.7 cm)
    Depth   7.7 in (19.7 cm)

Orientation: -Y = front, +Y = back, +Z = up, origin at footprint centre on the
table surface. Units are centimetres (scene scale_length = 1.0).
"""

import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector

# ---------------------------------------------------------------- parameters
W = 19.7          # X, width
D = 19.7          # Y, depth
H_TOTAL = 9.5     # Z, full height incl. feet
FOOT_H = 0.2      # rubber feet height
BODY_H = H_TOTAL - FOOT_H
R_VERT = 1.05     # vertical corner radius. Apple calls the shell "a single piece
                  # of aluminium"; the corner is a crisp machined break, NOT a
                  # soft pillow. At 1.6 cm it was 8.1% of the 19.7 cm width and
                  # every elevation read as a bulging pillow even though the
                  # panel geometry was provably flat (99 front-face verts, all
                  # at y = -9.8500, spread 0.0000 cm).
R_HORZ = 0.48     # top/bottom edge fillet. Slightly LARGER than the vertical
                  # corner: on the real part the top edge break is the softer
                  # of the two, and 0.35 read as a hard machined edge.
ARC_SEG = 20      # segments per rounded corner. At 8 the corner read as a
                  # visible faceted curve — a flat-shaded 8-gon arc against a
                  # 19.7 cm face is obvious, and it is most of what made the
                  # silhouette look soft rather than machined.

OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "renders"))
BLEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mac_studio.blend"))


# ------------------------------------------------------------------ materials
def make_mat(name, base, metallic, rough):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:  # 4.x always has it, but be explicit
        bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = rough
    m.diffuse_color = (*base, 1.0)
    return m


def build_materials():
    return {
        # anodised silver aluminium, satin finish. Real Mac Studio aluminium
        # reads noticeably reflective in a studio setup — too high a roughness
        # makes it look like matte plastic, which is the single biggest
        # giveaway that a render is CG rather than a product photo.
        "alu": make_mat("Aluminium_Silver", (0.760, 0.767, 0.775), 1.0, 0.19),
        # dark anodised bottom grille plate
        "grille": make_mat("Grille_DarkAlu", (0.135, 0.138, 0.142), 0.75, 0.42),
        # unlit cavity seen through the perforations
        "cavity": make_mat("Cavity_Black", (0.016, 0.016, 0.018), 0.0, 0.70),
        # connector bodies: dark grey plastic, not pure black — a pure black
        # socket interior renders as a flat silhouette with no readable shape
        "port": make_mat("Port_Black", (0.075, 0.076, 0.080), 0.0, 0.42),
        # rubber feet
        "rubber": make_mat("Foot_Rubber", (0.045, 0.045, 0.048), 0.0, 0.85),
        # status LED
        "led": make_mat("Status_LED", (0.85, 0.90, 0.95), 0.0, 0.20),
    }


# ------------------------------------------------------------------ geometry
def rounded_rect(hx, hy, r, seg=ARC_SEG, edge_sub=4):
    """CCW point ring of a rounded rectangle.

    Every straight edge is subdivided into `edge_sub` extra points: without
    them a flat panel becomes one enormous quad, and auto-shaded normals across
    it produce the visible horizontal banding on the front face.
    """
    r = max(0.02, min(r, hx - 0.02, hy - 0.02))
    corners = (
        (hx - r, hy - r, 0.00),
        (-hx + r, hy - r, 0.25),
        (-hx + r, -hy + r, 0.50),
        (hx - r, -hy + r, 0.75),
    )
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


def boolean_diff(body, cutter, label="Cut"):
    """Apply an EXACT boolean difference and drop the cutter.

    The body MUST already be triangulated (see triangulate_caps): the lofted
    shell's top/bottom caps are large non-planar n-gons, and the EXACT solver
    mis-resolves their winding. Symptom of skipping it: the boolean "succeeds"
    but merges the cutter's outer half into the shell, and the bbox grows by
    the cutter's overhang instead of shrinking.
    """
    triangulate_caps(body)
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
    """Boolean-difference a rounded box out of the shell — a real recess.

    See boolean_diff for why the body has to be triangulated first.
    """
    cutter = add_box("_cut_" + name, cx, cy, cz, sx, sy, sz,
                     (mats or {}).get("cavity") or bpy.data.materials["Cavity_Black"],
                     bevel=bevel)
    return boolean_diff(body, cutter, "Cut_" + name)


def paint_recess_black(obj, y_lo, y_hi, x_extent, z_lo, z_hi, slot=1):
    """Force every face inside a rear recess to the cavity material.

    A boolean difference flips the cutter's geometry to become the recess's
    walls, but those flipped faces keep the SHELL's material index — the bay
    ended up with 45 aluminium faces at its back wall (y=9.75), so the port bay
    read as a bright silver recess instead of a black cavity. The cutter's own
    material does not help: EXACT only carries a material across if the target
    lacks the slot, and the target already has two.

    Select by volume, not by normal: the recess's back wall has a normal
    pointing *into* the bay, same as its side walls, so a normal test misses it.
    """
    me = obj.data
    for p in me.polygons:
        c = p.center
        if (y_lo < c.y < y_hi and abs(c.x) < x_extent
                and z_lo < c.z < z_hi):
            p.material_index = slot
    return obj


def triangulate_caps(obj):
    """Make the whole mesh triangles, once.

    The guard must look at polygon sizes, not at `data.loop_triangles` — that
    cache is lazily filled, so its length is unreliable before the first
    tessellation and the check would re-triangulate on every cut.
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


def build_body(mats):
    """Lofted rounded box: exact 19.7 x 19.7 footprint, 9.5 tall incl. feet.

    The perforated band around the lower perimeter is a genuine recess in this
    loft, not a boolean cut: `grille_inset` pulls the profile inboard across
    the band height so the groove is part of the surface from the start. A
    boolean was the obvious approach and it fought back three separate ways —
    a cutter tangent to the skin cuts nothing, a cutter buried inside the shell
    cuts nothing, and a cutter proud of the skin leaves the difference as new
    geometry and inflates the bounding box by the overshoot (+1.16 mm). None of
    those failures is visible from the vertex count or the bbox alone.
    """
    z_lo, z_hi = FOOT_H, H_TOTAL
    z_g0, z_g1 = GRILLE_BAND_Z0, GRILLE_BAND_Z1

    levels = []
    steps = 8
    for i in range(steps + 1):                       # bottom fillet
        levels.append(z_lo + R_HORZ * (1.0 - math.cos(math.pi / 2 * i / steps)))
    for i in range(GRILLE_LEVELS + 1):               # base band
        levels.append(z_g0 + (z_g1 - z_g0) * i / GRILLE_LEVELS)
    for i in range(LOWER_F_LEVELS + 1):           # lower rear field
        levels.append(LOWER_F_Z0 + (LOWER_F_Z1 - LOWER_F_Z0)
                      * i / LOWER_F_LEVELS)
    for i in range(UPPER_LEVELS + 1):                # upper rear/side field
        levels.append(UPPER_Z0 + (UPPER_Z1 - UPPER_Z0) * i / UPPER_LEVELS)
    for i in range(steps + 1):                       # top fillet
        levels.append(z_hi - R_HORZ * (1.0 - math.cos(math.pi / 2 * i / steps)))
    # A field's top edge can sit above the midpoint, so appending field levels
    # before the straight band and the top fillet leaves the list out of order
    # and the loft folds through itself — which showed up as a bounding box
    # 4.6 cm short in Z rather than an error. Sort and dedupe; a level list
    # must be strictly increasing for the loft to be a solid.
    levels = sorted(set(round(v, 4) for v in levels))

    verts, faces, mats_per_face = [], [], []
    hx, hy = W / 2.0, D / 2.0
    gap_t = UPPER_FRONT_GAP / (2.0 * hy)   # front-corner gap as a 0..1 frac

    for z in levels:
        base_d = fillet_inset(z, z_lo, z_hi)
        prof = rounded_rect(hx - base_d, hy - base_d, R_VERT - base_d)
        # The upper and lower perforated fields stop short of the front face,
        # so their recess depth is a function of position around the perimeter,
        # not just of z. Measure it on the UNINSET profile, then re-proportion
        # each point to the inset profile — scaling by the profile's own extents
        # keeps the rounded corners correct instead of squashing them.
        #
        # The BASE band is different: it wraps the whole perimeter, front
        # included. Apple's front diagram reads 23% dark across the bottom 10%
        # of the panel, so the front's base band is perforated too, and this
        # factor used to force it to 0 there — which left the front face solid
        # down to the feet while the other three faces were perforated.
        ux0, uy0 = hx - base_d, hy - base_d
        in_base = (GRILLE_BAND_Z0 - 1e-6 <= z <= GRILLE_BAND_Z1 + 1e-6)
        for px, py in prof:
            t = (py + uy0) / (2.0 * uy0)          # 0 at the front, 1 at the rear
            if t >= 1.0 - gap_t:
                ff = 1.0
            elif t <= gap_t:
                ff = 1.0 if in_base else 0.0
            else:
                u = (t - gap_t) / (1.0 - 2.0 * gap_t)
                ff = u * u * (3.0 - 2.0 * u)     # smoothstep
            d = base_d + grille_inset(z, ff)
            verts.append((px / ux0 * (hx - d), py / uy0 * (hy - d), z))

    n = len(rounded_rect(hx, hy, R_VERT))
    for li in range(len(levels) - 1):
        a, b = li * n, (li + 1) * n
        for i in range(n):
            j = (i + 1) % n
            faces.append((a + i, a + j, b + j, b + i))
            mats_per_face.append(0)                  # aluminium

    faces.append(tuple(range(n - 1, -1, -1)))        # bottom cap -> cavity black
    mats_per_face.append(1)
    faces.append(tuple(range((len(levels) - 1) * n, len(levels) * n)))  # top cap
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


def auto_smooth(obj, angle):
    """Blender 4.1+ replaced mesh.use_auto_smooth with an operator/modifier."""
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    try:
        bpy.ops.object.shade_auto_smooth(angle=angle)   # 4.2+
    except Exception:
        try:
            bpy.ops.object.shade_smooth_by_angle(angle=angle)   # 4.1
        except Exception:
            bpy.ops.object.shade_smooth()


def link(obj, mats):
    bpy.context.collection.objects.link(obj)
    return obj


def simple_mesh(name, verts, faces, mat, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    me.materials.append(mat)
    me.update()
    obj = bpy.data.objects.new(name, me)
    link(obj, None)
    if smooth:
        auto_smooth(obj, math.radians(50))
    return obj


def add_box(name, cx, cy, cz, sx, sy, sz, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx, cy, cz))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if bevel > 0.0:
        # A bevel wider than half the shortest side self-intersects, and the
        # EXACT boolean solver then silently fails to cut (the cutter's own
        # bounds get merged into the shell instead). Clamp it.
        bevel = min(bevel, 0.45 * min(abs(sx), abs(sy), abs(sz)))
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 3
        mod.limit_method = "ANGLE"
    obj.data.materials.append(mat)
    return obj


def add_cylinder(name, cx, cy, cz, r, h, mat, verts=48, axis="Z"):
    rot = {"Z": (0, 0, 0), "Y": (math.pi / 2, 0, 0), "X": (0, math.pi / 2, 0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts, radius=r, depth=h, location=(cx, cy, cz), rotation=rot
    )
    obj = bpy.context.active_object
    obj.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    mod = obj.modifiers.new("Bevel", "BEVEL")
    mod.width = min(0.02, h * 0.35, r * 0.25)
    mod.segments = 2
    mod.limit_method = "ANGLE"
    obj.data.materials.append(mat)
    auto_smooth(obj, math.radians(40))
    return obj


# ------------------------------------------------------- perforated base band
# The real Mac Studio does NOT have a grille across the whole bottom. It has a
# shallow perforated band running around the lower perimeter — roughly 1.1 cm
# tall on a 9.5 cm body (~12%), with a solid lip below it and the perforated
# field wrapping around the front and side corners. Holes are small circles in
# staggered rows, not hexagons. (Verified against Apple's own product photos:
# the front face is smooth silver above this band.)
# Ventilation, laid out from Apple's own rear hardware diagram
# (/v/mac-studio/o/images/overview/connectivity/hw_back__*.jpg), read against a
# 10% grid overlay on the chassis silhouette:
#
#   0% .. 50% from the top   perforated field
#   50% .. 80%              solid band holding the port bay
#   80% .. 100%             perforated field again
#
# So the rear is perforated top AND bottom with a plain strip between them —
# not a narrow base band. An earlier build had only the bottom band and a
# smooth upper rear, which is the single biggest error this file had.
#
# The front panel is smooth silver above its base band (Apple's front diagram
# and the straight-on product shot both confirm), so the upper field stops
# short of the front face and tapers off around the front corners.
Z_TOTAL = H_TOTAL
GRILLE_H = 0.75     # height of the base band
GRILLE_Z0 = 0.20   # band floor; GRILLE_H + GRILLE_Z0 = GRILLE_BAND_Z1
GRILLE_PITCH = 0.22
# Base band open area, same derivation as UPPER_HOLE_R. Apple's diagram reads
# ~22% dark across the bottom two bands; the first pass opened
# pi * 0.058^2 / 0.22^2 = 0.208, which measured 25% — close enough, but r
# 0.057 at this pitch gives 0.201 and lands on the reference more closely.
GRILLE_HOLE_R = 0.057
GRILLE_RECESS = 0.14   # how deep the groove is cut into the shell

# The base band, all around. Modelled directly into the body loft.
#
# Height is set from the reference, not from taste. Mapping the pixel diff onto
# z (image row 0 is the top of the machine, so band 85-90% is z 0.95..1.43):
#
#     z 0.95..1.43   official  0% dark   solid
#     z 0.48..0.95   official 24% dark   perforated
#     z 0.00..0.48   official 22% dark   perforated
#
# So the band runs from the underside up to z 0.95, not to 1.62. The old
# ceiling of 1.62 put holes at z 0.95..1.43 where the real part is solid and
# measured 27% dark against a reference of 0%. Note the reference's bottom 5%
# band still reads as perforated even though it overlaps the feet plane — the
# band's holes start above the shell's own underside at z = FOOT_H = 0.2.
GRILLE_BAND_Z0 = 0.20   # groove floor, just above the underside
GRILLE_BAND_Z1 = 0.95   # groove ceiling
GRILLE_LEVELS = 4       # extra loft levels across the band, for crisp walls

# The three rear zones, as fractions of the 9.5 cm height.
#
# Measured from Apple's own rear hardware diagram (apple.com/hk/mac-studio/ ->
# hw_back__*.jpg, 656x322). Sampling the dark-pixel share in 5% horizontal
# bands across the chassis gives an unambiguous read:
#
#     0- 5%   0.0%   smooth
#     5-55%  ~43%    perforated field
#    55-70%   6%    the port band (solid, ports cut into it)
#    70-80%  ~28%    perforated field
#    80-90%   3%    solid transition
#    90-100% ~22%    the base band's perforation
#
# So the port band sits at 55..70% from the TOP, not at the 50..80% the first
# pass assumed, and the upper field reaches 55% rather than 50%.
#
# The 55..70% figure is where the dark CONNECTOR OPENINGS sit, not the extent
# of the recess. The recess has to clear its tallest connector: the RJ45 is
# 1.28 cm tall, and at the literal 15% (1.43 cm) that leaves 0.075 cm of
# aluminium above and below it, which is not a machined bay, it is a slot the
# jack is wedged into. 27..47% gives 1.90 cm, a real 0.3 cm margin top and
# bottom, and still keeps the bay clear of both perforated fields.
BAY_Z0 = Z_TOTAL * 0.27   # 2.57 cm
BAY_Z1 = Z_TOTAL * 0.47   # 4.47 cm

# The upper field: 5%..53% of the height from the top, stopping above the bay.
#
# The top bound is 5% down, not the diagram's literal 5%, because 5% of 9.5 cm
# is 0.475 cm and the top fillet R_HORZ occupies z 9.02..9.50. Ending the field
# at 0.95*H = 9.03 put its upper edge just inside that fillet, where the shell
# has already curved inward — the recess then ate the outermost skin and the
# rear panel came out 0.09 mm short in Y. 0.94 keeps a clear 0.09 cm of flat
# metal above the field, inside the fillet's straight run.
UPPER_Z0 = Z_TOTAL * 0.47
UPPER_Z1 = Z_TOTAL * 0.94
# Depth of the recessed field. The zone summary reads 31.2% dark against the
# reference's 42.8% even though the lattice geometry opens 39.6% of the
# surface — the holes are there but they do not go dark, because at 0.10 cm
# the recess is shallower than the hole radius (0.071) and light rakes across
# the far wall. Going to 0.22 overshoots the other way: the whole recessed
# floor fell below the dark threshold and the zone read 64.1%. 0.15 cm is
# roughly two hole radii — deep enough to shadow each opening individually,
# shallow enough that the floor between them still catches light.
UPPER_DEPTH = 0.15
UPPER_FRONT_GAP = 0.34   # the field stops this far short of the front face
UPPER_LEVELS = 5         # loft levels across the field
# Hole size is set from the OPEN AREA, not by eye. A pixel diff against
# Apple's rear diagram puts the perforated field at 42-45% dark pixels per
# band; the first pass read 20-29% because the lattice only opened 21% of the
# surface (pi * 0.052^2 / 0.20^2 = 0.212). These numbers open 41%:
#   pitch 0.20, r 0.071  ->  pi * 0.005041 / 0.0400 = 0.396
# The 0.20 pitch keeps a 0.058 cm web between holes, which is what the real
# part shows — the perforations are separated by metal, not merged into slots.
UPPER_PITCH = 0.20
UPPER_HOLE_R = 0.071

# The lower field: 70%..80% from the top, between the port band and the base.
LOWER_F_Z0 = Z_TOTAL * 0.20
LOWER_F_Z1 = Z_TOTAL * 0.30
LOWER_F_DEPTH = 0.10
LOWER_F_GAP = 0.34
LOWER_F_LEVELS = 3


def grille_inset(z, front_factor=1.0):
    """Extra profile inset at height `z` — the three ventilation recesses.

    * base band   z 0.42..1.62 — wraps the whole perimeter
    * upper field z 50%..93% of height — rear and sides only
    * lower field z 18%..34% of height — rear and sides only, below the ports

    `front_factor` scales the inset on the front face: 1.0 keeps the front's
    base band, 0.0 leaves the front completely smooth. The two rear fields pass
    through 0 there, so the front panel stays solid silver all the way up.

    Steps rather than ramps: the real part has a flat groove floor and a sharp
    edge, not a chamfer.
    """
    if GRILLE_BAND_Z0 - 1e-6 <= z <= GRILLE_BAND_Z1 + 1e-6:
        return GRILLE_RECESS * front_factor
    if UPPER_Z0 - 1e-6 <= z <= UPPER_Z1 + 1e-6:
        return UPPER_DEPTH * front_factor
    if LOWER_F_Z0 - 1e-6 <= z <= LOWER_F_Z1 + 1e-6:
        return LOWER_F_DEPTH * front_factor
    return 0.0


def build_grille_field(mats, name, z_lo, z_hi, depth, pitch, hole_r,
                       front_factor, seg=8, rows_cap=40):
    """Punch a lattice of hole tubes into a recessed field, radially outward.

    Shared by the base band (which wraps the whole perimeter) and the upper
    rear/side field (which stops short of the front). `front_factor(py)` scales
    how much of the field exists at a given point around the profile, so the
    same path walk serves both the full wrap and the partial one.

    Tubes start on the groove floor and run OUTWARD to the original skin: a
    tube that stops short leaves a lip of skin in front of every hole, and one
    that overshoots pokes past the shell and inflates the bounding box.
    """
    ring = [
        (math.cos(2 * math.pi * k / seg), math.sin(2 * math.pi * k / seg))
        for k in range(seg)
    ]

    # The path is the profile at the GROOVE FLOOR, taken from the body's own
    # rounded_rect so the two can never drift. Corner arc centres there are
    # inset by the radius (a corner at half-extent hx with radius r is centred
    # at (hx - r, 0), not (hx, 0)); using the edge midpoint pushes the path
    # outward by r and inflates the bbox by exactly that much.
    hx, hy = W / 2.0 - depth, D / 2.0 - depth
    r = R_VERT - depth
    perim = rounded_rect(hx, hy, r, seg=24, edge_sub=96)
    acc = [0.0]
    for i in range(1, len(perim)):
        ax, ay = perim[i - 1]
        bx, by = perim[i]
        acc.append(acc[-1] + math.hypot(bx - ax, by - ay))
    total = acc[-1]

    def point_at(s):
        lo, hi = 0, len(acc) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if acc[mid] < s:
                lo = mid + 1
            else:
                hi = mid
        px, py = perim[lo]
        nx_, ny_ = perim[(lo + 1) % len(perim)]
        dx, dy = nx_ - px, ny_ - py
        ln = math.hypot(dx, dy) or 1.0
        return px, py, dx / ln, dy / ln

    # Rows are spaced on the SAME pitch as the columns, not stretched to fit.
    #
    # This used to be
    #     rows = clamp(int((z_hi - z_lo) / (pitch * 0.86)))
    #     row_dz = (z_hi - z_lo) / (rows - 1)
    # which distributes `rows` rows evenly across the band whatever that
    # comes to, so the row pitch drifted away from the column pitch. At
    # pitch 0.20 the field came out on a 0.175 cm row pitch, and the pixel
    # diff against Apple's rear diagram came back alternating — 40%, 29%,
    # 41%, 29% down the field — because some bands caught a hole row edge-on
    # and some caught the gap between two of them.
    #
    # On a square lattice the band gets floor(span / pitch) rows, spaced
    # exactly `pitch` apart, with the remainder left as solid metal at the
    # bottom rather than smeared across the whole field.
    span = z_hi - z_lo
    rows = max(1, min(rows_cap, int(span / pitch) + 1))
    row_dz = pitch

    verts, faces = [], []
    placed = 0
    for row in range(rows):
        # Rows run from the TOP of the band down to the bottom, evenly.
        #
        # This used to be
        #     z0 = z_lo + (z_hi - z_lo) / 2.0 - row * row_dz
        # which anchors the first row at the band's MIDPOINT and then walks
        # down, so the upper half of the field was never built: the upper
        # rear field spans z 4.47..8.93 but only 4.47..6.70 got holes, and a
        # pixel diff against Apple's rear diagram showed the perforated band
        # starting at 25% of the height instead of 5%.
        z0 = z_hi - row * row_dz
        s = (pitch / 2.0) if row % 2 else 0.0
        while s < total:
            px, py, tx, ty = point_at(s)
            ff = front_factor(py)
            if ff < 0.15:
                s += pitch
                continue          # outside this field's arc
            rx, ry = -ty, tx                 # outward normal
            base = len(verts)
            for oz in (0.0, depth):
                for ox, oy in ring:
                    verts.append((px + rx * (ox * hole_r) + tx * (oy * hole_r),
                                  py + ry * (ox * hole_r) + ty * (oy * hole_r),
                                  z0 + oz))
            for k in range(seg):
                k2 = (k + 1) % seg
                faces.append((base + k, base + k2,
                              base + seg + k2, base + seg + k))
                faces.append((base + 2 * seg + k2, base + 2 * seg + k,
                              base + 3 * seg + k, base + 3 * seg + k2))
            for k in range(seg):
                k2 = (k + 1) % seg
                faces.append((base + k2, base + k,
                              base + 2 * seg + k, base + 2 * seg + k2))
                faces.append((base + seg + k, base + seg + k2,
                              base + 3 * seg + k2, base + 3 * seg + k))
            placed += 1
            s += pitch

    obj = simple_mesh(name, verts, faces, mats["grille"], smooth=True)
    print("  %s: %d holes in %d rows" % (name, placed, rows))
    return obj


def field_factor(gap_cm):
    """Perimeter mask: 1.0 on the rear and sides, 0.0 within `gap_cm` of the front.

    The front face is where py is most negative, so the mask is a smoothstep on
    how far around from that face a point sits.
    """
    gt = gap_cm / (2.0 * (D / 2.0))

    def f(py):
        t = (py + D / 2.0) / D            # 0 at the front, 1 at the rear
        if t >= 1.0 - gt:
            return 1.0
        if t <= gt:
            return 0.0
        u = (t - gt) / (1.0 - 2.0 * gt)
        return u * u * (3.0 - 2.0 * u)   # smoothstep
    return f


def build_grille_band(mats, body):
    """Both ventilation fields: the base band and the upper rear/side field.

    Neither is a boolean. Both recesses come from the body loft (see
    `grille_inset`), and the hole tubes are laid into them from the groove
    floor outward to the original skin. Booleans on this shape failed three
    ways in a row — tangent cutter, buried cutter, proud cutter — and two of
    those are silent.

    The fields differ only in span, depth and how far around the perimeter
    they reach, which is what `build_grille_field` takes as arguments:

    * base band   — z 0.42..1.62, the whole perimeter, 0.14 cm deep
    * upper field — z 50%..93% of height, rear and sides only, leaving the
      front panel solid silver above the band
    * lower field — z 18%..34% of height, rear and sides only, below the ports
    """
    band = build_grille_field(
        mats, "BottomGrille",
        GRILLE_BAND_Z0 + 0.06, GRILLE_BAND_Z1 - 0.06,
        GRILLE_RECESS, GRILLE_PITCH, GRILLE_HOLE_R,
        front_factor=lambda py: 1.0, seg=8, rows_cap=8)

    upper = build_grille_field(
        mats, "UpperGrille",
        UPPER_Z0 + 0.12, UPPER_Z1 - 0.12,
        UPPER_DEPTH, UPPER_PITCH, UPPER_HOLE_R,
        front_factor=field_factor(UPPER_FRONT_GAP), seg=8, rows_cap=40)

    lower = build_grille_field(
        mats, "LowerRearGrille",
        LOWER_F_Z0 + 0.10, LOWER_F_Z1 - 0.10,
        LOWER_F_DEPTH, UPPER_PITCH, UPPER_HOLE_R,
        front_factor=field_factor(LOWER_F_GAP), seg=8, rows_cap=8)
    return band, upper, lower


def rounded_rect_path(hx, hy, r, steps=720):
    """Sample a rounded rectangle. Corner arc centres are inset by r."""
    pts = []
    corners = ((hx - r, hy - r, 0.00), (-hx + r, hy - r, 0.25),
               (-hx + r, -hy + r, 0.50), (hx - r, -hy + r, 0.75))
    for i in range(steps):
        t = (i / steps) * 4.0
        e = int(t)
        u = t - e
        a, b = corners[e], corners[(e + 1) % 4]
        p0 = (a[0] + r * math.cos(2 * math.pi * a[2]),
              a[1] + r * math.sin(2 * math.pi * a[2]))
        p1 = (b[0] + r * math.cos(2 * math.pi * b[2]),
              b[1] + r * math.sin(2 * math.pi * b[2]))
        pts.append((p0[0] + (p1[0] - p0[0]) * u, p0[1] + (p1[1] - p0[1]) * u))
    return pts


def build_band_panel(mats, perim, z_lo, z_hi, mat, proud=0.0):
    """Closed ring prism wrapping the perimeter between two heights.

    Used as a boolean cutter for the grille groove, so it has to be a real
    watertight solid: sample the path densely and cap nothing (a ring prism is
    already closed if the path is closed). Sampling every 8th point leaves the
    faces so thin that EXACT treats the cutter as degenerate and the boolean
    silently no-ops — the groove stays uncut and the bounding box still
    verifies, so nothing else catches it.

    `proud` offsets the ring radially: negative values push it inboard, which
    is what cuts a recess rather than adding a shell of new geometry.
    """
    ring = list(perim)
    # A ring prism with no top/bottom caps is an open surface, and EXACT
    # silently no-ops on open cutters. Build all four rings — outer bottom,
    # outer top, inner bottom, inner top — and cap the ends so the solid is
    # watertight before handing it to the boolean.
    m = len(ring)
    verts, faces = [], []

    def add_ring(z, offset):
        base = len(verts)
        for px, py in ring:
            n = math.hypot(px, py) or 1.0
            verts.append((px + px / n * offset, py + py / n * offset, z))
        return base

    ob = add_ring(z_lo, proud)      # outer, bottom
    ot = add_ring(z_hi, proud)      # outer, top
    ib = add_ring(z_lo, 0.0)        # inner (on the path), bottom
    it = add_ring(z_hi, 0.0)        # inner, top
    for i in range(m):
        j = (i + 1) % m
        faces.append((ob + i, ob + j, ot + j, ot + i))   # outer wall
        faces.append((ib + j, ib + i, it + i, it + j))   # inner wall
        faces.append((ib + i, ib + j, ob + j, ob + i))   # bottom cap
        faces.append((ot + i, ot + j, it + j, it + i))   # top cap
    return simple_mesh("BandPanel_%.2f" % z_lo, verts, faces, mat, smooth=True)


def add_socket(name, x, z, w, h, y_mouth, mats, depth=0.30, wall=0.05, inward=1.0):
    """A rectangular connector socket: 4 bright metal walls + dark back + tongue.

    Built wall-by-wall rather than as one solid dark box. That is what makes a
    connector read as a real socket in a render — you see the lit inner walls
    and the shadowed back plate, instead of a flat black silhouette. A solid
    box at any lighting reads as a painted-on cutout.

    `y_mouth` is the plane the opening sits on. `inward` is +1 when the socket
    body extends toward +Y (rear panel, which is at +D/2) and -1 when it
    extends toward -Y (front panel, at -D/2). Getting this backwards builds
    the socket outside the enclosure and inflates the bounding box.
    """
    shell, cav = mats["alu"], mats["cavity"]
    # yc is the socket's mid-depth, measured from the mouth plane toward the
    # interior. y_mouth is already set *behind* the skin by the caller, so the
    # body spans y_mouth .. y_mouth + inward*depth and never crosses the skin.
    yc = y_mouth + inward * depth / 2.0
    add_box(name + "_w_top", x, yc, z + h / 2 - wall / 2, w, depth, wall, shell)
    add_box(name + "_w_bot", x, yc, z - h / 2 + wall / 2, w, depth, wall, shell)
    add_box(name + "_w_l", x - w / 2 + wall / 2, yc, z, wall, depth, h - 2 * wall, shell)
    add_box(name + "_w_r", x + w / 2 - wall / 2, yc, z, wall, depth, h - 2 * wall, shell)
    add_box(name + "_back", x, y_mouth + inward * (depth - 0.03), z, w, 0.05, h, cav)
    add_box(name + "_tongue", x, y_mouth + inward * depth * 0.55, z, w * 0.58, 0.09,
            h * 0.34, shell, bevel=0.02)


def add_round_socket(name, x, z, r, y_mouth, mats, depth=0.30, inward=1.0):
    """Same idea for a round jack: bright metal tube, dark back disc, centre pin."""
    shell, cav = mats["alu"], mats["cavity"]
    yc = y_mouth + inward * depth / 2.0
    add_cylinder(name + "_shell", x, yc, z, r, depth, shell, verts=40, axis="Y")
    add_cylinder(name + "_back", x, y_mouth + inward * (depth - 0.04), z, r * 0.88,
                 0.05, cav, verts=40, axis="Y")
    add_cylinder(name + "_pin", x, y_mouth + inward * depth * 0.62, z, r * 0.16,
                 0.14, shell, verts=16, axis="Y")


# ------------------------------------------------------------------- I/O layout
def build_rear_io(mats):
    """Rear bay is a real recess (boolean); the connectors sit inside it."""
    y_face = D / 2.0
    # Port bay geometry, from Apple's rear diagram. The solid band runs
    # 55%..70% down from the top, so its height is 15% of the 9.5 cm chassis
    # (1.43 cm). The earlier bay was 4.1 cm tall — 43% — and 17.4 cm wide, so
    # it covered almost the whole rear panel and swallowed both perforated
    # fields. Its top edge also sat ABOVE the upper field's floor, so the
    # boolean removed that field outright.
    bay_x = 7.60
    bay_z0, bay_z1 = BAY_Z0, BAY_Z1
    # 0.18 cm, not 0.42. A 15.2 x 1.9 cm panel does not have a 4 mm deep
    # pocket in it — that is a slot, and it renders as a black bar. The real
    # bay is a shallow step so the connector collars stand slightly proud.
    bay_depth = 0.18
    zc = (bay_z0 + bay_z1) / 2.0
    body = bpy.data.objects["Body"]

    # The cutter must straddle the skin: its outer face stays OUTSIDE the rear
    # panel (that part is simply discarded) and its inner face reaches exactly
    # bay_depth inside. Overshooting the footprint makes EXACT merge the
    # cutter's outer half into the shell and grow the bbox.
    cut_from_body(body, "RearBay", 0.0, y_face + 0.10 - bay_depth / 2.0, zc,
                  bay_x * 2.0, bay_depth + 0.20, bay_z1 - bay_z0,
                  bevel=0.35, mats=mats)
    # The bay floor is ALUMINIUM, not black.
    #
    # The first pass painted the whole recess Cavity_Black, which was the wrong
    # reading of "the port bay should not look silver": against Apple's rear
    # diagram the band at 55-70% of the height reads 6% / 0% / 9% dark, i.e.
    # solid metal, and painting it black put the model at 74% / 59% / 66% — the
    # bay became a black slot.
    #
    # The bay is a machined step in one piece of aluminium, so its floor AND
    # its walls are aluminium. A boolean difference leaves the walls carrying
    # Cavity_Black (the cutter's material), which is what kept 68 faces dark
    # after the depth came down from 0.42 to 0.18 cm. Repaint the whole recess
    # back to the shell material: the only dark geometry in the band should be
    # the connector mouths, and those are separate objects.
    body_mat = bpy.data.materials["Aluminium_Silver"]
    slot_alu = [i for i, m in enumerate(body.data.materials)
                if m == body_mat]
    alu_slot = slot_alu[0] if slot_alu else 0
    y_lo = y_face - bay_depth - 0.02
    y_hi = y_face - 0.02
    repainted = 0
    for p in body.data.polygons:
        c = p.center
        if (y_lo < c.y < y_hi and abs(c.x) < bay_x + 0.6
                and bay_z0 - 0.10 < c.z < bay_z1 + 0.10
                and p.material_index != alu_slot):
            p.material_index = alu_slot
            repainted += 1
    print("  RearBay: %d faces repainted to aluminium" % repainted)

    # Rear port order, from Apple's own rear hardware diagram
    # (/v/mac-studio/o/images/overview/connectivity/hw_back__*.jpg), read
    # left-to-right as shown in that image:
    #
    #   4x USB-C (USB 3.2 Gen 2, 10 Gb/s) | 10GbE | AC power inlet
    #   | 2x Thunderbolt 5 | HDMI | 3.5 mm headphone | power button
    #
    # The earlier build had four THUNDERBOLT ports grouped on the left and no
    # power button at all. Apple's diagram shows only TWO Thunderbolt 5 ports,
    # and the four leftmost are plain 10 Gb/s USB-C.
    #
    # That diagram is a straight-on REAR view, which in this model is the +Y
    # side, so its left-to-right is the NEGATIVE of our +X. Mirror the x values.
    # The connector mouths sit just outside the bay floor: the floor is at
    # y_face - bay_depth = 9.67, and a USB-C shell stands 0.10 cm proud of
    # the outer skin, so its mouth is at 9.75.
    y_mouth = y_face - 0.10
    # x positions are MODEL space, mirrored from the diagram's visual order.
    # The bay is 15.2 cm wide, so keep everything within +/- 7.4.
    #
    # USB-C and Thunderbolt shells are TALLER THAN WIDE on the real part — the
    # opening is a vertical rounded slot about 0.38 x 0.90 cm, not a wide letter
    # slot. The earlier build had them 0.92 wide x 0.30 high, which reads as a
    # horizontal slot and is wrong in both axes.
    #
    # Spacing is set by verify_ports.py, which fails the build if any two
    # connectors are closer than 0.20 cm. HDMI (1.50 wide) and the 3.5 mm jack
    # (0.52 across) sat 0.14 cm apart at the old positions, which reads as the
    # two openings touching.
    parts = [
        # (name, x, width, height) — USB-C and TB5 are vertical slots
        ("USBC_1", 6.30, 0.38, 0.90),
        ("USBC_2", 5.15, 0.38, 0.90),
        ("USBC_3", 4.00, 0.38, 0.90),
        ("USBC_4", 2.85, 0.38, 0.90),
        ("RJ45", 1.05, 1.45, 1.28),
        ("PowerInlet", -1.25, 1.05, 0.60),
        ("TB5_1", -3.05, 0.38, 0.90),
        ("TB5_2", -4.20, 0.38, 0.90),
        ("HDMI", -5.75, 1.50, 0.46),
    ]
    for name, x, w, h in parts:
        add_socket("Port_" + name, x, zc, w, h, y_mouth, mats, inward=-1.0)
    # 3.5 mm jack at the bay's far end, clear of the HDMI's right edge
    add_round_socket("Port_Headphone", -7.10, zc, 0.26, y_mouth, mats, inward=-1.0)

    # Touch ID power button, at the far end of the bay in Apple's diagram,
    # vertically centred like the rest of the row (it sat above the port line
    # before, hanging outside the bay band).
    pw = add_cylinder("Port_PowerButton", 7.05, y_mouth - 0.06, zc,
                      0.22, 0.10, mats["alu"], verts=32, axis="Y")
    return pw


def build_front_io(mats, body):
    """Front: 2x USB-C + SDXC on the left, 3.5 mm jack on the right.

    Each opening is booleaned into the shell so it reads as a real slot with
    an inner shadow, not a black sticker on the skin. A bright chamfer ring
    around each opening is what actually sells the depth: without a specular
    edge catching light, a recessed hole reads flat in a studio render.

    Positions are measured, not guessed. From Apple's own front hardware
    diagram (apple.com/hk/mac-studio/ -> hw_front__*.jpg, 656x322), the feature
    centres sit at 16.5%, 24.0%, 37.7% and 83.5% of the panel width, read
    left-to-right in that image. The diagram shows the machine from in front,
    which is the -Y side here, so image-left is model +X and each position maps
    to x = W/2 - (pct/100)*W. That puts them at +6.60, +5.12, +2.42 and -6.60.

    The right-hand round feature is the 3.5 mm headphone jack, NOT a status
    light. The earlier build modelled it as an emissive LED at x = -7.60, which
    is both the wrong function and 1.0 cm too far out.
    """
    y_face = -D / 2.0
    zc = 2.55
    slots = [
        # USB-C openings on the real part are vertical rounded slots, roughly
        # 0.36 wide x 0.90 tall — the same shell as the rear Thunderbolt ports.
        # The earlier build used 0.32 x 0.90 for the front (correct) but the
        # rear row was the transposed 0.92 x 0.30, so the two disagreed.
        ("Front_USBC_1", 6.60, 0.36, 0.90),
        ("Front_USBC_2", 5.12, 0.36, 0.90),
        # SD slot spans 31%..44% of the panel width -> x +1.18..+3.74
        ("Front_SDXC", 2.42, 1.30, 0.34),
    ]
    for name, x, w, h in slots:
        # Straddling convention: outer face 0.10cm proud of the skin, inner
        # face 0.50cm in. The bevel is deliberately small — a large bevel on a
        # 0.60cm-deep cutter rounds away the part that overlaps the skin and
        # EXACT then merges the cutter's outer cap into the shell, growing the
        # bbox by the cutter's overhang instead of shrinking it.
        cut_from_body(body, name, x, y_face + 0.20, zc, w + 0.20, 0.60, h + 0.20,
                      bevel=0.06, mats=mats)
        # same flipped-skin problem as the rear bay: the slot's back wall is the
        # original skin turned inward, and it keeps the aluminium material
        paint_recess_black(body, y_face + 0.02, y_face + 0.55,
                           abs(x) + w / 2.0 + 0.12, zc - h / 2.0 - 0.12,
                           zc + h / 2.0 + 0.12)
        # The socket sits behind the skin opening. y_face is the outer skin at
        # -D/2, so "behind the skin" is larger y: inward=+1. (The rear panel
        # is at +D/2, where "behind" is smaller y: inward=-1.)
        add_socket(name, x, zc, w, h, y_face + 0.10, mats, depth=0.34, wall=0.045,
                   inward=1.0)

    # 3.5 mm headphone jack on the right, at 83.5% of the panel width.
    #
    # This was previously an emissive status LED at x = -7.60. Apple's front
    # hardware diagram shows a plain round jack on the right and no light at
    # all — the M5 Max has no front status LED, and the Touch ID button is on
    # the underside, not here. So the cut, the lens and the spill light all
    # go; what stays is a bored round socket with a dark cavity.
    #
    # add_round_socket only builds the tube; the skin still has to be opened
    # for it, otherwise the jack sits buried under the panel.
    jack_x = -6.60
    cut_from_body(body, "Front_Headphone", jack_x, y_face + 0.20, zc,
                  0.66, 0.60, 0.66, bevel=0.08, mats=mats)
    paint_recess_black(body, y_face + 0.02, y_face + 0.55,
                       abs(jack_x) + 0.45, zc - 0.45, zc + 0.45)
    add_round_socket("Front_Headphone", jack_x, zc, 0.26, y_face + 0.10, mats,
                     depth=0.34, inward=1.0)
    return jack_x


def build_bottom_details(mats):
    """Underside: four feet, the Touch ID button, and the round vent intakes.

    The real underside is not a bare plate. Between the four feet sit circular
    ventilation intakes: a round recess going UP into the shell, with a dark
    cavity and a raised lip. They are mouths, not bumps — the shell's underside
    plane is z = FOOT_H (0.2 cm) and everything else stands on the floor, so
    anything modelled as a dome below that plane would hang into the foot gap
    and read as a lump. The model had no intakes at all, which is why the
    bottom looked like a plain slab.
    """
    for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        add_cylinder(
            "Foot_%d" % (i + 1), sx * 7.45, sy * 7.45, FOOT_H / 2.0,
            0.55, FOOT_H, mats["rubber"],
        )

    # Circular ventilation intakes. The lip is a shallow ring standing at the
    # underside plane; the bore is a dark cavity recessed above it.
    for i, (bx, by) in enumerate(((-3.5, -3.5), (3.5, -3.5), (-3.5, 3.5), (3.5, 3.5))):
        # dark cavity floor, set up inside the shell
        add_cylinder("VentCavity_%d" % (i + 1), bx, by, FOOT_H + 0.55,
                     0.62, 0.06, mats["cavity"], verts=40)
        # bore wall: a short tube from the underside plane up to the cavity
        add_cylinder("VentBore_%d" % (i + 1), bx, by, FOOT_H + 0.30,
                     0.66, 0.62, mats["cavity"], verts=40)
        # aluminium lip ring around the mouth, flush with the underside
        add_cylinder("VentLip_%d" % (i + 1), bx, by, FOOT_H + 0.02,
                     0.86, 0.05, mats["alu"], verts=48)

    # Touch ID power button, underside toward the rear-left
    add_cylinder("PowerButton", -5.60, 6.05, FOOT_H + 0.05, 0.56, 0.12, mats["port"])
    add_cylinder(
        "PowerRing", -5.60, 6.05, FOOT_H + 0.115, 0.34, 0.02, mats["alu"], verts=48,
    )


# -------------------------------------------------------------------- lighting
def build_studio(scene):
    # A generated studio environment. At roughness 0.19 the shell is very close
    # to a mirror, and a plain constant world background gives it nothing to
    # reflect — the result reads as matte plastic. A gradient sky plus bright
    # overhead strips is what makes the aluminium read as metal.
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
    ramp.color_ramp.elements[0].position = 0.32
    ramp.color_ramp.elements[0].color = (0.55, 0.57, 0.62, 1.0)   # floor bounce
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.96, 0.97, 1.00, 1.0)   # sky
    mid = ramp.color_ramp.elements.new(0.55)
    mid.color = (0.80, 0.82, 0.86, 1.0)
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (math.radians(90), 0, 0)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], grad.inputs["Vector"])
    nt.links.new(grad.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])

    bpy.ops.mesh.primitive_plane_add(size=200.0, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "Floor"
    floor.data.materials.append(make_mat("Floor", (0.80, 0.80, 0.81), 0.0, 0.45))

    def area(name, loc, rot, size, power):
        bpy.ops.object.light_add(type="AREA", location=loc, rotation=rot)
        o = bpy.context.active_object
        o.name = name
        o.data.size = size
        o.data.energy = power
        o.data.color = (1.0, 1.0, 1.0)
        return o

    # Powers are tuned against the new gradient world, which already supplies
    # most of the ambient. Adding these on top at full strength blows out.
    area("Key", (-26, -30, 34), (math.radians(46), 0, math.radians(-40)), 40, 520)
    # A strong fill from the front-right puts a hot specular band along the top
    # edge, which reads as a raised "lid rim" on an enclosure that is actually a
    # single machined block. Softening it removes the tray illusion.
    area("Fill", (30, -20, 20), (math.radians(66), 0, math.radians(56)), 34, 140)
    area("Rim", (6, 30, 30), (math.radians(-52), 0, math.radians(8)), 30, 260)
    area("Top", (0, 0, 40), (0, 0, 0), 34, 150)
    # grazing light aimed into the rear bay so the connectors are not a
    # featureless black rectangle: a shallow back-side fill skims the panel
    # and puts a specular edge on every connector rim
    area("RearBayFill", (2, 34, 16), (math.radians(74), 0, math.radians(184)), 12, 260)

    # Large white bounce cards. At roughness 0.19 the shell is a mirror, and
    # bare area lights alone give it nothing to reflect — these provide the
    # soft gradient streaks that make brushed aluminium read as metal.
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
VIEWS = [
    ("01_front", "front", 46.0, 6.0, 7.0),
    ("02_side", "side", 62.0, 90.0, 8.0),
    ("03_rear", "rear", 46.0, 186.0, 7.0),
    ("04_hero", "3q", 42.0, 214.0, 12.0),
    ("05_top", "top", 62.0, 200.0, 90.0),
    ("06_bottom", "bottom", 60.0, 20.0, -90.0),
    ("07_front_closeup", "front", 26.0, 0.0, 2.0),
]


def place_camera(name, az, el, dist, target):
    az_r, el_r = math.radians(az), math.radians(el)
    cam_data = bpy.data.cameras.new(name)
    cam_data.lens = 62.0
    cam = bpy.data.objects.new(name, cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = Vector((
        dist * math.cos(el_r) * math.cos(az_r) + target[0],
        dist * math.cos(el_r) * math.sin(az_r) + target[1],
        dist * math.sin(el_r) + target[2],
    ))
    direction = (Vector(target) - cam.location).normalized()
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return cam


# ------------------------------------------------------------------------ main
def evaluated_bbox():
    deps = bpy.context.evaluated_depsgraph_get()
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.name in ("Floor", "BounceL", "BounceR"):
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
    build_rear_io(mats)
    build_front_io(mats, body)
    build_bottom_details(mats)
    build_grille_band(mats, body)
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
    scene.cycles.samples = 48
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1500
    scene.render.resolution_y = 1125
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"

    for name, _, az, el, dist in VIEWS:
        target = (0.0, 0.0, H_TOTAL / 2.0)
        if name == "07_front_closeup":
            target = (-5.0, -D / 2.0, 2.8)
        cam = place_camera("CAM_" + name, az, el, dist, target)
        if name == "07_front_closeup":
            cam.data.lens = 85.0
        scene.camera = cam
        path = os.path.join(OUT_DIR, name + ".png")
        scene.render.filepath = path
        try:
            bpy.ops.render.render(write_still=True)
            print("RENDERED %s" % path)
        except Exception as exc:  # GPU backend unavailable -> CPU retry
            print("GPU_FAIL %s (%s) -> CPU retry" % (name, exc))
            scene.cycles.device = "CPU"
            bpy.ops.render.render(write_still=True)
            print("RENDERED %s" % path)

    print("BUILD_OK")


if __name__ == "__main__":
    main()
