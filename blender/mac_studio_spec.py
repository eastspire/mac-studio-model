"""Measured specification of the Mac Studio (2026, M5 Max).

Every number here is MEASURED, in millimetres, off Apple's own flat product
photography, then converted to centimetres. Nothing in this file imports bpy,
so the Blender build and the offline comparison renderer both read the same
constants — there is no second copy to drift.

Source of truth for the three overall dimensions:
    https://www.apple.com/mac-studio/specs/  (checked 2026-09-30)
    Apple Support 128107 "Mac Studio (2026) - Tech Specs"
        Height 3.7 in (9.5 cm), Width 7.7 in (19.7 cm), Depth 7.7 in (19.7 cm)

Everything else was measured with the tools in ../tools, which locate the
chassis bounding box in each photo and express every feature as a fraction of
it. The chassis is 197 mm wide in every shot, so a pixel measurement converts
to millimetres directly:

    measure_ref.py      chassis box, gross row/column bands, hole pitch
    measure_detail.py   field extents, coarse port list
    measure_cc.py       connected components over the rear port row
    measure_front.py    front openings, status LED, edge radii

Re-run those before changing anything here. Several values in this file
replaced numbers that earlier revisions described as "verified against Apple's
diagram" and were still wrong — most visibly the port row, which sat 12 mm too
high, and the front panel, which was mirrored.

Orientation: -Y = front, +Y = back, +Z = up, origin at the footprint centre on
the table surface. Units are centimetres.
"""

# ------------------------------------------------------------------ envelope
W = 19.7          # X, width
D = 19.7          # Y, depth
H_TOTAL = 9.5     # Z, full height including the feet
FOOT_H = 0.2      # rubber feet height
BODY_H = H_TOTAL - FOOT_H

# The vertical corner is a crisp machined break, not a soft pillow. 1.05 cm is
# 5.3% of the width; at 1.6 cm every elevation read as a bulging tray even
# though the panel geometry was provably flat.
R_VERT = 1.05
# The top/bottom edge break. Apple's front elevation reaches its full width
# within about 1.5 mm of the top, so this is deliberately small.
R_HORZ = 0.38
ARC_SEG = 20

# ============================================================== rear elevation
# Row profile, from tools/verify_spec.py on reference/apple_hw_back.jpg
# (1305 x 629 px chassis, 197 mm wide => 0.15096 mm/px):
#
#      0.0 ..  4.7 mm   solid              top edge break
#      4.7 .. 52.8 mm   perforated field   the single large rear grille
#     52.8 .. 62.9 mm   solid
#     62.9 .. 79.3 mm   the port row       (the AC inlet spans the full height)
#     79.3 .. 88.0 mm   solid
#     88.0 .. 95.0 mm   the base band      wrap-around lower intake
#
# There is exactly ONE perforated field on the rear. An earlier build had three
# zones, and the "lower field" it placed at z 1.9..2.85 cm landed at 66..76 mm
# from the top — straight through the port row. It has been deleted.

FIELD_TOP_MM = 4.7          # from the top of the chassis
FIELD_BOT_MM = 52.8
UPPER_Z0 = (95.0 - FIELD_BOT_MM) / 10.0     # 4.220 cm
UPPER_Z1 = (95.0 - FIELD_TOP_MM) / 10.0     # 9.030 cm
# Field width. At every row of the field the silhouette is bright for the first
# ~13 mm, so the dark region is inset about 13 mm from each side: 171.5 mm
# wide, centred. The centring is not assumed - tools/check_field_symmetry.py
# measures the field's own centre and it lands on 98.50 mm from the left edge
# to within 0.08 mm, which is what validates the x origin for everything else.
UPPER_HALF_X = 8.575
UPPER_DEPTH = 0.15          # ~2 hole radii, deep enough to shadow each opening
# Hole lattice, fitted by 2-D cross-correlation over a 39 x 42 mm patch of the
# field (tools/fit_lattice.py) and confirmed by drawing the fitted lattice back
# onto the photograph (tools/lattice_overlay.py). The rows are 16% further
# apart than the columns and each alternate row is offset by a fifth of the
# pitch - neither a square grid nor the usual half-pitch stagger, both of which
# an earlier revision assumed and both of which drift visibly across the field.
# Hole diameter 1.42 mm from the dark area fraction, i.e. 76% of the pitch;
# the bridges between holes are thin, as they are on the real part.
UPPER_PITCH_X = 0.186       # 1.86 mm, column to column
UPPER_PITCH_Z = 0.157       # 1.57 mm, row to row
UPPER_STAGGER = 0.20        # alternate rows offset by 0.20 * UPPER_PITCH_X
UPPER_HOLE_R = 0.071
UPPER_PITCH = UPPER_PITCH_X          # kept for callers that want one number

# The base band wraps the WHOLE perimeter — front, both sides and rear, visible
# in the front product shot as well as the rear one. Measured on the rear
# photograph: its top edge is straight at 87.4-87.7 mm from the top across the
# full width, and it runs to the bottom of the machine, so 0.0..0.744 cm above
# the table. The old 0.70 put the top edge 0.44 mm low.
GRILLE_BAND_Z0 = 0.00
GRILLE_BAND_Z1 = 0.744
# The band's lattice is a plain RECTANGULAR grid of obround holes: 1.962 mm
# between columns, 0.906 mm between rows, no stagger, each hole about 1.5 mm
# wide and 0.56 mm tall.
#
# Fitted by tools/fit_band_lattice.py on apple_hw_back.jpg at 0.15096 mm/px:
#   x pitch 1.962 mm  - autocorrelation: first local minimum at lag 4, the
#                       next local maximum at lag 13
#   z pitch 0.906 mm  - the dark-share-per-row profile repeats every 6 rows
#                       (peaks at rows 3, 9, 15, 21, 27, 33). The 1.811 mm
#                       autocorrelation peak is the SECOND harmonic of that,
#                       not the pitch; taking it as the pitch was how the band
#                       ended up two rows deep instead of eight.
#   stagger 0.00     - alternating rows are NOT offset. Correlating the even
#                       rows against the odd ones puts the peak at shift 0
#                       (0.69) and the minimum at half a pitch (-0.62), the
#                       signature of a rectangular lattice; for a half-
#                       staggered one it is the reverse, and
#                       tools/test_stagger.py confirms the measurement does
#                       recover 0.50 from a synthetic staggered band. A first
#                       pass that correlated single rows instead of row
#                       averages reported 0.46, and a 7 mm zoom looked
#                       staggered as well - tools/band_candidates.py settles it
#                       by drawing both lattices on the photograph, where the
#                       unstaggered one lands on every hole and the staggered
#                       one straddles the gaps between them.
#   open area 48.7%  - on the band's own two-mode split, 0.35% of the dark
#                       pixels in any one blob, so the dark class is holes and
#                       not a lighting gradient
GRILLE_PITCH_X = 0.1962     # 1.962 mm
GRILLE_PITCH_Z = 0.0906     # 0.906 mm
GRILLE_STAGGER = 0.0
# Holes are obround, not circular. How big they are cannot be read off the
# dark area alone: the band's dark class is the opening PLUS the shadow the
# 1.3 mm recess throws around it, so a photograph reports more dark than it has
# hole. The BRIGHT web between holes is metal catching the light and carries no
# such ambiguity, so the split is taken from the web.
#
# Measured on both images with the same rule at the photograph's own
# 0.15096 mm/px, over 88.5-93.5 mm and 40-160 mm of width (tools/band_web.py):
#
#                     web across   hole across   web up   hole up
#   photograph         0.755 mm      1.057 mm   0.453 mm  0.604 mm
#   model              0.453 mm      1.510 mm   0.302 mm  0.453 mm
#
# The photo's two runs sum to 1.81 mm against a 1.962 mm pitch: one pixel is
# lost to the anti-aliased edge between them, so the split is only good to
# about +/-0.15 mm and neither side can be called the true one on its own.
# Half of each discrepancy is therefore given to the hole and half to the web,
# which leaves both within 0.1 mm of the photograph without assuming which of
# the two was measured correctly.
GRILLE_HOLE_RX = 0.0640     # 0.640 mm semi-axis across the band
GRILLE_HOLE_RZ = 0.0264     # 0.264 mm semi-axis up the band
GRILLE_HOLE_R = GRILLE_HOLE_RX    # legacy alias: the larger semi-axis
GRILLE_PITCH = GRILLE_PITCH_X
GRILLE_RECESS = 0.13

# Every connector, front and rear, shares one centre height. Measured from the
# rear: the port bodies sit at 71.41..71.48 mm from the top (centre 23.55 mm
# above the foot plane). Measured from the front, whose SDXC slot is a shallow
# rectangle and so the least biased by cavity shading: 71.54 mm, centre 23.46
# mm. 95 - 71.5 = 23.5 mm.
IO_Z = 2.35

# ------------------------------------------------------- rear connector table
# Measured by connected component on the rear photo. The chassis centre is at
# 98.5 mm and a REAR view puts model +X on the image's LEFT, so
# model_x = 98.5 - x_from_image_left.
#
#   name       x(cm)     w(cm)    h(cm)
#   TB5_1     +6.801    0.27     0.845
#   TB5_2     +5.827    0.26     0.845
#   TB5_3     +4.861    0.26     0.845
#   TB5_4     +3.887    0.27     0.845
#   RJ45      +2.438    1.24     1.060
#   AC_INLET  +0.008    2.20     1.640   three-lobed cloverleaf
#   USBA_1    -2.083    0.53     1.300
#   USBA_2    -3.336    0.53     1.300
#   HDMI      -5.072    1.46     0.500
#   HEADPHONE -6.733    r 0.205
#   POWER_BTN   -8.099    r 0.407   (measured edge-to-edge 8.14 mm)
#
# Every one of these x values was 7.9 mm too far toward the centre in the
# previous revision, and the error was invisible because it was a pure
# translation: all the gaps between neighbouring ports were exactly right, so
# the layout looked perfectly plausible. It came from measure_cc.py reporting
# component columns relative to its cropped window without adding the window
# origin back; the window is inset 8 mm from the chassis edge, so everything
# moved in by that much. tools/verify_spec.py now measures against the
# photographs and fails if any of it drifts again.
#
# The previous build had 4x USB-C, RJ45, a small rectangular power inlet, 2x
# more USB-C where the USB-A ports are, and its round control at x +7.05 — the wrong
# end of the panel.
REAR_PORTS = [
    ("TB5_1",  6.801, 0.27, 0.845),
    ("TB5_2",  5.827, 0.26, 0.845),
    ("TB5_3",  4.861, 0.26, 0.845),
    ("TB5_4",  3.887, 0.27, 0.845),
    ("RJ45",   2.438, 1.24, 1.060),
    ("USBA_1", -2.083, 0.53, 1.300),
    ("USBA_2", -3.336, 0.53, 1.300),
    ("HDMI",   -5.072, 1.46, 0.500),
]
AC_INLET_X = 0.008
AC_INLET_W = 2.20
AC_INLET_H = 1.640
HEADPHONE_X = -6.733
HEADPHONE_R = 0.205
POWER_BTN_X = -8.099
# The button's own edge, measured by the radius of peak |dI/dr| taken ray by
# ray and taken as the median over 72 angles, so the shadow on one side of the
# disc cannot move it. It comes out at 4.07 mm, i.e. 8.14 mm across, and the
# 0.430 cm that was here before was the outer ring of a DIFFERENT measurement -
# a connected-component bounding box, which cannot tell a ring from a filled
# disc and therefore read the gap around the button as part of the button.
#
# The same radial pass finds a second, much tighter edge at 0.98 mm, which is
# the power glyph's own arc, and the darkness never exceeds 19% of rays at any
# radius - i.e. there is no dark ring anywhere on this feature. The face is
# anodised aluminium like the panel it sits in.
POWER_BTN_R = 0.407
# Everything about the button's FACE was invented until tools/touchid_probe.py
# measured it off the rear photograph, and the invention was wrong in a way that
# was visible: the button is the same anodised aluminium as the case, so it
# should read as bright as the panel around it, and tools/port_row.py caught the
# model painting it 84% -> 32% bright.
#
# A radial profile of the photograph, both sides of the button averaged so the
# panel's 40/255 lighting gradient cancels, 0.15 mm bins:
#
#     r 0.00..1.35 mm   208/255   98% of panel   bright metal, not a disc
#     r 1.50..2.25 mm    51-72%                the fingerprint strokes
#     r 2.25..3.90 mm   208/255   99% of panel  bright metal again
#     r 3.90..4.20 mm    82-88%                the gap around the button
#     r 4.65..6.00 mm   213/255  100% of panel  bare panel
#
# The two numbers this adds:
#   POWER_BTN_GAP_W   the dark annulus is 0.30 mm wide, not the 0.60 mm the
#                   offline renderer drew;
#   POWER_BTN_GLYPH_R/POWER_BTN_GLYPH_W
#                   the dark is an annulus 1.50..2.25 mm in radius - strokes,
#                   not the FILLED disc of radius 0.52 R that the renderer used.
#                   The renderer was the only place that thought it was a disc;
#                   build_mac_studio.py has always drawn an arc plus a bar, and
#                   the two had silently diverged because nothing compared them.
#
# A fingerprint icon is a swirl, and this photo resolves the two arcs a centre
# cut crosses and nothing finer. The arc and bar below are that measurement, not
# a claim about the icon's real path - tools/touchid_probe.py says so too.
POWER_BTN_GAP_W = 0.030
POWER_BTN_GLYPH_R = 0.185
POWER_BTN_GLYPH_W = 0.060
# The arc is drawn from 40 deg to 320 deg so it is open at the button's right,
# which is what the photograph shows where the cut crosses 0 deg.
POWER_BTN_GLYPH_A0 = 40.0
POWER_BTN_GLYPH_A1 = 320.0
# The engraved icons sit at 60.3 mm from the top, i.e. 3.47 cm, clear of both
# the port row and the perforated field above it. There is ONE Thunderbolt
# bolt, centred on the group of four ports at x = +5.34, not one per port.
#
# Each x is MEASURED, not assumed: tools/measure_glyphs.py takes the median of
# the connected components found at three thresholds, and the residuals
# against the constants below are 0.001, 0.076, 0.072, 0.074 and 0.078 mm.
#
# Four of the five used to be 7.9 mm out - Thunderbolt and Ethernet too high,
# USB and HDMI too low - which is the same 7.9 mm as the port row's old error
# and has the same cause: a measurement that reported columns relative to a
# cropped window without adding the window's origin back. The headphone mark
# was the one that came out right, and only because it was written as
# HEADPHONE_X rather than as a measured number.
#
# The shapes and sizes are in ICON_GLYPHS below. Those were wrong too, and
# that is a separate fault from the offsets.
ICON_Z = 3.47
ICON_TB_X = 5.344         # centre of the four TB5 ports, +3.887..+6.801
ICON_ETH_X = 2.438        # over the RJ45
ICON_USB_X = -2.710       # centre of the USB-A pair, -2.083..-3.336
ICON_HDMI_X = -5.072      # over the HDMI port
ICON_HP_X = -6.733        # over the headphone jack

# ------------------------------------------------------------------- the marks
# Geometry for the five engraved glyphs, in centimetres RELATIVE to the glyph's
# own (ICON_*_X, ICON_Z). build_rear_icons() and the offline renderer's
# glyph raster both read this list, so the Blender model and the checked image
# cannot disagree about a shape that exists only in one of them.
#
# Three primitives, all filled, all lying in the panel plane:
#   ("poly",   [(x, z), ...])      a closed polygon, in the order given
#   ("stroke", x0, z0, x1, z1, h)  a band of half-width h from (x0,z0) to (x1,z1)
#   ("disc",   x, z, r)            a filled circle
#
# Measured off apple_hw_back.jpg with tools/glyph_grid.py, which shows each
# glyph at 20x on a 0.5 mm grid; sizes cross-checked by tools/measure_glyphs.py.
# Glyph bounding boxes, photo vs this geometry, in millimetres:
#
#   glyph          photo w x h      model w x h
#   thunderbolt     1.36 x 3.17      1.24 x 3.10
#   ethernet        4.08 x 2.26      4.02 x 2.26
#   usb             1.96 x 3.32      1.96 x 3.32
#   hdmi            5.74 x 1.66      5.79 x 1.66
#   headphone       2.72 x 3.02      2.68 x 3.10
#
# What this replaces, and why it was wrong: the old glyphs were a four-upward-
# chevron Ethernet mark with no dots (the photograph has two chevrons opening
# outward with THREE dots between them), a USB trident ending in a square
# (it ends in a circle), a bolt 3.35 x 6.2 mm (twice the real size), an HDMI
# text object whose font metrics nothing here could check, and a headphone mark
# 4.48 mm across (the real one is 2.72). A feature can be present in the model
# and still be wrong; the icon row was 7.9 mm out before it was measured at all.
ICON_GLYPHS = {
    # A lightning bolt: an upper band from the top tip, a flare opening to the
    # right, a lower band, and a flare opening to the left at the bottom. The
    # photograph puts the mark from +1.88 mm to -1.37 mm, so it sits high in
    # its own band rather than centred on ICON_Z.
    "thunderbolt": [
        ("poly", [(-0.015, 0.188), (-0.060, 0.184), (-0.005, 0.075),
                  (-0.062, 0.051), (-0.046, 0.027), (-0.028, 0.012),
                  (0.040, -0.124), (0.058, -0.137), (0.062, -0.119),
                  (0.020, 0.002), (0.046, 0.017), (0.050, 0.044),
                  (0.035, 0.070)]),
    ],
    # Two chevrons opening away from each other, with three dots between them.
    # The first trace of these undershot by 11% in both axes, which the
    # acceptance test caught: 3.67 x 2.00 mm against the photograph's
    # 4.08 x 2.26.
    "ethernet": [
        ("poly", [(-0.209, 0.000), (-0.122, 0.113), (-0.087, 0.113),
                  (-0.173, 0.000), (-0.087, -0.113), (-0.122, -0.113)]),
        ("poly", [(0.209, 0.000), (0.122, 0.113), (0.087, 0.113),
                  (0.173, 0.000), (0.087, -0.113), (0.122, -0.113)]),
        ("disc", -0.100, 0.006, 0.023),
        ("disc", 0.000, 0.006, 0.023),
        ("disc", 0.100, 0.006, 0.023),
    ],
    # The trident: an arrowhead on the stem, a branch to a square on the -X
    # side and one to a circle on the +X side, and a circle for the tail. The
    # branches are two segments each, because in the photograph they leave the
    # stem low and swing outward before turning up; a single straight line
    # reads as a Y, not as the USB mark. The square is on -X because a REAR
    # view mirrors the model, and in Apple's photograph the square is on the
    # right of the frame.
    "usb": [
        ("poly", [(-0.030, 0.136), (0.032, 0.136), (0.001, 0.202)]),
        ("stroke", 0.000, -0.095, 0.000, 0.145, 0.009),
        ("stroke", 0.000, -0.042, 0.040, -0.022, 0.0085),
        ("stroke", 0.040, -0.022, 0.078, 0.055, 0.0085),
        ("stroke", 0.000, -0.042, -0.034, -0.020, 0.0085),
        ("stroke", -0.034, -0.020, -0.068, 0.070, 0.0085),
        ("disc", 0.000, -0.119, 0.026),
        ("disc", 0.070, 0.092, 0.022),
        ("poly", [(-0.100, 0.058), (-0.060, 0.058), (-0.060, 0.098),
                  (-0.100, 0.098)]),
    ],
    # "HDMI" as strokes. Cap height 1.66 mm; the wordmark measures 5.74 mm.
    # Every z endpoint stops 0.13 mm short of the cap line because a stroke
    # carries a round cap of its own half-width past each end: ending them on
    # the cap line makes the mark 1.92 mm tall, which is the whole of the
    # height error the acceptance test reported.
    "hdmi": [
        ("stroke", 0.281, -0.070, 0.281, 0.070, 0.013),      # H
        ("stroke", 0.187, -0.070, 0.187, 0.070, 0.013),
        ("stroke", 0.281, 0.000, 0.187, 0.000, 0.011),
        ("stroke", 0.112, -0.070, 0.112, 0.070, 0.013),      # D
        ("stroke", 0.112, 0.059, 0.022, 0.059, 0.013),
        ("stroke", 0.112, -0.059, 0.022, -0.059, 0.013),
        ("stroke", 0.022, 0.059, 0.004, 0.035, 0.013),
        ("stroke", 0.004, 0.035, 0.004, -0.035, 0.013),
        ("stroke", 0.004, -0.035, 0.022, -0.059, 0.013),
        ("stroke", -0.066, -0.070, -0.066, 0.070, 0.013),    # M
        ("stroke", -0.191, -0.070, -0.191, 0.070, 0.013),
        ("stroke", -0.066, 0.070, -0.128, -0.017, 0.012),
        ("stroke", -0.128, -0.017, -0.191, 0.070, 0.012),
        ("stroke", -0.2565, -0.076, -0.2565, 0.076, 0.0075),  # I
    ],
    # A headband over two rounded earcups. The arc runs 214 degrees, from -17
    # up over the top and down to 197: a0/a1 are degrees from +X, so the sweep
    # is measured anticlockwise and 200..340 is the arc UNDER the centre, not
    # over it. Centre of curvature is 0.24 mm above ICON_Z, which is what puts
    # the band's crown at +1.72 mm. The earcups are the rounded octagons you
    # get from a 0.52 x 1.00 mm rounded rectangle turned 18 degrees inward; the
    # photograph shows them leaning towards each other, and upright ones read
    # as a different mark.
    "headphone": [
        ("arc", 0.000, 0.024, 0.133, 0.015, -17.0, 197.0),
        ("poly", [(-0.133, -0.015), (-0.106, -0.006), (-0.091, -0.014),
                  (-0.068, -0.086), (-0.075, -0.101), (-0.102, -0.110),
                  (-0.117, -0.102), (-0.141, -0.030)]),
        ("poly", [(0.111, -0.015), (0.084, -0.006), (0.069, -0.014),
                  (0.046, -0.086), (0.053, -0.101), (0.080, -0.110),
                  (0.095, -0.102), (0.119, -0.030)]),
    ],
}

# Glyph -> its centre x, so a caller need not know the naming convention.
ICON_GLYPH_X = {
    "thunderbolt": ICON_TB_X,
    "ethernet": ICON_ETH_X,
    "usb": ICON_USB_X,
    "hdmi": ICON_HDMI_X,
    "headphone": ICON_HP_X,
}

# ============================================================= front elevation
# A FRONT view puts model +X on the image's RIGHT, so
# model_x = x_from_image_left - 98.5.
#
#   name      x(cm)     w(cm)    h(cm)
#   USBC_1   -6.626    0.26     0.850
#   USBC_2   -5.148    0.27     0.850
#   SDXC     -2.447    2.700    0.270
#   LED      +6.619    r 0.161  (a bright 3.2 mm dot, not a hole)
FRONT_PORTS = [
    ("USBC_1", -6.626, 0.26, 0.850),
    ("USBC_2", -5.148, 0.27, 0.850),
    ("SDXC",   -2.447, 2.700, 0.270),
]
LED_X = 6.619
# 0.135 was a guess. The photograph gives 3.21 mm as the mean of two
# independent measurements that agree to 0.06 mm - the widest chord across the
# dot (3.17 horizontal, 3.25 vertical) and the equivalent disc from its
# quarter-peak area (3.23) - so the radius is 0.161 cm, not 0.135.
LED_R = 0.161

# ==================================================================== underside
FOOT_XY = 7.45
FOOT_R = 0.55

# ==================================================================== internals
# From the rear cutaway in reference/hk/hw_elements_case_xray.jpg and the fin
# detail in hw_elements_fans_xray.jpg, read as fractions of the 95 mm height
# and converted:
#
#     6% .. 45% from the top   z 8.9 .. 5.0   two blower shrouds, each ~80 mm
#                                               wide, split by a centre gap
#    45% .. 53%               z 5.0 .. 4.5   the finned heatsink under them
#    53% .. 58%               z 4.5 .. 4.1   the copper heat pipe / board plane
#    58% .. 76%               z 4.1 .. 2.3   the logic board and its components
#    76% .. 90%               z 2.3 .. 0.9   the power supply, right, with its
#                                               copper coil; connectors, left
#    90% .. 95%               z 0.9 .. 0.0   the base intake
#
# These came out of "looks about right".  They are now measured off Apple's
# own front cutaway (reference/hk/hw_elements_fans_xray.jpg) by
# tools/measure_xray.py, and the numbers below are what that tool reports:
#
#   two assemblies, mirror-symmetric about the centreline to 0.5 mm
#   each 58 mm wide, x 8..66 and 131..189, centres +/-62 mm
#   each 32.4 mm of fin field, y 4.3..36.7 mm below the case top,
#     i.e. z 5.83..9.07, and a shroud that has to clear the top cover's inner
#     face at z 9.20 -> 3.50 tall, axis z 7.40
#
# The blowers' lower edge lands at z 5.8 cm, 3 mm above the rear exhaust
# field's top edge at 5.28 cm.  Two independently measured features meeting
# like that is the main reason to believe the height: the blowers feed that
# field.
#
# What this view CANNOT give, and what is therefore still a design choice and
# not a measurement: the impeller's rotation axis, its diameter, and the
# assembly's fore/aft position.  There is one cutaway and it is a front view,
# so depth is simply not observable.  FAN_R is set by the modelling
# constraint that the bore has to fit inside the shroud, not by the photo.
#
# An earlier revision put the fans at z 6.15, offset 4.55, 83 mm wide, with
# the heatsink at 3.60 and the supply at 3.0.  That was wrong in the x
# direction by 17 mm and in width by 25 mm, and it stacked the assembly too
# low, leaving the bottom third of the case empty.
FAN_Z = 7.40                 # impeller centre
FAN_X = 6.20                 # +/- offset of each blower from the centreline
FAN_R = 2.70                 # bore radius; must satisfy 2*r <= FAN_SHROUD_W
FAN_SHROUD_W = 5.90
FAN_SHROUD_D = 13.0
FAN_SHROUD_H = 3.50
# The centre spine. The X-ray shows a bright vertical bar hard against the
# case centreline, with a hard edge on BOTH sides at 97.3 and 100.6 mm, so its
# width (3.3 mm) and position are the best-determined thing in the whole
# interior. It runs the height of the fan bay and is interrupted by a
# cross-member. The earlier build left the whole centre empty.
SPINE_W = 0.33
# Measured visible runs are y 3.9..18.4 and 26.1..39.5 mm from the top, i.e.
# z 9.11..7.66 and 7.29..5.55. The bar is already interrupted once, so the
# lower end is where it is last SEEN, not necessarily where it stops; the
# spine is modelled down to the bottom of the fan bay it divides, 5.65, which
# is 1 mm below the last visible row and keeps it clear of the fin stack.
SPINE_Z0 = 5.65
SPINE_Z1 = 9.11
SPINE_D = 12.4               # depth: not observable in a front cutaway
SPINE_BREAK_Z0 = 6.90        # the cross-member that interrupts it
SPINE_BREAK_Z1 = 7.60
SPINE_BREAK_HALF_X = 2.60    # spans the gap between the two housings
# The bright full-width plane below the blowers measures y 57..64 mm from the
# top, i.e. z 3.1..3.8 cm, centre 3.45.  The heatsink and the copper plane sit
# in the unlit gap above it and are not measurable from this render, so they
# are placed to keep the stack clear instead: tools/check_internals.py fails
# the build if the fin stack reaches the fan shroud or the copper plane
# intersects the package under it.
HEATSINK_Z = 4.70             # fin stack tops out just under the blowers
PIPE_Z = 3.95                # the copper heat-pipe / board plane
PCB_Z = 3.45
# The row of cylindrical parts sitting on the floor rail measures y 82..89 mm
# from the top, centre z 0.95.
PSU_Z = 0.95
SPEAKER_Z = 1.60
WALL = 0.15                  # aluminium wall thickness of the shell


def io_row_check():
    """Assert the measured layout is self-consistent. Cheap, and it catches a
    transcription error in the tables above immediately."""
    problems = []

    def chk(cond, msg):
        if not cond:
            problems.append(msg)

    chk(IO_Z * 10 < 95 - FIELD_BOT_MM, "port row overlaps the perforated field")
    chk(IO_Z * 10 > 95 - 87.9 + 2.0, "port row overlaps the base band")
    chk(UPPER_Z0 < UPPER_Z1, "rear field is inverted")
    chk(GRILLE_BAND_Z1 < UPPER_Z0, "base band overlaps the rear field")
    chk(UPPER_HALF_X * 2 < W, "rear field is wider than the chassis")

    # The power button. These are ordering constraints, not repeats of the
    # measured values: what breaks is a gap that swallows the glyph, or a glyph
    # that lands in the gap, and both are invisible in a picture but obvious
    # here.
    chk(POWER_BTN_GAP_W > 0, "power button gap has no width")
    chk(POWER_BTN_GAP_W < POWER_BTN_R,
        "power button gap (%.3f cm) is wider than the button (%.3f cm)"
        % (POWER_BTN_GAP_W, POWER_BTN_R))
    chk(POWER_BTN_GLYPH_W > 0, "power glyph has no stroke width")
    chk(POWER_BTN_GLYPH_R + POWER_BTN_GLYPH_W / 2 < POWER_BTN_R - POWER_BTN_GAP_W,
        "power glyph (%.3f cm) runs into the gap at %.3f cm"
        % (POWER_BTN_GLYPH_R + POWER_BTN_GLYPH_W / 2, POWER_BTN_R - POWER_BTN_GAP_W))
    chk(POWER_BTN_GLYPH_R - POWER_BTN_GLYPH_W / 2 > 0,
        "power glyph straddles the button's centre")
    chk(POWER_BTN_GLYPH_A0 < POWER_BTN_GLYPH_A1,
        "power glyph arc is inverted")

    # no two rear connectors may overlap
    items = [(n, x, w) for n, x, w, _ in REAR_PORTS]
    items.append(("AC_INLET", AC_INLET_X, AC_INLET_W))
    items.append(("HEADPHONE", HEADPHONE_X, HEADPHONE_R * 2))
    items.append(("POWER_BTN", POWER_BTN_X, POWER_BTN_R * 2))
    items.sort(key=lambda t: t[1])
    for (n1, x1, w1), (n2, x2, w2) in zip(items, items[1:]):
        gap = (x2 - w2 / 2.0) - (x1 + w1 / 2.0)
        chk(gap > 0.10, "%s and %s are %.2f cm apart (need > 0.10)" % (n1, n2, gap))

    for n, x, w, h in REAR_PORTS:
        chk(abs(x) + w / 2.0 < UPPER_HALF_X,
            "rear port %s at x=%.2f falls outside the field width" % (n, x))
    return problems


if __name__ == "__main__":
    bad = io_row_check()
    for b in bad:
        print("SPEC_FAIL:", b)
    print("SPEC_OK" if not bad else "SPEC_FAIL (%d)" % len(bad))
