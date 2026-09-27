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
R_VERT = 1.6      # vertical corner radius
# Top/bottom edge fillet. Kept small on purpose: a large fillet on a 9.5cm-tall
# body reads as a tray with a raised rim rather than a solid aluminium block.
# 0.35cm matches the crisp edge break on the real enclosure.
R_HORZ = 0.35     # top/bottom edge fillet radius
ARC_SEG = 8       # segments per rounded corner

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


def cut_from_body(body, name, cx, cy, cz, sx, sy, sz, bevel=0.0, mats=None):
    """Boolean-difference a rounded box out of the shell — a real recess.

    The body MUST already be triangulated (see triangulate_caps): the lofted
    shell's top/bottom caps are large non-planar n-gons, and the EXACT solver
    mis-resolves their winding. Symptom of skipping it: the boolean "succeeds"
    but merges the cutter's outer half into the shell, and the bbox grows by
    the cutter's overhang instead of shrinking.
    """
    triangulate_caps(body)
    cutter = add_box("_cut_" + name, cx, cy, cz, sx, sy, sz,
                     (mats or {}).get("cavity") or bpy.data.materials["Cavity_Black"],
                     bevel=bevel)
    bpy.context.view_layer.objects.active = body
    for o in bpy.context.selected_objects:
        o.select_set(False)
    body.select_set(True)
    mod = body.modifiers.new("Cut_" + name, "BOOLEAN")
    mod.operation, mod.object, mod.solver = "DIFFERENCE", cutter, "EXACT"
    bpy.ops.object.modifier_apply(modifier="Cut_" + name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    return body


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
    """Lofted rounded box: exact 19.7 x 19.7 footprint, 9.5 tall incl. feet."""
    z_lo, z_hi = FOOT_H, H_TOTAL
    levels = []
    steps = 8
    for i in range(steps + 1):                       # bottom fillet
        levels.append(z_lo + R_HORZ * (1.0 - math.cos(math.pi / 2 * i / steps)))
    levels.append(z_lo + (z_hi - z_lo) / 2.0)         # straight band
    for i in range(steps + 1):                       # top fillet
        levels.append(z_hi - R_HORZ * (1.0 - math.cos(math.pi / 2 * i / steps)))

    verts, faces, mats_per_face = [], [], []
    hx, hy = W / 2.0, D / 2.0
    for z in levels:
        d = fillet_inset(z, z_lo, z_hi)
        for px, py in rounded_rect(hx - d, hy - d, R_VERT - d):
            verts.append((px, py, z))

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


# ------------------------------------------------------- perforated bottom plate
def build_grille_plate(mats, pitch=0.30, hole_r=0.085, seg=8):
    """Flat plate with genuine perforations; one 8-quad cell per grid position."""
    z_top = FOOT_H + 0.045
    nx = int(16.4 / pitch)
    ny = nx
    x0, y0 = -nx * pitch / 2.0, -ny * pitch / 2.0
    half = pitch / 2.0

    outer = [  # CCW, corners then edge midpoints -> tiles with its neighbours
        (half, half), (0.0, half), (-half, half), (-half, 0.0),
        (-half, -half), (0.0, -half), (half, -half), (half, 0.0),
    ]
    inner = [
        (hole_r * math.cos(2 * math.pi * k / seg), hole_r * math.sin(2 * math.pi * k / seg))
        for k in range(seg)
    ]
    # remap outer to 8 phases aligned with the inner octagon
    outer = [
        (half, 0.0),
        (half * 0.7071, half * 0.7071), (0.0, half),
        (-half * 0.7071, half * 0.7071), (-half, 0.0),
        (-half * 0.7071, -half * 0.7071), (0.0, -half),
        (half * 0.7071, -half * 0.7071),
    ]

    verts, faces = [], []
    for iy in range(ny):
        for ix in range(nx):
            cx = x0 + (ix + 0.5) * pitch
            cy = y0 + (iy + 0.5) * pitch
            base = len(verts)
            verts.extend((cx + px, cy + py, z_top) for px, py in outer)
            verts.extend((cx + px, cy + py, z_top) for px, py in inner)
            for k in range(seg):
                k2 = (k + 1) % seg
                faces.append((base + k, base + k2, base + seg + k2, base + seg + k))

    obj = simple_mesh("BottomGrille", verts, faces, mats["grille"])
    sol = obj.modifiers.new("Solidify", "SOLIDIFY")
    sol.thickness = 0.10
    sol.offset = -1.0
    return obj


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
    bay_x, bay_z0, bay_z1 = 8.70, 2.20, 6.30
    bay_depth = 0.85
    zc = (bay_z0 + bay_z1) / 2.0
    body = bpy.data.objects["Body"]

    # The cutter must straddle the skin: its outer face stays OUTSIDE the rear
    # panel (that part is simply discarded) and its inner face reaches exactly
    # bay_depth inside. Overshooting the footprint makes EXACT merge the
    # cutter's outer half into the shell and grow the bbox.
    cut_from_body(body, "RearBay", 0.0, y_face + 0.10 - bay_depth / 2.0, zc,
                  bay_x * 2.0, bay_depth + 0.20, bay_z1 - bay_z0,
                  bevel=0.35, mats=mats)

    # every socket mouth sits 0.45cm inside the bay opening, so the whole
    # connector is visibly recessed rather than flush with the panel.
    # The rear panel is at +D/2, so "into the enclosure" is decreasing y.
    y_mouth = y_face - 0.45
    parts = [
        # (name, x, width, height)
        ("PowerInlet", -7.90, 1.05, 0.62),
        ("TB5_1", -5.90, 0.95, 0.30),
        ("TB5_2", -4.00, 0.95, 0.30),
        ("TB5_3", -2.10, 0.95, 0.30),
        ("TB5_4", -0.20, 0.95, 0.30),
        ("USBA_1", 1.80, 1.40, 0.58),
        ("USBA_2", 3.40, 1.40, 0.58),
        ("HDMI", 5.20, 1.50, 0.46),
        ("RJ45", 6.95, 1.45, 1.35),
    ]
    for name, x, w, h in parts:
        add_socket("Port_" + name, x, zc, w, h, y_mouth, mats, inward=-1.0)

    add_round_socket("Port_Headphone", 8.35, zc, 0.30, y_mouth, mats, inward=-1.0)


def build_front_io(mats, body):
    """Front: 2x USB-C + SDXC (M5 Max layout), low on the left; LED at right.

    Each opening is booleaned into the shell so it reads as a real slot with
    an inner shadow, not a black sticker on the skin. A bright chamfer ring
    around each opening is what actually sells the depth: without a specular
    edge catching light, a recessed hole reads flat in a studio render.
    """
    y_face = -D / 2.0
    zc = 2.55
    slots = [
        ("Front_USBC_1", -7.40, 0.32, 0.90),
        ("Front_USBC_2", -6.40, 0.32, 0.90),
        ("Front_SDXC", -4.70, 1.30, 0.34),
    ]
    for name, x, w, h in slots:
        # Straddling convention: outer face 0.10cm proud of the skin, inner
        # face 0.50cm in. The bevel is deliberately small — a large bevel on a
        # 0.60cm-deep cutter rounds away the part that overlaps the skin and
        # EXACT then merges the cutter's outer cap into the shell, growing the
        # bbox by the cutter's overhang instead of shrinking it.
        cut_from_body(body, name, x, y_face + 0.20, zc, w + 0.20, 0.60, h + 0.20,
                      bevel=0.06, mats=mats)
        # The socket sits behind the skin opening. y_face is the outer skin at
        # -D/2, so "behind the skin" is larger y: inward=+1. (The rear panel
        # is at +D/2, where "behind" is smaller y: inward=-1.)
        add_socket(name, x, zc, w, h, y_face + 0.10, mats, depth=0.34, wall=0.045,
                   inward=1.0)

    # status LED: shallow bore plus a real, lit lens
    cut_from_body(body, "Front_LED", 7.60, y_face - 0.10 + 0.30, zc, 0.24, 0.60, 0.24,
                  bevel=0.08, mats=mats)
    led = bpy.data.materials["Status_LED"]
    led_bsdf = next(n for n in led.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    led_bsdf.inputs["Emission Color"].default_value = (0.80, 0.92, 1.0, 1.0)
    led_bsdf.inputs["Emission Strength"].default_value = 6.0
    led_bsdf.inputs["Base Color"].default_value = (0.9, 0.95, 1.0, 1.0)
    # lens sits 0.16cm inside the bore mouth, flush enough to be visible
    lens = add_cylinder("Front_LED", 7.60, y_face + 0.16, zc, 0.085, 0.04, led,
                        verts=24, axis="Y")
    # small point light so the LED actually spills onto the surrounding panel
    ld = bpy.data.lights.new("LEDglow", "POINT")
    ld.energy, ld.color, ld.shadow_soft_size = 2.5, (0.75, 0.88, 1.0), 0.12
    glow = bpy.data.objects.new("LEDglow", ld)
    glow.location = (7.60, y_face - 0.10, zc)
    bpy.context.collection.objects.link(glow)
    return lens


def build_bottom_details(mats):
    """Four rubber feet + the Touch ID power button on the underside."""
    for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        add_cylinder(
            "Foot_%d" % (i + 1), sx * 7.45, sy * 7.45, FOOT_H / 2.0,
            0.55, FOOT_H, mats["rubber"],
        )
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
    build_grille_plate(mats)
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
