"""Check that the ventilation fields are actually OPEN, not merely present.

A perforated field can exist in the scene and still be invisible: the
perforation tubes are cut to the field's full depth, but if the shell's
recess is shallower than the tubes then the tubes end up buried inside solid
aluminium. The first pass had exactly that on both sides - the loft
smoothstepped the recess across the whole perimeter, the side faces landed at
0.5 of full depth, and a grid over the right face hit UpperGrille zero times
while the grille object itself carried 23,936 vertices.

What is measured
----------------
The OPEN AREA FRACTION of each perforated region, rayed from outside the
chassis and compared against the fraction the spec's lattice predicts. This
settles both halves of the question at once, without needing to know where
the holes sit:

  * a field whose tubes are buried rays ~0% open  (the failure above)
  * a field with no bridges left rays ~100% open  (a sieve)
  * a correct field rays ~the design duty cycle, so the holes are open AND
    the metal between them is still solid

Why not a coarse grid, and why not reconstructed hole centres
------------------------------------------------------------
Both were tried first and both failed in a way that looked like a real defect:

  * a uniform 21x21 grid over the face put one sample per ~46 holes, scored
    2.7% against a 20% threshold, and reported VENT_FAIL on a healthy model.
  * rebuilding the hole centres from build_grille_field()'s arc-length walk
    produced a lattice that is off by about half a pitch: hole-centre rays
    passed at 32.6% and "bridge" midpoints leaked at 32.8%. Two tests that
    disagree by 0.2% are not measuring holes and bridges, they are both
    measuring the duty cycle at the wrong phase.

A dense grid spaced well under one hole diameter does not care about phase,
so that is what this uses. It is also self-checking: if the sample spacing
ever got coarse enough to miss the lattice, the measured fraction would drift
away from the predicted one and the comparison would fail.

usage:  blender --background --python verify_ventilation.py
"""
import math
import os
import sys

import bpy
from mathutils import Vector

_HERE = os.path.dirname(os.path.abspath(__file__))
BLEND = os.path.join(_HERE, "mac_studio.blend")

if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import mac_studio_spec as S  # noqa: E402


def fillet_inset(z, z_lo, z_hi):
    """The body's bottom/top fillet, reimplemented here on purpose.

    The curve is a CIRCLE, not a cosine: the inset is R - sqrt(R^2 - t^2),
    which is 0 where the shell is straight and R at the very bottom edge. A
    cosine here looks plausible and is wrong - it is non-zero at z = z_lo (so
    the "straight" middle of the shell got pinched) and it does not reach R at
    the edge. A first version of this file used the cosine and the band probe
    aimed at a surface that was up to 3.2 mm off, reporting 0% open on a band
    that is in fact perforated.
    """
    r = S.R_HORZ
    if z <= z_lo + r:
        t = (z_lo + r) - z
        return r - math.sqrt(max(0.0, r * r - t * t))
    if z >= z_hi - r:
        t = z - (z_hi - r)
        return r - math.sqrt(max(0.0, r * r - t * t))
    return 0.0

# The convention is +Y = FRONT (2x USB-C, SDXC, status LED) and -Y = REAR (the
# I/O row, the exhaust field, the power button).
#
# This table had them the other way round, and so did the ray list: the entry
# called "rear  +Y" fired its rays along -Y, straight into the solid FRONT
# panel. It reported 0/441 and read as "the rear field is no longer
# perforated" - the alarm that surfaced this. Nothing about the machine had
# changed; the probe was aimed at the wrong face. A verifier with the axes
# backwards is worse than no verifier, because it converts a real green into a
# false red and sends you to rebuild geometry that is already correct.
FRONT = "front +Y"
REAR = "rear  -Y"
RIGHT = "right +X"
LEFT = "left  -X"

# Ray-start distance in centimetres: far enough out that nothing is hit before
# the skin.
STANDOFF = 40.0

# Sample spacing in centimetres. The rear field's holes are 0.142 cm across, so
# 0.05 cm puts ~3 samples across every hole - fine enough that the measured
# fraction is the true fraction, and coarse enough to stay quick.
STEP = 0.05

# The shell. A ray landing here has hit aluminium, so it counts as closed.
SKIN = ("Body", "BaseGrille", "RearField", "BottomCover", "Frame_floor",
        "Base_floor")

# How far the measured open fraction may sit from the designed one.
TOLERANCE = 0.06

fails = 0


def hide_studio():
    for n in ("BounceL", "BounceR", "Floor"):
        o = bpy.data.objects.get(n)
        if o:
            o.hide_viewport = True


def crosses_skin(sc, dg, origin_fn, u, v, direction, reach, standoff):
    """Is the skin at (u, v) open? A SEGMENT test, not a ray_cast.

    Three ways to get this wrong, all of which look like a working model:

    1. A bare ray_cast answers "what is the first thing anywhere on this
       infinite line". Fired at an open hole it flies through the rear skin,
       crosses the chassis and reports the FRONT wall, and a check reading
       that as "solid" measures a 19 cm wall it was never aimed at.
    2. Bounding that ray by a reach and starting the walk out at a standoff is
       no better: the first hit is `standoff` away, so everything exceeds the
       reach and every sample reads open - 100% on the field, on the band AND
       on the faces that must be solid.
    3. Making the standoff larger than the span tests the wrong surface. The
       band check stood off 1 cm from the groove floor to find the shell, so
       the ray met the un-perforated OUTER skin a full centimetre away and
       scored the band 0% open even where the holes are correct. The standoff
       has to be small enough that the first thing met is the surface the
       caller aimed at.

    So the standoff must be smaller than the reach, and small in absolute
    terms - a fraction of a millimetre is enough to clear float noise while
    still starting on the surface being measured. Callers pass the surface
    they want probed; a wide reach is for looking THROUGH an opening into the
    cavity, not for finding the surface.
    """
    if standoff >= reach:
        return "STANDOFF_TOO_BIG"
    org = origin_fn(u, v) - direction * standoff
    limit = reach + standoff
    hit, loc, _nr, _idx, obj, _mtx = sc.ray_cast(dg, org, direction)
    if not hit:
        return None
    if (loc - org).length > limit:
        return None
    return obj.name


def open_fraction(sc, dg, origin_fn, u_range, v_range, direction, reach,
                  standoff=1.0):
    """Share of sampled points where the skin is open.

    `origin_fn` returns the point on the face's own plane; the ray starts
    `standoff` outside it and the measured span is `reach` inside it.
    """
    total = 0
    opened = 0
    u0, u1 = u_range
    v0, v1 = v_range
    nu = max(2, int((u1 - u0) / STEP) + 1)
    nv = max(2, int((v1 - v0) / STEP) + 1)
    for iu in range(nu):
        u = u0 + (u1 - u0) * iu / (nu - 1)
        for iv in range(nv):
            v = v0 + (v1 - v0) * iv / (nv - 1)
            total += 1
            if crosses_skin(sc, dg, origin_fn, u, v, direction, reach,
                            standoff) is None:
                opened += 1
    return opened, total


def report(label, opened, total, expect, note=""):
    global fails
    share = opened / max(1, total)
    ok = abs(share - expect) <= TOLERANCE
    fails += 0 if ok else 1
    print("  %-4s %-16s %6d/%6d open (%5.1f%%, design %4.1f%%) %s"
          % ("OK" if ok else "FAIL", label, opened, total, share * 100,
             expect * 100, note))
    return share


def main():
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    hide_studio()
    dg = bpy.context.evaluated_depsgraph_get()
    sc = bpy.context.scene

    field_duty = math.pi * S.UPPER_HOLE_R ** 2 \
        / (S.UPPER_PITCH_X * S.UPPER_PITCH_Z)
    # the base band's holes are obround, so the area is (pi/4) of the box
    band_duty = (math.pi / 4 * S.GRILLE_HOLE_RX * S.GRILLE_HOLE_RZ) \
        / (S.GRILLE_PITCH_X * S.GRILLE_PITCH_Z)

    print("ventilation check on %s" % os.path.basename(BLEND))
    print("  rear field: %.2f x %.2f mm pitch, %.2f mm holes -> %.1f%% open"
          % (S.UPPER_PITCH_X * 10, S.UPPER_PITCH_Z * 10, S.UPPER_HOLE_R * 20,
             field_duty * 100))
    print("  base band : %.2f x %.2f mm pitch, %.2f x %.2f mm obrounds -> %.1f%% open"
          % (S.GRILLE_PITCH_X * 10, S.GRILLE_PITCH_Z * 10,
             S.GRILLE_HOLE_RX * 20, S.GRILLE_HOLE_RZ * 20, band_duty * 100))
    print("  sampling at %.2f mm, which is %.1fx finer than one hole diameter"
          % (STEP * 10, S.UPPER_HOLE_R * 20 / (STEP * 10)))

    # How deep the probe looks, in centimetres. It must clear the recessed
    # floor and whatever sits just behind the skin, but stop far short of the
    # far wall, or the machine's own opposite panel answers the question. The
    # deepest thing just behind a perforated panel is interior, so 2 cm is
    # generous - and 10x too short to reach the other side of a 19.7 cm
    # chassis.
    # How deep the probe looks, in centimetres. It has to clear the wall
    # behind the opening - the shell is WALL thick, plus the recess the hole
    # sits in - so a clear hole is answered by the cavity. It must NOT reach
    # the far wall, or the machine's own opposite panel answers the question.
    REACH = S.WALL + 0.05             # through the recess and the wall below it
    # The rays start this far OUTSIDE the face plane they are aimed at. It has
    # to be much smaller than the reach: a standoff of a centimetre makes the
    # first thing met the un-perforated outer skin rather than the surface
    # under test, which is how this file came to report the base band 0% open
    # on a band whose holes are geometrically correct.
    STANDOFF_CM = 0.002

    # ---- the rear field, the one face Apple perforates broadly -------------
    # Aimed at the RECESSED surface, which is where the field's outer face
    # actually is. grille_inset() steps the skin in by UPPER_DEPTH across the
    # whole field, so there is no material at the nominal -D/2 plane there at
    # all - a ray aimed at it starts in empty space and reads 0% open.
    # Verified directly: at a bridge between holes, the outermost hit on the
    # whole field is Body at -9.775, not -9.85.
    y_rear = -(S.D / 2.0 - S.UPPER_DEPTH)
    hx = S.UPPER_HALF_X
    z_lo = S.UPPER_Z0 + 0.10
    z_hi = S.UPPER_Z1 - 0.10
    opened, total = open_fraction(
        sc, dg,
        lambda x, z: Vector((x, y_rear, z)),
        (-hx, hx), (z_lo, z_hi), Vector((0, 1, 0)), REACH, STANDOFF_CM)
    report("rear field", opened, total, field_duty,
           "buried if 0%, a sieve if 100%")

    # ---- the wrap-around base band, where it crosses each face -------------
    # Sampled as a 2-D patch, not a single z line. The band's holes are obround
    # and only 0.53 mm tall on a 0.91 mm row pitch, so a 1-D sweep at one z
    # can pass between every row and read 0% open on a band that is in fact
    # perforated - which is what the first version of this check reported for
    # all four faces. The patch spans the band's own height, so the measured
    # fraction is the band's area fraction and can be compared to its duty
    # cycle.
    #
    # The band lives INSIDE the body's bottom fillet (a 3.8 mm quarter-round
    # from z = 2.0 to 5.8 mm), so the surface is not at +/-D/2 there - it is
    # up to 3.8 mm further in. Aiming at the nominal +/-D/2 plane measures
    # empty space 3.8 mm in front of the panel and reports 0% open no matter
    # what the geometry says. So each face's own surface offset is computed
    # from the same fillet the loft used.
    # The band is NOT at the spec's GRILLE_BAND_Z0..Z1.
    #
    # A hole cannot be drilled into the bottom fillet - the surface turns away
    # from vertical there - so the builder puts the band on the wall ABOVE
    # it, at FOOT_H + R_HORZ, and says in a comment that this disagrees with
    # the photograph (the spec's 0.00..0.744 is where the band really is).
    #
    # This gate was measuring the spec range anyway, so 11 of its 14 z
    # samples sat on solid metal by design and all four band rows read 0.0%
    # open - reporting FAIL into exit 0, which is how it stayed invisible.
    #
    # The range now comes from S.BAND_Z0/BAND_Z1, the same constants the
    # builder uses. That is the actual fix: the two files had separate
    # arithmetic for the same quantity, and a third copy here would have been
    # a fourth thing to forget to update.
    z_lo = S.BAND_Z0 + 0.04
    z_hi = S.BAND_Z1 - 0.04
    hxu = 8.0
    BODY_Z0, BODY_Z1 = S.FOOT_H, S.H_TOTAL
    # The band lives INSIDE the body's bottom fillet, so the surface is not
    # at +/-D/2 there. And the loft applies the fillet AND the groove recess
    # as separate insets, so the real skin is at
    #     (W/2 - fillet(z) - GRILLE_RECESS)
    # for the band, not (W/2 - fillet(z)).
    #
    # Getting that wrong put the probe up to 1.3 mm IN FRONT of the panel -
    # measuring empty air - which reported 0% open no matter what the geometry
    # said. This was found by printing, for each sampled z, the y the probe
    # aimed at next to the y the body actually has: they disagreed by the
    # recess depth at every height.
    #
    # Rather than recompute a third version of the surface, take the body's
    # own profile at each z and stand off from THAT. The probe then cannot
    # drift away from the geometry it is measuring.
    def surface_y(z, axis):
        """Where the shell's OUTER skin is on `axis` at height z, from the mesh.

        The probe must travel ALONG the axis it is measuring: a ray fired
        along +Y finds the rear panel's y, and one fired along +X finds a side
        panel's x. Firing along +X to measure a y returns the entry point of
        the LEFT panel instead, and every sample then stands off from a
        nonsense position.

        The returned value is the OUTER skin, not the recessed floor: the
        holes open at the skin, and the groove is only `depth` further in.
        Aiming at the floor measures the bottom of the recess, which the
        tubes sit on top of.
        """
        if axis == "y":
            org, d = Vector((0.0, -40.0, z)), Vector((0, 1, 0))
        else:
            org, d = Vector((-40.0, 0.0, z)), Vector((1, 0, 0))
        hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, org, d)
        if not hit:
            return (S.D / 2.0 if axis == "y" else S.W / 2.0)
        # step back out to the outer surface: keep walking until we leave
        # this object, so the value is the skin and not the groove floor
        prev = loc
        p = loc
        for _ in range(12):
            hit2, loc2, _a, _b, ob2, _c = sc.ray_cast(dg, p - d * 0.002, d)
            if not hit2 or ob2.name != ob.name:
                break
            prev = loc2
            p = loc2
        return abs(prev.y) if axis == "y" else abs(prev.x)

    sides = [
        (REAR,  Vector((0, 1, 0)), "y",
         lambda u, v: Vector((u, -surface_y(v, "y"), v))),
        (FRONT, Vector((0, -1, 0)), "y",
         lambda u, v: Vector((u, surface_y(v, "y"), v))),
        (RIGHT, Vector((-1, 0, 0)), "x",
         lambda u, v: Vector((surface_y(v, "x"), u, v))),
        (LEFT,  Vector((1, 0, 0)), "x",
         lambda u, v: Vector((-surface_y(v, "x"), u, v))),
    ]
    for label, direction, _axis, origin_fn in sides:
        opened, total = open_fraction(sc, dg, origin_fn,
                                      (-hxu, hxu), (z_lo, z_hi),
                                      direction, REACH, STANDOFF_CM)
        report("band %s" % label.split()[0], opened, total, band_duty)

    # ---- faces Apple leaves plain must be fully solid ----------------------
    # The upper front panel and both upper side panels, above the band and
    # below the rear field's own band.
    z_plain = (S.GRILLE_BAND_Z1 + S.UPPER_Z0) / 2.0
    plains = [
        (FRONT, Vector((0, -1, 0)),
         lambda u, v: Vector((u, S.D / 2.0, v))),
        (RIGHT, Vector((-1, 0, 0)),
         lambda u, v: Vector((S.W / 2.0, u, v))),
        (LEFT,  Vector((1, 0, 0)),
         lambda u, v: Vector((-S.W / 2.0, u, v))),
    ]
    for label, direction, origin_fn in plains:
        opened, total = open_fraction(sc, dg, origin_fn,
                                      (-hxu, hxu), (z_plain, z_plain),
                                      direction, REACH, STANDOFF_CM)
        report("%s solid" % label.split()[0], opened, total, 0.0,
               "must be 0")

    print("\n%s (%d failures)"
          % ("VENT_OK" if not fails else "VENT_FAIL", fails))
    # 0/1, not the count: the wrapper at the bottom of this file forwards
    # main()'s return value straight to sys.exit, and a count is a valid
    # non-zero status but reads as "failed 3 ways" nowhere except here.
    return 0 if not fails else 1




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
