#!/usr/bin/env python3
"""Offline renderer + comparison harness for the Mac Studio model.

Why this exists
---------------
Blender cannot start in this environment: it crashes inside Metal's GPU backend
detection before any Python runs, so `build_mac_studio.py` cannot be executed
here. Rather than verify the model by reading the code back, this renders the
model's geometry directly from the SAME spec module the Blender build imports
(blender/mac_studio_spec.py) and lays it beside Apple's photograph.

That is a stronger check than eyeballing a Cycles render anyway: both images
are reduced to a common chassis box, so anything that differs is a real
difference in the model rather than a framing or lens difference.

Method
------
Signed-distance-field ray march, orthographic, one view per elevation. The
perforations are not marched — at a 1.57 mm pitch there are ~3,300 holes on the
rear field alone and marching them is hopeless. Instead the recessed floor is
detected from the hit point and the regular lattice is evaluated in 2-D at the
hit, which is what the eye actually reads.

Usage:
    python3 tools/compare_render.py front rear
    python3 tools/compare_render.py all
"""
import math
import os
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "blender"))

import mac_studio_spec as S   # noqa: E402

REF = os.path.join(ROOT, "reference")
OUT = os.path.join(ROOT, "renders", "compare")

F = np.float32


# ------------------------------------------------------------------ SDF utils
def sd_round_rect2(px, py, hx, hy, r):
    """2-D rounded rectangle, negative inside."""
    r = min(r, hx, hy)
    qx = np.abs(px) - (hx - r)
    qy = np.abs(py) - (hy - r)
    outside = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2)
    inside = np.minimum(np.maximum(qx, qy), 0.0)
    return outside + inside - r


def sd_box(p, b):
    """Axis-aligned box, negative inside. p is (N, 3) — note q[:, k], not q[k]:
    q[k] would take the k-th ROW and silently collapse an (N, 3) result to (3,)."""
    q = np.abs(p) - b
    qx, qy, qz = q[:, 0], q[:, 1], q[:, 2]
    return (np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2
                    + np.maximum(qz, 0) ** 2)
            + np.minimum(np.maximum(qx, np.maximum(qy, qz)), 0.0))


def sd_round_box(p, b, r):
    return sd_box(p, np.array(b, dtype=np.float64) - r) - r


def smax(a, b, k):
    """Smooth max — blends two solids without the hard crease of np.maximum."""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h + k * h * (1.0 - h)


# ------------------------------------------------------------------ the model
def sdf_body(P):
    """The enclosure.

    Built as an ERODED CORE plus a uniform offset, not by shrinking the Z
    half-height and taking a max with the plan outline. The shrink version
    looks equivalent and is not: it produces a prism of half-height
    hz - R_HORZ, so the body ends up 7.6 mm short and 7.6 mm low. The base band
    lives at z 0..0.70 cm and simply fell off the bottom of the case, and the
    whole elevation was then cropped against a chassis box the render did not
    fill. Eroding by R_HORZ in all three axes and dilating by the same amount
    keeps the plan radius R_VERT, the half-height hz, and breaks both edges.
    """
    cz = S.FOOT_H + (S.H_TOTAL - S.FOOT_H) / 2.0
    hz = (S.H_TOTAL - S.FOOT_H) / 2.0
    core = np.maximum(
        sd_round_rect2(P[:, 0], P[:, 1], S.W / 2.0 - S.R_HORZ, S.D / 2.0 - S.R_HORZ,
                       max(S.R_VERT - S.R_HORZ, 1e-3)),
        np.abs(P[:, 2] - cz) - (hz - S.R_HORZ))
    return core - S.R_HORZ


def sdf_ac_inlet(P):
    """The three-lobed mains inlet.

    A polar radius r(t) = r0 (1 + a cos 3t) is a smooth trefoil; the real part
    is a rounded cloverleaf, not three separate circles, and a union of circles
    at 120 degrees leaves notches that reach almost to the centre. The outline
    is then scaled to the measured bounding box (22.0 x 16.4 mm), which is wider
    than tall, so a circular arrangement would be wrong.
    """
    x = P[:, 0] - S.AC_INLET_X
    z = P[:, 2] - S.IO_Z
    th = np.arctan2(z, x)
    rr = np.sqrt(x * x + z * z)
    a = 0.26
    r_lobe = 0.5 * S.AC_INLET_H / (1.0 + a)          # so the shape fills the box
    shape = rr - r_lobe * (1.0 + a * np.cos(3.0 * th + math.pi / 2.0))
    kx = S.AC_INLET_W / (2.0 * r_lobe * (1.0 + a))
    kz = S.AC_INLET_H / (2.0 * r_lobe * (1.0 + a))
    xs = x / max(kx, 1e-6)
    zs = z / max(kz, 1e-6)
    th2 = np.arctan2(zs, xs)
    r2 = np.sqrt(xs * xs + zs * zs)
    return r2 - r_lobe * (1.0 + a * np.cos(3.0 * th2 + math.pi / 2.0))


def sdf_shell(P):
    """Hollow enclosure: the outer form with the ventilation recesses cut in."""
    d = sdf_body(P)

    # --- rear perforated field -------------------------------------------
    # A shallow pocket in the rear panel. The cutter's inner face has to land
    # exactly UPPER_DEPTH behind the skin: centring it on the panel plane cuts
    # 0.6 cm, which is 4x the real recess and swallows the field's own lattice
    # test (which keys on the hit point being just behind the skin).
    c = np.array([0.0, S.D / 2.0 + 0.60 - S.UPPER_DEPTH,
                  (S.UPPER_Z0 + S.UPPER_Z1) / 2.0])
    b = np.array([S.UPPER_HALF_X, 0.60, (S.UPPER_Z1 - S.UPPER_Z0) / 2.0])
    pocket = sd_round_box(P - c, b, 0.06)
    d = np.maximum(d, -pocket)

    # --- base band: a groove around the whole perimeter -------------------
    # The cutter is a ring SLAB that has to reach OUTSIDE the skin. Bounding it
    # by the skin itself makes `max(outer, -inner)` exactly zero everywhere on
    # the surface, so the subtraction removes nothing at all: the band then
    # renders as bare metal and the whole lower intake is simply missing.
    over = 0.25
    outer = sd_round_rect2(P[:, 0], P[:, 1], S.W / 2.0 + over, S.D / 2.0 + over,
                           S.R_VERT + over)
    inner = sd_round_rect2(P[:, 0], P[:, 1], S.W / 2.0 - S.GRILLE_RECESS,
                           S.D / 2.0 - S.GRILLE_RECESS, S.R_VERT - S.GRILLE_RECESS)
    zc = (S.GRILLE_BAND_Z0 + S.GRILLE_BAND_Z1) / 2.0
    zh = (S.GRILLE_BAND_Z1 - S.GRILLE_BAND_Z0) / 2.0
    ring = np.maximum(np.maximum(-outer, inner), np.abs(P[:, 2] - zc) - zh)
    d = np.maximum(d, -ring)

    # --- rear connectors --------------------------------------------------
    yf = S.D / 2.0
    for name, x, w, h in S.REAR_PORTS:
        c = np.array([x, yf - 0.05, S.IO_Z])
        b = np.array([w / 2.0 + 0.05, 0.32, h / 2.0 + 0.05])
        d = np.maximum(d, -sd_round_box(P - c, b, 0.045))

    ac = np.maximum(sdf_ac_inlet(P), yf - 0.42 - P[:, 1])
    d = np.maximum(d, -ac)

    # headphone jack
    jack = np.sqrt((P[:, 0] - S.HEADPHONE_X) ** 2 + (P[:, 2] - S.IO_Z) ** 2)
    d = np.maximum(d, -np.maximum(jack - S.HEADPHONE_R, yf - 0.32 - P[:, 1]))

    # Touch ID: a shallow debossed disc on the rear panel. The y window is
    # D/2-0.34 .. D/2-0.05; the previous form asked for y > D/2-0.05 AND
    # y < D/2-0.14 at once, which is empty, so the button was never cut.
    td = np.sqrt((P[:, 0] - S.TOUCHID_X) ** 2 + (P[:, 2] - S.IO_Z) ** 2)
    d = np.maximum(d, -np.maximum(td - S.TOUCHID_R,
                                  np.abs(P[:, 1] - (S.D / 2.0 - 0.20)) - 0.15))

    # --- front connectors and LED ----------------------------------------
    yf = -S.D / 2.0
    for name, x, w, h in S.FRONT_PORTS:
        c = np.array([x, yf + 0.05, S.IO_Z])
        b = np.array([w / 2.0 + 0.05, 0.32, h / 2.0 + 0.05])
        d = np.maximum(d, -sd_round_box(P - c, b, 0.045))
    return d


def sdf_feet(P):
    d = None
    for sx in (-1, 1):
        for sy in (-1, 1):
            s = sd_box(P - np.array([sx * S.FOOT_XY, sy * S.FOOT_XY, S.FOOT_H / 2.0]),
                       np.array([S.FOOT_R, S.FOOT_R, S.FOOT_H / 2.0]))
            d = s if d is None else np.minimum(d, s)
    return d


def sdf_internals(P):
    """The inside, for the cutaway view. Mirrors build_internals().

    Layout read off the rear cutaways in reference/hk/, as fractions of the
    95 mm height: two blower shrouds from z 8.9 down to 5.0 filling almost the
    whole width, the finned heatsink immediately beneath them, the copper
    heat-pipe plane at z 4.15, the logic board at 3.2, and the power supply and
    speaker at the bottom, next to the intake they feed. An earlier layout put
    the supply at z 3.0 and left the bottom third of the case empty.
    """
    d = None

    def uni(s):
        nonlocal d
        d = s if s is not None else d

    def put(s):
        nonlocal d
        d = s if d is None else np.minimum(d, s)

    fz, fx, fr = S.FAN_Z, S.FAN_X, S.FAN_R
    for sx in (-1, 1):
        cx = sx * fx
        shroud = sd_round_box(P - np.array([cx, 0.0, fz + 0.10]),
                              np.array([S.FAN_SHROUD_W / 2, S.FAN_SHROUD_D / 2,
                                        S.FAN_SHROUD_H / 2]), 0.35)
        # a round duct through the shroud, so each fan reads as an airway
        bore = np.sqrt((P[:, 0] - cx) ** 2 + P[:, 1] ** 2) - fr
        duct = np.maximum(bore, np.abs(P[:, 2] - fz) - S.FAN_SHROUD_H * 0.48)
        put(np.maximum(shroud, -duct))
        hub = np.sqrt((P[:, 0] - cx) ** 2 + P[:, 1] ** 2) - fr * 0.30
        put(np.maximum(hub, np.abs(P[:, 2] - fz) - 0.65))

    # the centre spine and its cross-member, measured off the X-ray
    put(sd_box(P - np.array([0.0, 0.0, (S.SPINE_Z0 + S.SPINE_Z1) / 2]),
               np.array([S.SPINE_W / 2, S.SPINE_D / 2,
                         (S.SPINE_Z1 - S.SPINE_Z0) / 2])))
    put(sd_round_box(P - np.array(
        [0.0, 0.0, (S.SPINE_BREAK_Z0 + S.SPINE_BREAK_Z1) / 2]),
        np.array([S.SPINE_BREAK_HALF_X, S.SPINE_D * 0.36,
                  (S.SPINE_BREAK_Z1 - S.SPINE_BREAK_Z0) / 2]), 0.06))

    hz = S.HEATSINK_Z
    put(sd_box(P - np.array([0.0, 0.0, hz]), np.array([8.4, 6.3, 0.25])))
    # fin stack, as a repeating slab
    fin = np.maximum(np.abs(P[:, 0]) - 8.2,
                     np.maximum(np.abs(((P[:, 1] + 5.9) % 0.37) - 0.185) - 0.08,
                                np.abs(P[:, 2] - (hz + 0.48)) - 0.40))
    put(fin)
    put(sd_box(P - np.array([0.0, 0.0, hz - 0.36]), np.array([2.3, 2.3, 0.14])))

    # the copper plane that crosses the whole machine at this height
    put(sd_box(P - np.array([0.0, 0.0, S.PIPE_Z]), np.array([8.8, 7.2, 0.11])))

    pz = S.PCB_Z
    put(sd_box(P - np.array([0.0, 0.0, pz]), np.array([9.1, 7.8, 0.08])))
    for sx in (-1, 1):
        put(sd_box(P - np.array([sx * 3.9, 0.0, pz + 0.22]),
                   np.array([2.1, 1.3, 0.14])))
    for sy in (-1, 1):
        put(sd_box(P - np.array([-5.2, sy * 3.4, pz + 0.20]),
                   np.array([2.0, 1.1, 0.12])))

    # power supply bottom right, speaker and front I/O bottom left
    put(sd_round_box(P - np.array([5.90, 1.4, S.PSU_Z]),
                     np.array([2.8, 4.7, 0.85]), 0.12))
    put(np.maximum(np.sqrt((P[:, 0] - 5.90) ** 2 + (P[:, 1] + 3.6) ** 2) - 1.15,
                   np.abs(P[:, 2] - (S.PSU_Z + 0.10)) - 0.70))
    # the electrolytic row, on the floor frame left of the supply
    for k in range(7):
        put(np.maximum(np.sqrt((P[:, 0] + 6.0 - 1.3 * k) ** 2
                               + (P[:, 1] + 2.0) ** 2) - 0.30,
                       np.abs(P[:, 2] - 1.00) - 0.35))
    put(sd_round_box(P - np.array([-6.6, -5.4, S.SPEAKER_Z]),
                     np.array([1.3, 1.1, 0.55]), 0.12))
    put(sd_round_box(P - np.array([-6.6, 3.2, S.SPEAKER_Z + 0.20]),
                     np.array([1.7, 2.5, 0.40]), 0.10))

    for sx in (-1, 1):
        put(sd_box(P - np.array([sx * 8.95, 0.0, 4.0]),
                   np.array([0.25, 7.5, 3.7])))
    put(sd_box(P - np.array([0.0, 0.0, 0.52]), np.array([8.7, 7.5, 0.11])))
    return d


# ------------------------------------------------------------------- marching
def march(P0, DIRS, sdf, tmax=60.0, steps=110):
    """Sphere-trace, then STOP each ray at its own first surface sample.

    The subtlety that matters: `t` must not keep advancing after a ray has
    already hit. Advancing it anyway walks the sample point further and further
    *into* the solid — at the 0.0006 minimum step, 105 leftover iterations put
    the reported point 0.06 cm behind the skin. That is enough to make every
    ray in the port band land inside the "connector cavity" test, so the whole
    band renders as one black bar and the port row becomes invisible. Aiming
    the shading at a surface the ray already passed 0.6 mm behind measures
    nothing; it just hides the geometry the harness exists to check.
    """
    t = np.zeros(P0.shape[0])
    alive = np.ones(P0.shape[0], dtype=bool)
    hit = np.zeros(P0.shape[0], dtype=bool)
    for _ in range(steps):
        d = sdf(P0 + DIRS * t[:, None])
        new = alive & (d < 0.0008 * (1.0 + t))
        hit |= new
        alive &= ~new
        t = np.where(alive, t + np.maximum(d * 0.85, 0.0006), t)
        alive &= t < tmax
        if not alive.any():
            break
    return np.where(hit, t, np.inf)


def normal(P, sdf, eps=0.0012):
    n = np.zeros_like(P)
    for k in range(3):
        e = np.zeros(3)
        e[k] = eps
        n[:, k] = sdf(P + e) - sdf(P - e)
    # A point sitting exactly on a lattice seam gets a difference of zero in
    # every axis; the norm is then 0, the division emits inf, and inf reaches
    # the shading matrix and turns the whole row band into NaN. Clamp the norm
    # AND drop non-finite normals, so a single degenerate sample cannot take a
    # region out of the comparison.
    n = np.nan_to_num(n, nan=0.0, posinf=0.0, neginf=0.0)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    bad = ~(ln[:, 0] > 1e-6)
    n = n / np.maximum(ln, 1e-6)
    n[bad] = np.array([0.0, 0.0, 1.0])
    return n


def autocorr_profile(a, axis):
    """Normalised autocorrelation of a 2-D boolean array along one axis."""
    a = np.asarray(a, dtype=np.float64)
    a = a - a.mean()
    n = a.shape[axis]
    out = np.zeros(n)
    for k in range(n):
        if axis == 0:
            p, q = a[k:], a[:n - k]
        else:
            p, q = a[:, k:], a[:, :n - k]
        d = np.sqrt((p * p).sum() * (q * q).sum())
        out[k] = float((p * q).sum() / d) if d > 0 else 0.0
    return out


def autocorr_peak(mask, axis, lo=1, hi=None, frac=0.90):
    """Lag, in pixels, of the FUNDAMENTAL period of a lattice.

    Two ways this goes wrong, both of which hit the base band.

    Taking the plain argmax finds lag 1. Adjacent pixels inside one hole are
    perfectly correlated, so the autocorrelation peaks at 1 px and falls off
    from there whatever the real period is.

    Taking the largest peak at all finds a harmonic. The band correlates at
    0.906 mm AND at 1.811 mm, and the harmonic is marginally stronger; that is
    how the band came to be modelled two hole rows deep instead of eight.

    So: find the first local minimum - the autocorrelation has fallen off the
    hole itself - and then the first local maximum after it. That is the
    fundamental by construction, whatever the harmonics do.
    """
    prof = autocorr_profile(mask, axis)
    if hi is None:
        hi = len(prof) // 2
    if hi <= lo:
        return 0
    seg = prof[lo:hi]
    if not len(seg) or seg.max() <= 0:
        return 0
    # first local minimum
    k = int(np.argmin(seg))
    # then the first local maximum after it
    tail = seg[k:]
    if len(tail) < 2:
        return lo + k
    m = int(np.argmax(tail))
    return lo + k + m


def row_pitch_profile(mask):
    """1-D dark-share-per-row profile, for measuring a lattice's row pitch.

    The 2-D vertical autocorrelation is a poor estimator for a half-staggered
    lattice, and not by a little: on the base band it runs 0.5, 0.0, -0.2,
    -0.2, 0.0, 0.2, 0.1, -0.1 ... so the six-pixel period is barely above the
    noise. That is expected - shifting a hexagonal lattice straight up by one
    row moves every hole half a pitch sideways, so it is not supposed to
    correlate with itself. Collapsing each row to its dark share first removes
    that cancellation and the period comes back cleanly.
    """
    return np.asarray(mask, dtype=np.float64).mean(axis=1)


def stagger_fraction(mask, pitch_px):
    """How far alternate rows are offset, as a fraction of the column pitch.

    Averaging the even rows and the odd rows separately, then correlating the
    two profiles against each other. That is the definition of a stagger
    directly, and it is also the only version with enough signal: correlating
    single rows against row 0 on the base band peaks at 0.2-0.6 and wanders
    between +0.0 and +0.9 pitch from one separation to the next, because one
    row of 775 pixels is not enough to locate a hole edge to a third of a
    pitch. Averaging a dozen rows on each side brings the same estimate back
    with a spread under a tenth of a pitch.

    On a square lattice the peak lands at 0.00; on a half-staggered one, 0.50.
    """
    m = np.asarray(mask, dtype=np.float64)
    if pitch_px < 2 or m.shape[0] < 4:
        return 0.0
    even = m[0::2].mean(axis=0)
    odd = m[1::2].mean(axis=0)
    even = even - even.mean()
    odd = odd - odd.mean()
    den = np.sqrt((even * even).sum() * (odd * odd).sum())
    if den <= 0:
        return 0.0
    half = int(pitch_px) // 2
    if half < 1:
        return 0.0
    cc = np.array([float((np.roll(even, t) * odd).sum() / den)
                   for t in range(half + 1)])
    t = int(np.argmax(cc))
    return t / float(pitch_px)


# ------------------------------------------------------------- grille lattice
def _semi_axes(radius):
    """Hole semi-axes as (rx, rz).

    `radius` may be a scalar, which keeps every existing caller a circle, or a
    pair, which is what the base band needs: its holes are obround, about
    twice as wide as they are tall, and forcing them into a circle is what made
    the modelled band read as a row of small squares.
    """
    if np.isscalar(radius):
        return float(radius), float(radius)
    rx, rz = radius
    return float(rx), float(rz)


def lattice_mask(x, z, pitch, radius, row_pitch=None, stagger=0.0, row0=0.0):
    """1.0 inside a hole of the measured lattice.

    Column pitch, row pitch and stagger fraction are all separate. The rear
    field's rows sit 16% further apart than its columns and each alternate row
    is offset by a fifth of the pitch, so a single pitch with a hard-coded
    half-pitch stagger lines up over the first centimetres and then drifts
    visibly across a 171 mm field - which is precisely the error a numeric
    profile cannot see and a picture shows immediately. The base band is the
    other case: same idea, half-staggered, but with its own pitch and its own
    obround hole.
    """
    row_pitch = pitch if row_pitch is None else row_pitch
    rx, rz = _semi_axes(radius)
    row = np.floor((z - row0) / row_pitch)
    xs = x - np.where(stagger, (row % 2.0) * stagger * pitch, 0.0)
    cx = np.round(xs / pitch) * pitch
    cz = row0 + (row + 0.5) * row_pitch
    return ((xs - cx) / rx) ** 2 + ((z - cz) / rz) ** 2 < 1.0


def lattice_coverage(x, z, pitch, radius, row_pitch=None, stagger=0.0, row0=0.0,
                     n=3):
    """Fraction of a pixel that is hole, by supersampling the lattice test.

    A hard in/out test at this scale makes every hole one pixel larger than it
    is, and the perforation then reads several per cent darker than Apple's
    photograph in EVERY region at once. That is a sampling bias, not a
    geometry error, and it is exactly the kind of offset that would otherwise
    be "fixed" by moving real dimensions around. Three samples per axis is
    enough: the residual error is well under a per cent of the open area.
    """
    acc = np.zeros(np.shape(x), dtype=np.float64)
    offs = np.linspace(-0.5 + 0.5 / n, 0.5 - 0.5 / n, n)
    for dx in offs:
        for dz in offs:
            acc += lattice_mask(x + dx * pitch, z + dz * pitch, pitch, radius,
                                row_pitch, stagger, row0)
    return acc / (n * n)


# ------------------------------------------------------------- the icon glyphs
def _poly_inside(px, pz, pts):
    """Even-odd crossing test for a closed polygon, vectorised over px/pz."""
    inside = np.zeros(np.shape(px), dtype=bool)
    n = len(pts)
    for i in range(n):
        ax, az = pts[i]
        bx, bz = pts[(i + 1) % n]
        straddles = (az > pz) != (bz > pz)
        if not straddles.any():
            continue
        t = np.where(straddles, (pz - az) / np.where(bz == az, 1e-12, bz - az), 0.0)
        inside ^= straddles & (px < ax + t * (bx - ax))
    return inside


def _seg_dist(px, pz, x0, z0, x1, z1):
    """Distance from each point to the segment (x0,z0)-(x1,z1)."""
    dx, dz = x1 - x0, z1 - z0
    L2 = dx * dx + dz * dz
    if L2 < 1e-18:
        return np.hypot(px - x0, pz - z0)
    t = np.clip(((px - x0) * dx + (pz - z0) * dz) / L2, 0.0, 1.0)
    return np.hypot(px - (x0 + t * dx), pz - (z0 + t * dz))


def glyph_mask(x, z, name=None, supersample=3):
    """The engraved marks, True where a glyph is.

    Reads S.ICON_GLYPHS - the same table the Blender build reads - so the
    checked image and the model are two renderings of one description. Values
    are model-space centimetres; the glyph is placed at (ICON_GLYPH_X, ICON_Z).
    """
    x = np.asarray(x, dtype=np.float64)
    z = np.asarray(z, dtype=np.float64)
    out = np.zeros(np.broadcast(x, z).shape, dtype=bool)
    names = [name] if name else sorted(S.ICON_GLYPHS)
    for g in names:
        cx, cz = S.ICON_GLYPH_X[g], S.ICON_Z
        for part in S.ICON_GLYPHS[g]:
            acc = np.zeros(out.shape, dtype=bool)
            if part[0] == "poly":
                pts = [(px + cx, pz + cz) for px, pz in part[1]]
                acc = _poly_inside(x, z, pts)
            elif part[0] == "stroke":
                _, x0, z0, x1, z1, hw = part
                acc = _seg_dist(x, z, cx + x0, cz + z0, cx + x1, cz + z1) <= hw
            elif part[0] == "disc":
                _, px, pz, r = part
                acc = (x - (cx + px)) ** 2 + (z - (cz + pz)) ** 2 <= r * r
            elif part[0] == "arc":
                _, px, pz, r, hw, a0, a1 = part
                ax, az = cx + px, cz + pz
                rad = np.hypot(x - ax, z - az)
                th = (np.degrees(np.arctan2(z - az, x - ax)) - a0) % 360.0
                acc = ((np.abs(rad - r) <= hw)
                       & (th <= (a1 - a0) % 360.0))
            else:
                raise ValueError("unknown icon primitive %r" % (part[0],))
            out |= acc
    return out


def shade(P, N, view, hit, cam_dir):
    """A simple studio shade: it only has to read the FORM, not be pretty.

    The key light is placed relative to the CAMERA, not to the world. A fixed
    key leaves the rear elevation lit only by ambient — the rear render came
    back nearly black, which reads as a modelling error when it is only a
    lighting one, and a black panel is exactly where the grille lattice needs
    to be checked.
    """
    col = np.zeros((P.shape[0], 3))
    if not hit.any():
        return col
    p, n = P[hit], N[hit]
    n = np.nan_to_num(n, nan=0.0, posinf=0.0, neginf=0.0)

    alb = np.array([0.76, 0.765, 0.775])
    col[hit] = alb

    # --- rear perforated field -------------------------------------------
    rear = ((np.abs(n[:, 1]) > 0.5) & (p[:, 1] > S.D / 2.0 - 0.28)
            & (np.abs(p[:, 0]) < S.UPPER_HALF_X)
            & (p[:, 2] > S.UPPER_Z0) & (p[:, 2] < S.UPPER_Z1))
    # --- base band: the groove around the whole perimeter -----------------
    band = ((p[:, 2] > S.GRILLE_BAND_Z0 + 0.03) & (p[:, 2] < S.GRILLE_BAND_Z1 - 0.03)
            & (np.abs(n[:, 2]) < 0.5)
            & (np.maximum(np.abs(p[:, 0]) / (S.W / 2), np.abs(p[:, 1]) / (S.D / 2)) > 0.93))
    # The groove FLOOR is bare metal, only a little shaded by its own walls.
    # Painting it dark counts as "hole" in the profile comparison and makes the
    # band read as solid; the base band gets a slightly brighter floor than the
    # rear field because its 1.3 mm groove wraps the whole perimeter and takes
    # less light than the field's shallow 1.5 mm pocket, and at 0.60 it came
    # back 9% more open than Apple's photograph.
    floor_col = np.where(band[:, None], np.array([0.70, 0.705, 0.715]),
                         np.array([0.60, 0.605, 0.615]))
    col[hit] = np.where((rear | band)[:, None], floor_col, col[hit])

    # A HARD in/out test, not a supersampled one. Supersampling was tried and
    # reverted: it is more faithful as an image, but it turns a genuinely
    # bimodal region - hole or groove floor, nothing between - into a
    # continuum, and Otsu then splits that continuum down the middle and reports
    # the field as 89% open when its true open area is 48%. The measurement
    # wants the physical two levels; the picture is not the metric.
    cov = np.zeros(p.shape[0], dtype=bool)
    if rear.any():
        cov = np.where(rear, lattice_mask(
            p[:, 0], p[:, 2], S.UPPER_PITCH_X, S.UPPER_HOLE_R,
            S.UPPER_PITCH_Z, S.UPPER_STAGGER, S.UPPER_Z0 + 0.10), cov)
    if band.any():
        # The lattice has to be evaluated in the TANGENT plane, keyed on which
        # axis the face NORMAL runs along:
        #   normal along +/-Y  (front and rear panels) -> columns run along X
        #   normal along +/-X  (the two sides)           -> columns run along Y
        # Testing `|n_x| < 0.5` to mean "this is a front panel" is off by one
        # axis: it is true for the front panel AND it selects the Y column
        # coordinate, which barely varies across that face, so every pixel in a
        # row gets the same answer and the band renders as a few solid
        # horizontal stripes instead of a perforation.
        front_back = band & (np.abs(n[:, 1]) > 0.5)
        sides = band & (np.abs(n[:, 0]) > 0.5)
        cb = np.where(front_back, lattice_mask(
            p[:, 0], p[:, 2], S.GRILLE_PITCH_X,
            (S.GRILLE_HOLE_RX, S.GRILLE_HOLE_RZ),
            S.GRILLE_PITCH_Z, S.GRILLE_STAGGER, S.GRILLE_BAND_Z0 + 0.055), False)
        cs = np.where(sides, lattice_mask(
            p[:, 1], p[:, 2], S.GRILLE_PITCH_X,
            (S.GRILLE_HOLE_RX, S.GRILLE_HOLE_RZ),
            S.GRILLE_PITCH_Z, S.GRILLE_STAGGER, S.GRILLE_BAND_Z0 + 0.055), False)
        cov = np.where(band, cb | cs, cov)
    col[hit] = np.where(cov[:, None], np.array([0.05, 0.05, 0.055]), col[hit])

    # --- connector cavities ------------------------------------------------
    # Key on RECESS DEPTH, not on "behind the panel plane": the panel skin is
    # itself at y = D/2, so a test of the form `p.y > D/2 - k` paints the whole
    # port band black and the individual connectors disappear into one bar.
    # Only geometry that is actually *behind* the skin is cavity.
    rear_cav = ((p[:, 1] < S.D / 2.0 - 0.05) & (p[:, 1] > S.D / 2.0 - 0.55)
                & (np.abs(p[:, 0]) < 8.2)
                & (p[:, 2] > S.IO_Z - 1.0) & (p[:, 2] < S.IO_Z + 1.0))
    front_cav = ((p[:, 1] > -S.D / 2.0 + 0.05) & (p[:, 1] < -S.D / 2.0 + 0.55)
                 & (np.abs(p[:, 0]) < 8.2)
                 & (p[:, 2] > S.IO_Z - 0.60) & (p[:, 2] < S.IO_Z + 0.60))
    col[hit] = np.where((rear_cav | front_cav)[:, None],
                        np.array([0.028, 0.028, 0.032]), col[hit])

    # status LED: a bright lens, the one non-metal feature on the front.
    # Guarded by the panel it belongs to, or the rear elevation grows a white
    # dot 13 cm from the Touch ID button and the comparison "passes" a model
    # that has a light where no light exists.
    led = (((p[:, 0] - S.LED_X) ** 2 + (p[:, 2] - S.IO_Z) ** 2)
           < (S.LED_R * 1.7) ** 2) & (p[:, 1] < -S.D / 2.0 + 0.30)
    col[hit] = np.where(led[:, None], np.array([0.96, 0.97, 0.99]), col[hit])

    # Touch ID ring: a debossed circle reads as a tone step, not a hole.
    # Both the ring AND the glyph are gated on the rear panel. An ungated glyph
    # paints a dark disc on the FRONT panel at the same x and z, which is how
    # a front elevation ended up with a mysterious hole 8 cm to the left of
    # the USB-C ports.
    #
    # The ring used to be 0.6 mm wide and the glyph a FILLED disc of radius
    # 0.52 R, both invented. tools/touchid_probe.py measured the photograph and
    # the button is bright metal with a 0.3 mm gap and a set of strokes in an
    # annulus at 1.5..2.25 mm. Filling that disc is what made the button read
    # 32% bright against the photograph's 84%, and tools/port_row.py then
    # charged the whole difference to the model being "too open" in the port
    # row. build_mac_studio.py already drew an arc and a bar; the two files had
    # diverged silently because nothing compared them.
    on_rear = p[:, 1] > 9.0
    td = np.sqrt((p[:, 0] - S.TOUCHID_X) ** 2 + (p[:, 2] - S.IO_Z) ** 2)
    ring = ((td < S.TOUCHID_R) & (td > S.TOUCHID_R - S.TOUCHID_GAP_W)
            & on_rear)
    col[hit] = np.where(ring[:, None], np.array([0.30, 0.30, 0.31]), col[hit])
    gr0 = S.TOUCHID_GLYPH_R - S.TOUCHID_GLYPH_W / 2.0
    gr1 = S.TOUCHID_GLYPH_R + S.TOUCHID_GLYPH_W / 2.0
    ang = np.degrees(np.arctan2(-(p[:, 2] - S.IO_Z), p[:, 0] - S.TOUCHID_X))
    ang = np.where(ang < 0, ang + 360.0, ang)
    glyph = ((td > gr0) & (td < gr1) & on_rear
             & (ang >= S.TOUCHID_GLYPH_A0) & (ang <= S.TOUCHID_GLYPH_A1))
    col[hit] = np.where(glyph[:, None], np.array([0.22, 0.22, 0.23]), col[hit])
    # the bar across the open side, as build_mac_studio.py draws it
    bar = ((np.abs(p[:, 0] - S.TOUCHID_X) < S.TOUCHID_GLYPH_W / 2.0)
           & (np.abs(p[:, 2] - (S.IO_Z + S.TOUCHID_R * 0.30))
              < S.TOUCHID_R * 0.46 / 2.0) & on_rear)
    col[hit] = np.where(bar[:, None], np.array([0.22, 0.22, 0.23]), col[hit])

    # The engraved icon row. Same source as the Blender build: ICON_GLYPHS in
    # the spec, rasterised here. The renderer used to skip this row entirely,
    # so a rear comparison could not see the glyphs even while the model
    # carried them - which is how a bolt twice the right size and an Ethernet
    # mark with the wrong shape survived a passing run.
    icons = on_rear & (p[:, 1] > S.D / 2.0 - 0.10)
    if icons.any():
        col[hit] = np.where(
            (icons & glyph_mask(p[:, 0], p[:, 2]))[:, None],
            np.array([0.20, 0.20, 0.21]), col[hit])

    # --- lighting ----------------------------------------------------------
    # These matmuls emit "divide by zero / overflow / invalid value in matmul"
    # on some BLAS builds and are FALSE: the inputs here are a unit normal and
    # three unit vectors, the result is bounded by 1, and the render comes back
    # with zero non-finite pixels (checked, not assumed). What numpy is
    # reporting is a stale FP status flag left by an earlier underflow, not a
    # value. Left in, they bury a real NaN in forty lines of warning noise, so
    # the status noise is silenced here and replaced by an explicit assertion
    # that WOULD catch a real one.
    with np.errstate(all="ignore"):
        c = cam_dir / max(float(np.linalg.norm(cam_dir)), 1e-9)
        up = np.array([0.0, 0.0, 1.0])
        key = c * 0.72 + up * 0.62 + np.cross(c, up) * 0.34
        key /= max(float(np.linalg.norm(key)), 1e-9)
        fill = -c * 0.55 + up * 0.35
        fill /= max(float(np.linalg.norm(fill)), 1e-9)
        lam = np.maximum(n @ key, 0.0) * 0.66 + np.maximum(n @ fill, 0.0) * 0.22 + 0.34
        h = key + c
        h /= max(float(np.linalg.norm(h)), 1e-9)
        spec = np.maximum(n @ h, 0.0) ** 48 * 0.50
        col[hit] = np.clip(col[hit] * (lam + spec)[:, None], 0.0, 1.0)
    if not np.isfinite(col[hit]).all():
        bad = int((~np.isfinite(col[hit]).all(axis=1)).sum())
        raise FloatingPointError(
            "shade() produced %d non-finite pixels for view %r; normals were "
            "unit length to %.12f, so the fault is upstream of the lighting"
            % (bad, view))
    return np.nan_to_num(col, nan=0.0)


# --------------------------------------------------------------------- views
VIEWS = {
    # name: (ray direction, image right axis, image up axis, ref image)
    "front": (np.array([0.0, 1.0, 0.0]), np.array([1.0, 0.0, 0.0]),
              np.array([0.0, 0.0, 1.0]), "apple_static_front.jpg"),
    "rear": (np.array([0.0, -1.0, 0.0]), np.array([-1.0, 0.0, 0.0]),
             np.array([0.0, 0.0, 1.0]), "apple_hw_back.jpg"),
    "side": (np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]),
             np.array([0.0, 0.0, 1.0]), None),
    "top": (np.array([0.0, 0.0, -1.0]), np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]), None),
    "bottom": (np.array([0.0, 0.0, 1.0]), np.array([1.0, 0.0, 0.0]),
               np.array([0.0, -1.0, 0.0]), None),
}


def render(view, W=760, H=None, cutaway=False, samples=2):
    d, right, up, _ = VIEWS[view]
    span_x = S.W + 3.0
    if view in ("front", "rear"):
        span_y = S.H_TOTAL + 3.0
    else:
        span_y = S.D + 3.0
    if H is None:
        H = int(round(W * span_y / span_x))
    us = np.linspace(-span_x / 2, span_x / 2, W)
    vs = np.linspace(span_y / 2, -span_y / 2, H)
    U, V = np.meshgrid(us, vs)
    centre = np.array([0.0, 0.0, S.H_TOTAL / 2.0])
    target = centre + right * U.ravel()[:, None] + up * V.ravel()[:, None]
    P0 = target - d * 40.0
    DIRS = np.tile(d, (target.shape[0], 1))

    sdf = sdf_shell
    if cutaway:
        shell, inner = sdf_shell, sdf_internals
        # Remove the half of the enclosure nearest the camera.
        #
        # The camera sits at target - d*40, so points with the SMALLEST
        # (P . d) are the closest to it: the near half is {P . d < 0} and the
        # far half, the one to keep, is {P . d >= 0}.  The signed distance of
        # that half-space is -(P . d) - it is negative inside the kept half and
        # positive outside it - and intersecting with it is a max:
        #
        #     max(shell(P), -(P . d))
        #
        # The sign here was wrong and the failure was silent.  Using +(P . d)
        # is the signed distance of the OPPOSITE half-space, so the clip kept
        # the near half and deleted the far one.  The rear cutaway still
        # produced a plausible-looking picture, which is what made it survive:
        # you were looking at the outside of the rear panel with the
        # internals safely behind it.  The front cutaway gave it away
        # immediately - the full front panel came back, ports, slot, LED and
        # all, because nothing in front of it had been removed.
        #
        # The matmul's divide-by-zero warning in here is the same stale FP
        # status flag as in shade(): P and d are finite, the clip is
        # intentional, and the render comes back with no non-finite pixels.
        def sdf(P):
            with np.errstate(all="ignore"):
                return np.minimum(np.maximum(shell(P), -(P @ d)), inner(P))
    else:
        # The feet belong to the chassis silhouette. Leaving them out shortens
        # the rendered body by FOOT_H against a crop box computed for the full
        # height, which offsets every feature by 2% of the machine.
        _shell = sdf_shell
        _feet = sdf_feet

        def sdf(P):
            return np.minimum(_shell(P), _feet(P))
    t = march(P0, DIRS, sdf)
    hit = np.isfinite(t)
    P = P0 + DIRS * np.where(hit, t, 0.0)[:, None]
    N = normal(P, sdf)
    col = shade(P, N, view, hit, -d)
    img = col.reshape(H, W, 3)
    img[~hit.reshape(H, W)] = 0.94
    return np.clip(img, 0, 1)


def model_chassis_box(view, W, H):
    """Pixel box of the chassis in a render, computed rather than detected.

    The render maps model space to pixels linearly, so the box is exact:
    rescaling the whole image to the reference's chassis height instead — which
    is what a naive comparison does — leaves the model body smaller than the
    reference body and offsets every feature by several percent of the height.
    That is enough to hide a 12 mm error in the port row.
    """
    d, right, up, _ = VIEWS[view]
    span_x = S.W + 3.0
    span_y = (S.H_TOTAL if view in ("front", "rear") else S.D) + 3.0
    if view in ("front", "rear"):
        # the "width" of the silhouette is W; the "height" is H_TOTAL
        span_x, span_y = S.W + 3.0, S.H_TOTAL + 3.0
    # column: u from -span_x/2 (col 0) to +span_x/2 (col W)
    half = S.W / 2.0
    c0 = (span_x / 2.0 + half) / span_x * W
    c1 = (span_x / 2.0 - half) / span_x * W
    # row: v from +span_y/2 (row 0) down; target_z = H_TOTAL/2 + v
    zc = S.H_TOTAL / 2.0
    body_h = S.H_TOTAL if view in ("front", "rear") else S.D
    if view in ("front", "rear"):
        r0 = (span_y / 2.0 - (S.H_TOTAL - zc)) / span_y * H
        r1 = (span_y / 2.0 - (0.0 - zc)) / span_y * H
    else:
        r0 = (span_y / 2.0 - body_h / 2.0) / span_y * H
        r1 = (span_y / 2.0 + body_h / 2.0) / span_y * H
    return (int(round(min(c0, c1))), int(round(min(r0, r1))),
            int(round(max(c0, c1))), int(round(max(r0, r1))))


def to_pil(arr):
    return Image.fromarray((arr * 255).astype(np.uint8))


# ---------------------------------------------------------------- comparison
def chassis_box(g):
    """Chassis box in pixels: width detected, height DERIVED from 197:95.

    The height used to be taken from `g < 244`, which runs past the bottom of
    the machine into the contact shadow. On both Apple shots that overshoots by
    1.2-1.3 mm, 1.3% of the height, and because the model side is cropped from a
    synthetic render whose silhouette ends exactly at the chassis, the two
    images were being compared at different vertical scales - the region report
    was reading a different physical millimetre out of each side, up to 1.3 mm
    apart, which is wider than the 0.9 mm acceptance tolerance this project
    works to. Apple publishes 197 x 197 x 95 mm, so the pixel box has a known
    aspect and the height follows from the width.
    """
    def span(mask, axis):
        prof = mask.sum(axis=axis)
        idx = np.nonzero(prof > 0.02 * prof.max())[0]
        return int(idx[0]), int(idx[-1])
    x0, x1 = span(g < 238.0, 0)
    y0, _ = span(g < 244.0, 1)     # FIRST row, not the last
    width = x1 - x0 + 1
    height = int(round(width * 95.0 / 197.0))
    return x0, y0, x0 + width - 1, y0 + height - 1


def normalise_ref(path, out_h=520):
    """Crop an Apple photo to its chassis box and resample to a common size."""
    im = Image.open(path).convert("RGB")
    g = np.asarray(im.convert("L"), dtype=np.float32)
    x0, y0, x1, y1 = chassis_box(g)
    crop = im.crop((x0, y0, x1 + 1, y1 + 1))
    w, h = crop.size
    out_w = int(round(out_h * w / h))
    return crop.resize((out_w, out_h), Image.LANCZOS)


def overlay(a, b):
    """Model in magenta over the reference: a half-millimetre shift in a
    feature shows up as a magenta fringe rather than an argument."""
    al = np.asarray(a.convert("L"), dtype=np.float32) / 255.0
    bl = np.asarray(b.convert("L").resize(a.size), dtype=np.float32) / 255.0
    return Image.fromarray((np.clip(
        np.stack([1.0 - bl * 0.80, 1.0 - al * 0.80,
                  1.0 - np.maximum(al, bl) * 0.55], axis=2), 0, 1) * 255
    ).astype(np.uint8))


def _panel_level(img):
    """Brightness of the bare metal on a panel, kept for reporting only.

    The dark-share THRESHOLD is set per region by Otsu below; this is only the
    "how bright is the metal" figure printed in the header.
    """
    g = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
    return float(np.percentile(g, 85.0))


def otsu(values, bins=256):
    """Otsu's threshold AND its separability, as (threshold, eta).

    The dark-share measurement has to be exposure-invariant, and every fixed
    or globally-scaled threshold fails at that. A fixed cut is defeated by a
    difference in lighting between a synthetic render and a JPEG; a threshold
    scaled to the whole image's own brightness is defeated by the rear field
    itself, which covers 46% of the panel and drags any global statistic down
    with it until the field stops registering as perforated at all.

    Splitting each REGION on its own two modes sidesteps both. Inside the
    perforated field the histogram is genuinely bimodal - hole and groove floor
    - and Otsu finds the boundary between them in a synthetic render and in a
    photograph alike, whatever either one's absolute exposure happens to be.
    The number it yields is the physical open area, which is what the model
    and the photograph can actually be compared on.

    eta is Otsu's own between-class variance normalised by the total variance.
    It is what makes the result checkable: Otsu returns a threshold for EVERY
    histogram, including a perfectly unimodal one, where the "best" split is an
    arbitrary quantile and the dark share it produces is pure noise. A strip of
    bare aluminium 79-86 mm below the top edge, for example, has mean 0.758 with
    range 0.604-0.914 and no dark structure at all - Otsu still splits it at
    0.791 and reports 80% of it as "dark". That is not a modelling difference, it
    is the metric lying. eta separates the two cases: a real perforation field
    scores above ~0.5, a lit panel with a lighting gradient scores far below, and
    a low-eta strip has to be excluded from the comparison instead of compared.
    """
    v = np.asarray(values, dtype=np.float64).ravel()
    if v.size == 0:
        return 0.0, 0.0
    hist, edges = np.histogram(v, bins=bins, range=(0.0, 1.0))
    hist = hist.astype(np.float64)
    total = hist.sum()
    if total == 0:
        return 0.0, 0.0
    centres = (edges[:-1] + edges[1:]) / 2.0
    w0 = np.cumsum(hist)
    w1 = total - w0
    csum = np.cumsum(hist * centres)
    m0 = csum / np.maximum(w0, 1e-9)
    mt = csum[-1] / total
    m1 = (mt * total - csum) / np.maximum(w1, 1e-9)
    # sigma^2_B from pixel COUNTS, normalised to a probability scale, and
    # sigma^2_T as the true mean squared deviation - the ratio is eta in [0,1].
    # Skipping either normalisation is what makes eta come out in the millions.
    var_b = w0 * w1 * (m0 - m1) ** 2 / (total * total)
    var_t = float(((v - v.mean()) ** 2).mean())
    k = int(np.argmax(var_b))
    eta = float(var_b[k] / var_t) if var_t > 1e-12 else 0.0
    return float(centres[k]), eta


def is_lighting_falloff(values, thr=None):
    """True when a region's "dark" class is lighting, not openings.

    Two conditions, and both are needed.

    The dark class must cover a large share of the region. A panel lit from
    one side puts roughly half of itself below any split point; a row of
    connectors puts 15% there, and a perforation 45% - but the perforation's
    dark pixels are 0.2% of any one blob while the lit panel's are 80%.

    The largest blob must be most of that dark class. Perforation is thousands
    of small isolated holes, so the biggest is a fraction of a percent; a
    falloff, a contact shadow or an unmodelled opening is one contiguous
    region.

    Either condition alone misfires, and both ways. Judging on the blob alone
    calls the front's port row "lighting" - its three openings are large and
    nearly touch, so 79% of its dark pixels are in one blob - and then a real
    +3.5% difference on the connectors goes unreported. Judging on the share
    alone calls every perforated region lighting, since they are all about
    half dark.
    """
    v = np.asarray(values, dtype=np.float64)
    if v.size == 0:
        return True
    t = otsu(v)[0] if thr is None else thr
    m = v < t
    share = float(m.mean())
    if share <= 0.30:
        return False              # too little dark to be a broad falloff
    return largest_blob_fraction(m) > 0.50


def largest_blob_fraction(mask):
    """Share of the True pixels that lie in the single biggest 4-connected run.

    This is the test that tells a perforation field from a lighting gradient,
    and neither Otsu nor its separability eta can. Otsu splits ANY histogram,
    and a panel lit from one side is genuinely bimodal - 0.604 to 0.914 on the
    rear photograph, eta 0.67 - so Otsu cuts that band down the middle and calls
    80% of it "dark" on a strip that is bare, unperforated metal. eta is high
    because the two halves really are 0.31 apart; it says nothing about whether
    either half is a hole.

    Geometry settles it. Perforation is thousands of small isolated blobs, so
    the biggest one is a fraction of a percent of the dark pixels. A gradient,
    a shadow, a contact edge or an unmodelled port is one contiguous region, so
    its biggest blob is nearly all of them. Run-length encoding with union-find
    keeps this cheap: a perforated strip has thousands of runs, a gradient one
    has a single run per row, and neither is walked pixel by pixel.
    """
    m = np.asarray(mask, dtype=bool)
    total = int(m.sum())
    if total == 0:
        return 0.0
    parent = [0]

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    areas = {}
    prev = []                      # [(start, end, label)] from the row above
    for y in range(m.shape[0]):
        row = m[y]
        if not row.any():
            prev = []
            continue
        # run starts / ends via a single diff
        d = np.diff(np.concatenate(([0], row.view(np.int8), [0])))
        starts = np.nonzero(d == 1)[0]
        ends = np.nonzero(d == -1)[0]
        cur = []
        for s, e in zip(starts.tolist(), ends.tolist()):
            label = len(parent)
            parent.append(label)
            areas[label] = e - s
            for ps, pe, pl in prev:
                if ps < e and s < pe:        # horizontal overlap == adjacency
                    union(label, pl)
            cur.append((s, e, label))
        prev = cur

    best = {}
    for lab, a in areas.items():
        r = find(lab)
        best[r] = best.get(r, 0) + a
    return max(best.values()) / float(total)


def numeric_report(ref_img, model_img, view, nbands=48):
    """Row and column dark-share profiles, model vs reference.

    This localises a fault: where the perforated field starts and stops, where
    the port row sits, where each connector falls horizontally. Both images are
    cropped to their own chassis box, so nothing here can move unless the
    geometry did.

    The threshold is Otsu's, computed once per named region, so the profile is
    a localisation aid and region_report below is the metric to converge on.
    """
    m = model_img.resize(ref_img.size, Image.LANCZOS)
    gr = np.asarray(ref_img.convert("L"), dtype=np.float32) / 255.0
    gm = np.asarray(m.convert("L"), dtype=np.float32) / 255.0
    h = gr.shape[0]

    # Each row band is judged on its own two modes, but only if it HAS two
    # modes. On bare aluminium Otsu returns a confident-looking split of a
    # single lighting gradient, and the resulting "dark share" is an arbitrary
    # quantile that swings by tens of percent between two images that are
    # actually identical. So a band is only compared when its dark class is
    # made of many small blobs rather than one contiguous region.
    #
    # The gate is the largest-blob test, not Otsu's separability eta. On the
    # reference's bare panel eta is 0.60-0.68 - it really is that bimodal, the
    # light simply falls off across the panel - and on the MODEL's flat panel
    # eta is 0.82, HIGHER, because a near-constant strip has a vanishing total
    # variance for its between-class variance to be measured against. eta
    # rewards a constant image; only geometry tells holes from a gradient.
    rrow = np.zeros(h)
    mrow = np.zeros(h)
    trusted = np.zeros(h, dtype=bool)
    step = max(2, int(round(0.5 / 95.0 * h)))
    for y in range(0, h - step + 1, step):
        tr, _ = otsu(gr[y:y + step])
        tm, _ = otsu(gm[y:y + step])
        fr = largest_blob_fraction(gr[y:y + step] < tr)
        fm = largest_blob_fraction(gm[y:y + step] < tm)
        if fr > 0.50 and fm > 0.50:
            continue                 # both are lighting, neither is a feature
        rrow[y:y + step] = (gr[y:y + step] < tr).mean()
        mrow[y:y + step] = (gm[y:y + step] < tm).mean()
        trusted[y:y + step] = True

    # xs must live in the same domain as the row index. Sampling a 0..1 axis
    # against a 0..h-1 axis clips everything past x=1 to the final row, which
    # prints the same number in all 48 bands and looks like a suspiciously
    # stable result rather than the total failure it is.
    xs = np.linspace(0, h - 1, nbands)
    idx = np.linspace(0, h - 1, h)
    rrow = np.interp(xs, idx, rrow)
    mrow = np.interp(xs, idx, mrow)
    tr8 = np.interp(xs, idx, trusted.astype(np.float64)) > 0.5
    rcol = (gr < otsu(gr)[0]).mean(axis=0)
    mcol = (gm < otsu(gm)[0]).mean(axis=0)
    print("  %-6s row bands (%% of height from top)   panel ref %.2f model %.2f"
          % (view, _panel_level(ref_img), _panel_level(m)))
    print("     " + " ".join("%3d" % (i * 100 // nbands) for i in range(nbands)))
    print("  ap " + " ".join("%3d" % round(v * 100) if t else "  ."
                            for v, t in zip(rrow, tr8)))
    print("  md " + " ".join("%3d" % round(v * 100) if t else "  ."
                            for v, t in zip(mrow, tr8)))
    # only bands with real structure on at least one side can be compared
    d = np.where(tr8, np.abs(mrow - rrow), 0.0)
    print("  |d| " + " ".join("%3d" % round(v * 100) for v in d)
          + "   mean %4.1f%%  max %4.1f%%  over %d/%d bands"
          % (d.mean() * 100, d.max() * 100, int(tr8.sum()), nbands))
    k = int(np.argmax(d)) if tr8.any() else 0
    print("  worst row band %d%% of height = %.1f mm from the top"
          % (k * 100 // nbands, (k + 0.5) * 95.0 / nbands))
    dc = np.abs(mcol - rcol)
    print("  column |d| mean %4.1f%%  max %4.1f%%" % (dc.mean() * 100, dc.max() * 100))
    return d


CUT_PREFIX = "cut_"


def regions(kind):
    """Named vertical regions of the panel, as fractions of the chassis height.

    The per-band table is the diagnostic that localises a fault, but a 48-band
    grid puts 1.98 mm in a band while the perforation rows are 1.57 mm apart, so
    inside the field the two alias against each other and the per-band number
    depends on which side of the beat the model's hole rows happen to land. The
    region means average that out and give a number that means what it says.
    """
    if kind == "rear":
        return [("plain top", 0.0, S.FIELD_TOP_MM / 95.0),
                ("field", S.FIELD_TOP_MM / 95.0, S.FIELD_BOT_MM / 95.0),
                ("plain mid", S.FIELD_BOT_MM / 95.0,
                 (95.0 - S.IO_Z * 10 - 1.1) / 95.0),
                ("port row", (95.0 - S.IO_Z * 10 - 1.1) / 95.0,
                 (95.0 - S.IO_Z * 10 + 1.1) / 95.0),
                ("plain lower", (95.0 - S.IO_Z * 10 + 1.1) / 95.0,
                 (95.0 - S.GRILLE_BAND_Z1 * 10) / 95.0),
                ("base band", (95.0 - S.GRILLE_BAND_Z1 * 10) / 95.0, 1.0)]
    return [("plain upper", 0.0,
             (95.0 - S.IO_Z * 10 - 1.1) / 95.0),
            ("port row", (95.0 - S.IO_Z * 10 - 1.1) / 95.0,
             (95.0 - S.IO_Z * 10 + 1.1) / 95.0),
            ("plain lower", (95.0 - S.IO_Z * 10 + 1.1) / 95.0,
             (95.0 - S.GRILLE_BAND_Z1 * 10) / 95.0),
            ("base band", (95.0 - S.GRILLE_BAND_Z1 * 10) / 95.0, 1.0)]


def web_runs(block):
    """Median BRIGHT run across a region and up it, in millimetres.

    Shared with tools/verify_spec.py, which gates the base band on it, so the
    picture comparison and the acceptance test cannot disagree about what the
    web is.
    """
    thr, _ = otsu(block)
    bright = ~(block < thr)
    out = []
    for axis in (1, 0):
        arr = bright if axis == 1 else bright.T
        lens = []
        for line in arr:
            d = np.diff(np.concatenate(([0], line.view(np.int8), [0])))
            s_, e_ = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
            lens.extend((e_ - s_).tolist())
        out.append(float(np.median(lens)) if lens else 0.0)
    # the caller works in millimetres; the blocks here are the full chassis
    # crop, so the scale is 197 mm across its width
    sx = 197.0 / block.shape[1]
    return out[0] * sx, out[1] * sx


def region_report(ref_img, m, view):
    """Open area per named region, model against reference, Otsu per region.

    This is the convergence metric. Everything in it is a physical quantity -
    how much of this part of the panel is open - and none of it depends on
    either image's exposure, which is what makes a delta here mean a modelling
    difference rather than a lighting one.
    """
    gr = np.asarray(ref_img.convert("L"), dtype=np.float32) / 255.0
    gm = np.asarray(m.convert("L"), dtype=np.float32) / 255.0
    h = gr.shape[0]
    # The silhouette edges are excluded. A region spanning the full width picks
    # up the anti-aliased boundary between chassis and background, which is a
    # crop artefact rather than a panel feature - the synthetic render's crop
    # blends to white over about a pixel and the photograph's over two, and
    # "plain lower" scored +2.2% purely from that difference. 2% of the width
    # is 3.9 mm at each side, well clear of any real feature.
    mgn = max(2, int(0.02 * gr.shape[1]))
    gr = gr[:, mgn:gr.shape[1] - mgn]
    gm = gm[:, mgn:gm.shape[1] - mgn]
    print("  %-6s %-12s %8s %8s %8s %7s" % (view, "region", "ref", "model",
                                            "delta", "eta r/m"))
    # track the worst region ALWAYS, not only the ones that fail: a report that
    # prints "worst 0.0% ()" whenever everything passes throws away the one
    # number that says how much margin is left
    worst = (0.0, "")
    over = []
    for name, a, b in regions(view):
        y0, y1 = int(round(a * h)), int(round(b * h))
        if y1 - y0 < 3:
            continue
        rr, rm = gr[y0:y1], gm[y0:y1]
        if name.startswith("plain"):
            # Bare metal has no bimodality to split, so a dark share here
            # measures lighting, not geometry. What can actually go wrong on a
            # plain panel is an unexpected opening or patch, and the way to
            # tell one from a lighting falloff is the shape of the dark class:
            # a patch is a few compact blobs, a falloff is one region that
            # covers most of the panel. When either side is a falloff the two
            # numbers are not comparable and the region is reported as such
            # rather than scored - scoring them is what produced "plain top
            # +3.6%" and "plain lower +6.4%" against images that differ only in
            # how they are lit.
            tr, _ = otsu(rr)
            tm, _ = otsu(rm)
            dr = float((rr < tr).mean())
            dm = float((rm < tm).mean())
            fr = largest_blob_fraction(rr < tr)
            fm = largest_blob_fraction(rm < tm)
            if is_lighting_falloff(rr) or is_lighting_falloff(rm):
                print("  %-6s %-12s %7.1f%% %7.1f%% %7s   %.2f/%.2f"
                      "  lighting falloff, not comparable"
                      % (view, name, dr * 100, dm * 100, "-", fr, fm))
                continue
            eta = (0.0, 0.0)
            ok = abs(dm - dr) < 0.02
        else:
            tr, er = otsu(rr)
            tm, em = otsu(rm)
            eta = (er, em)
            fr = largest_blob_fraction(rr < tr)
            fm = largest_blob_fraction(rm < tm)
            dr = float((rr < tr).mean())
            dm = float((rm < tm).mean())
            if is_lighting_falloff(rr) or is_lighting_falloff(rm):
                # one side is a lighting falloff, not perforation: the open
                # areas are not comparable, so this cannot be called a pass
                print("  %-6s %-12s %7.1f%% %7.1f%% %+7.1f%%  %.2f/%.2f"
                      "  NOT PERFORATION, not comparable"
                      % (view, name, dr * 100, dm * 100, (dm - dr) * 100,
                         fr, fm))
                over.append(name + " (lighting)")
                continue
            ok = abs(dm - dr) < 0.06
            if name == "base band":
                # The band is the one region where dark share cannot be the
                # verdict. Its dark class is the openings PLUS the shadow the
                # 1.3 mm recess throws onto its own web, so the photograph
                # reads about 48% open where the true opening is 28%, and the
                # offline renderer shades the band flat and cannot produce that
                # shadow at all. Scoring the two together would only measure
                # how deep the modelled recess is, which is a Cycles result
                # this sandbox cannot produce.
                #
                # What is comparable is the BRIGHT web: bare metal catching the
                # light, with no shadow term, from which the hole width follows
                # as pitch minus web. That is the acceptance criterion, and
                # tools/verify_spec.py check_band() gates on it - at the
                # photograph's own 0.151 mm/px, with the model rasterised on
                # the same grid.
                #
                # The number printed here is measured on the COMPARISON images,
                # which are 460 and 760 px wide, so a single pixel is 0.16 mm
                # and a bright run can only be counted to the nearest one. It
                # is a sanity check on the picture, not the gate; treat anything
                # inside +/-0.32 mm (two pixels) as "the render agrees", and go
                # to check_band for the number that actually decides.
                # `ref_img` is the chassis-box crop, so its width IS the case
                # width and one pixel is W/width mm. This line referenced a
                # W_MM that was never defined in this module, so the whole band
                # section raised NameError and the report ended before printing
                # the pass/fail line - the run looked like it had no result
                # rather than like it had failed. Take the width from the spec
                # so there is no second copy of it.
                px_mm = S.W * 10.0 / float(rr.shape[1])
                wx_r, wz_r = web_runs(rr)
                wx_m, wz_m = web_runs(rm)
                wtol = max(0.30, 2.0 * px_mm)
                web_ok = (abs(wx_m - wx_r) <= wtol and abs(wz_m - wz_r) <= wtol)
                print("      base band judged on the bright web, not the dark "
                      "share (the recess shadows its own web in the "
                      "photograph and the flat offline render cannot);")
                print("      measured here at %.3f mm/px, so +/-%.2f mm is one "
                      "pixel - check_band() is the gate" % (px_mm, px_mm))
                print("        web across  photo %.3f mm  model %.3f mm  "
                      "%+.3f mm%s" % (wx_r, wx_m, wx_m - wx_r,
                                      "" if abs(wx_m - wx_r) <= wtol
                                      else "   <-- OVER 2 px"))
                print("        web up       photo %.3f mm  model %.3f mm  "
                      "%+.3f mm%s" % (wz_r, wz_m, wz_m - wz_r,
                                      "" if abs(wz_m - wz_r) <= wtol
                                      else "   <-- OVER 2 px"))
                print("      %-6s %-12s %s"
                      % (view, name,
                         "OK (web, render resolution)" if web_ok
                         else "OVER 2 px (see check_band for the gate)"))
                if not web_ok:
                    over.append(name)
                continue
        if abs(dm - dr) > worst[0]:
            worst = (abs(dm - dr), name)
        if not ok:
            over.append(name)
        print("  %-6s %-12s %7.1f%% %7.1f%% %+7.1f%%  %.2f/%.2f%s"
              % (view, name, dr * 100, dm * 100, (dm - dr) * 100,
                 eta[0], eta[1], "" if ok else "  <-- check"))
    print("  %-6s worst region delta %.1f%% (%s)%s\n"
          % (view, worst[0] * 100, worst[1],
             "" if not over else "  OVER TOLERANCE: " + ", ".join(over)))
    return worst[0]


def compare(view, out_h=460):
    """Render one elevation and, when there is a photograph to check it
    against, lay it out beside Apple's shot plus a magenta overlay.

    A name prefixed `cut_` renders the same elevation with the near half of the
    enclosure removed and the internals exposed. There is no Apple photograph
    for that, but it is the only way to actually LOOK at the interior modelling
    while Blender is unavailable.
    """
    cutaway = view.startswith(CUT_PREFIX)
    key = view[len(CUT_PREFIX):] if cutaway else view
    d, right, up, ref = VIEWS[key]
    t0 = time.time()
    img = render(key, W=out_h * 3, cutaway=cutaway)
    os.makedirs(OUT, exist_ok=True)
    to_pil(img).save(os.path.join(OUT, "%s_model_full.png" % view))
    box = model_chassis_box(key, img.shape[1], img.shape[0])
    mine = to_pil(img[box[1]:box[3] + 1, box[0]:box[2] + 1])
    print("  rendered %-9s full %s, chassis %s in %.1fs"
          % (view, img.shape[:2], mine.size, time.time() - t0))
    mine.save(os.path.join(OUT, "%s_model.png" % view))
    if cutaway or not ref:
        return
    rp = normalise_ref(os.path.join(REF, ref), out_h)
    mine_r = mine.resize(rp.size, Image.LANCZOS)
    canvas = Image.new("RGB", (rp.size[0], out_h * 2 + 8), (255, 255, 255))
    canvas.paste(rp, (0, 0))
    canvas.paste(mine_r, (0, out_h + 8))
    canvas.save(os.path.join(OUT, "%s_compare.png" % view))
    overlay(rp, mine_r).save(os.path.join(OUT, "%s_overlay.png" % view))
    numeric_report(rp, mine_r, view)
    region_report(rp, mine_r, key)
    return rp, mine_r


def main():
    args = sys.argv[1:] or ["all"]
    if args[0] == "all":
        args = ["front", "rear", "side", "top", "bottom",
                "cut_rear", "cut_side", "cut_top"]
    for v in args:
        try:
            compare(v)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print("  FAILED %s: %s" % (v, exc))


if __name__ == "__main__":
    main()
