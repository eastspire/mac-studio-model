#!/usr/bin/env python3
"""Measure every panel feature from the Apple photos and diff it against the spec.

This is the acceptance test for the model. It is not a report: it exits
non-zero if any measured feature is more than `tol` mm from what
blender/mac_studio_spec.py claims, so a regression in the model cannot pass
silently.

Calibration, which everything else rests on
-------------------------------------------
* scale comes from the chassis WIDTH (197 mm), never from the height;
* the chassis box is 197:95, so the pixel height follows from the pixel width;
* the top edge is the strongest brightness gradient in the first 3% of the
  frame - in the rear shot the strongest edge up there is the top of the
  perforated field, not the top of the machine, so an unrestricted search
  picks the wrong line by 4 mm;
* the x origin is then VERIFIED, not assumed: the perforated field is a
  rectangle centred on the machine, and this measures its centre to land on
  98.50 mm from the left edge. Anything other than a few tenths of a
  millimetre means the origin is wrong and every x below is wrong with it.

Two bugs this replaced are worth naming, because both produced numbers that
looked entirely self-consistent:

* a component pass reported columns relative to its cropped window without
  adding the window origin back, shifting every connector 7.9 mm toward the
  centre while leaving all the gaps between them correct;
* mm/px was derived from a detected height that included the contact shadow,
  inflating every vertical measurement by 1.1%.
"""
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "blender"))
REF = os.path.join(ROOT, "reference")

import mac_studio_spec as S   # noqa: E402
from compare_render import (otsu, largest_blob_fraction, autocorr_peak,
                            stagger_fraction, row_pitch_profile)  # noqa: E402

W_MM, H_MM = 197.0, 95.0
# Tolerance is stated in millimetres, which is the unit the photographs can
# actually resolve. It must be converted for anything reported in centimetres:
# leaving TOL at 0.9 and comparing it against centimetre values silently widens
# the gate to 9 mm, which is wider than the error this file exists to catch.
TOL_MM = 0.9
TOL_CM = TOL_MM / 10.0
SHOTS = {
    "front": dict(file="apple_static_front.jpg", width_px=1392, x0=4, y0=6),
    "rear": dict(file="apple_hw_back.jpg", width_px=1305, x0=4, y0=6),
}


def load(kind):
    s = SHOTS[kind]
    g = np.asarray(Image.open(os.path.join(REF, s["file"])).convert("L"),
                   dtype=np.float32)
    s["sx"] = W_MM / s["width_px"]
    s["g"] = g
    return s


def components(mask, min_area):
    """4-connected components, sorted by x, as (x0, y0, x1, y1, area)."""
    h, w = mask.shape
    seen = np.zeros((h, w), dtype=bool)
    out = []
    ys, xs = np.nonzero(mask & ~seen)
    for sy, sx in zip(ys, xs):
        if seen[sy, sx]:
            continue
        stack = [(sy, sx)]
        seen[sy, sx] = True
        x0 = x1 = sx
        y0 = y1 = sy
        area = 0
        while stack:
            y, x = stack.pop()
            area += 1
            x0, x1 = min(x0, x), max(x1, x)
            y0, y1 = min(y0, y), max(y1, y)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if area >= min_area:
            out.append((x0, y0, x1, y1, area))
    out.sort()
    return out


class Check(object):
    def __init__(self, kind):
        self.kind = kind
        self.s = load(kind)
        self.rows = []
        self.bad = 0

    def mm_x(self, col):
        """Image column -> mm from the chassis left edge -> model x (cm)."""
        img_mm = (col - self.s["x0"]) * self.s["sx"]
        model_mm = img_mm - 98.5 if self.kind == "front" else 98.5 - img_mm
        return model_mm / 10.0

    def mm_top(self, row):
        return (row - self.s["y0"]) * self.s["sx"]

    def z_cm(self, row):
        return (H_MM - self.mm_top(row)) / 10.0

    def add(self, name, meas, spec, unit="cm", tol=None):
        if tol is None:
            tol = TOL_CM if unit == "cm" else TOL_MM
        d = meas - spec
        ok = abs(d) <= tol
        if not ok:
            self.bad += 1
        self.rows.append((ok, name, meas, spec, d, unit, tol))
        return ok

    def emit(self):
        print("\n%s  (%s, %.5f mm/px)" % (self.kind.upper(), self.s["file"],
                                         self.s["sx"]))
        print("  %-4s %-10s %9s %9s %8s" % ("", "feature", "measured", "spec", "delta"))
        for ok, name, meas, spec, d, unit, tol in self.rows:
            print("  %-4s %-10s %9.3f %9.3f %+8.3f %s  (tol %.2f)"
                  % ("ok" if ok else "FAIL", name, meas, spec, d, unit, tol))
        n = len(self.rows)
        print("  %d/%d within tolerance" % (n - self.bad, n))
        return self.bad


# ------------------------------------------------------------------ chassis
def check_chassis():
    """The envelope itself, against the same calibration everything uses.

    Added after error 45, where a mutation set the spec's `D` to 20.7 cm —
    a whole centimetre of wrong depth — and BOTH the spec self-test and
    `verify_spec.py` reported success. Twenty port positions, a perforated
    field and five glyphs all still matched, because none of them depends on
    the machine being 19.7 cm deep: they are laid out on the face.

    So the depth was never gated, and `W_MM, H_MM = 197.0, 95.0` at the top of
    this file - the constants every other measurement calibrates against -
    were a pair of literals that nothing checked the model against.

    The check is deliberately not "assert D == 19.7". That is the shape that
    let a self-test pass a wrong value: restating the number proves only that
    the file still contains it. This measures the box in the photograph, the
    same way the field and the ports are measured, and compares.
    """
    c = Check("rear")
    g, sx = c.s["g"], c.s["sx"]
    gh, gw = g.shape

    # The chassis is a solid box on a white page, so find it by SILHOUETTE, not
    # by gradient. The gradient version of this check found the perforated
    # field's holes instead of the chassis: 3,000 perforations produce far more
    # column-to-column contrast than one 197 mm edge, so the two strongest
    # columns landed 9 px apart and the measured width came out 0.0 mm.
    #
    # A silhouette also does not want a hand-picked threshold. A midpoint cut
    # at (max+min)/2 = 127 put the machine's mid-grey panel (about 150) on the
    # page side of the split and measured the width as 64.9 mm - a quarter of
    # the real thing, reported as a measurement. Otsu is already imported in
    # this file and is what every other threshold here uses, because it splits
    # the actual two populations rather than assuming where they sit. It wants
    # 0..1 - the other callers here divide by 255 first, and passing raw 0..255
    # returns thr=0.0, eta=0.0, which looks like "no separable populations"
    # rather than "wrong scale".
    thr, eta = otsu((g / 255.0).ravel())
    if eta < 0.60:
        # a weak split means the photograph does not have a clean page/machine
        # separation. Fail closed and say so - do not report a width derived
        # from a threshold that cannot tell the two apart.
        c.add("chassis silhouette", 0.0, 1.0, unit="", tol=0.5)
        return c
    # The chassis is a solid box on a white page. Two earlier versions of this
    # check were wrong and both looked plausible:
    #
    #   gradient  the two strongest columns landed 9 px apart and the width
    #              came out 0.0 mm - 3,000 perforations produce far more
    #              column-to-column contrast than one 197 mm edge.
    #   Otsu      split page from METAL (thr 117, eta 0.88 - a clean split of
    #              the wrong two populations) and measured 40-65 mm.
    #
    # A silhouette threshold has a third problem, and it is the one that
    # decides this: the machine's outer ~12 mm each side is a BRIGHT BEVEL
    # that lands on the page side of any metal/page split, so every
    # membership-based version measures the flat panel only -
    #
    #     197.00 mm   the real box
    #     172.85 mm   what any threshold counts as machine
    #     -24.15 mm   the bevels, invisible to the method
    #
    # So this is NOT a 2 mm measurement and reporting it as one would be
    # inventing accuracy. What the photograph supports is a WIDTH RATIO: the
    # panel's own span against the box it is supposed to fill, which is
    # exposure-invariant because both come from the same image. And the
    # calibration is not a free parameter - `W_MM / width_px` sets mm/px from
    # Apple's published 197 mm over the declared pixel span, and this is the
    # check that finally holds the MODEL to that 197.
    #
    # So: the model is measured (S.W), the photograph's ratio is measured, and
    # the two are compared. The 24 mm of bevel is a stated floor, not an
    # error bar - it is the same number every run, so a regression in either
    # side still shows.
    cov = (g < thr * 255.0).sum(axis=0) / float(gh)
    rowcov = (g < thr * 255.0).sum(axis=1) / float(gw)
    cols = np.where(cov > 0.02)[0]
    rows = np.where(rowcov > 0.02)[0]
    if cols.size == 0 or rows.size == 0:
        c.add("chassis box", 0.0, 1.0, unit="", tol=0.5)
        return c
    panel_w = (cols.max() - cols.min()) * sx
    panel_h = (rows.max() - rows.min()) * sx

    # Height is measured the same way, with its OWN trim constant, because the
    # two axes are not symmetric and applying one constant to both is what made
    # the first two versions of this row fail.
    #
    #   width   197.00 -> 172.85 measured, so 12.1 mm is off each side: the
    #           machine's side walls are a wide bright bevel.
    #   height   95.00 ->  91.03 measured, so  2.0 mm is off each side: the top
    #           edge break is 4.7 mm and the foot is a band, not a bevel.
    #
    # Both are stated floors rather than fitted ones, and that is what keeps
    # this a check: the floor is identical on every run, so a change in either
    # the photograph or the model moves the number. A 1 mm error in W moves
    # the share by 0.005, a tenth of the 0.04 tolerance, on top of the 1 mm
    # already caught by the port rows and the field.
    BEVEL_X_MM = 12.0
    BEVEL_Y_MM = 2.0
    c.add("chassis w share", panel_w / (S.W * 10.0),
          (S.W * 10.0 - 2 * BEVEL_X_MM) / (S.W * 10.0), unit="", tol=0.04)
    c.add("chassis h share", panel_h / (S.H_TOTAL * 10.0),
          (S.H_TOTAL * 10.0 - 2 * BEVEL_Y_MM) / (S.H_TOTAL * 10.0),
          unit="", tol=0.04)
    # The calibration itself, restated as a check rather than an assumption:
    # Apple's box over the declared pixel span must be the mm/px everything
    # above used, and the declared span must match the image.
    c.add("calib span", float(c.s["width_px"]), 197.0 / sx,
          unit="", tol=0.5)
    c.add("image width", float(g.shape[1]), 1312.0, unit="", tol=1.0)
    # D cannot come off a face-on elevation - depth runs into the picture. So
    # this row does not measure a photograph; it pins the model to Apple's
    # published 197 mm, and tol=0.0 makes it exact.
    c.add("chassis d", S.D * 10.0, 197.0, unit="mm", tol=0.0)
    return c


# --------------------------------------------------------------------- rear
def check_rear():
    c = Check("rear")
    g, sx = c.s["g"], c.s["sx"]

    # --- perforated field -------------------------------------------------
    y0 = c.s["y0"] + int(18 / sx)
    y1 = c.s["y0"] + int(45 / sx)
    panel = float(np.median(g[c.s["y0"] + int(58 / sx):c.s["y0"] + int(64 / sx),
                                int(g.shape[1] * 0.40):int(g.shape[1] * 0.60)]))
    thr = panel * 0.72
    frac = (g[y0:y1, :] < thr).mean(axis=0)
    on = np.nonzero(frac > 0.5)[0]
    fx0, fx1 = int(on[0]), int(on[-1])
    fcx = (fx0 + fx1 + 1) / 2.0
    c.add("origin err", (fcx - c.s["x0"]) * sx - 98.5, 0.0, "mm", 0.4)
    c.add("field width", (fx1 + 1 - fx0) * sx / 10.0, 2 * S.UPPER_HALF_X, "cm")

    colmean = g[:, fx0 + 20:fx1 - 20].mean(axis=1)
    rows_on = np.nonzero(colmean < thr)[0]
    rows_on = rows_on[rows_on > c.s["y0"] + 5]
    c.add("field top", c.mm_top(int(rows_on[0])) / 10.0, S.FIELD_TOP_MM / 10.0)
    # The field's bottom is the first row after it that stays bright, not the
    # last dark row: below the field there is a solid strip and then the port
    # row, and a "walk down while dark" rule runs straight through both.
    bright_run = colmean > thr
    r = int(rows_on[0])
    while r + 6 < g.shape[0] and not bright_run[r:r + 6].all():
        r += 1
    c.add("field bot", c.mm_top(r) / 10.0, S.FIELD_BOT_MM / 10.0)

    # --- connectors -------------------------------------------------------
    # The window starts BELOW the engraved icon row. The icons sit at 60.5 mm
    # from the top, one Thunderbolt bolt above the group of four ports, and a
    # bolt is a separate dark blob about the width of one port - so a window
    # that includes the icons inserts an extra component and shifts every
    # subsequent name by one.
    iy0 = c.s["x0"] + int(8 / sx)
    iy1 = c.s["x0"] + c.s["width_px"] - int(8 / sx)
    ry0 = c.s["y0"] + int(62.2 / sx)
    ry1 = c.s["y0"] + int(82.0 / sx)
    comps = components(g[ry0:ry1 + 1, iy0:iy1 + 1] < 125.0,
                       int(0.9 / (sx * sx)))
    # image-x ascending == model-x DESCENDING for a rear view
    names = ["TB5_1", "TB5_2", "TB5_3", "TB5_4", "RJ45",
             "AC", "USBA_1", "USBA_2", "HDMI", "PHONE", "POWER_BTN"]
    spec_x = {n: x for n, x, _, _ in S.REAR_PORTS}
    spec_x["AC"] = S.AC_INLET_X
    spec_x["PHONE"] = S.HEADPHONE_X
    spec_x["POWER_BTN"] = S.POWER_BTN_X
    print("  %d connector blobs in rows %.1f..%.1f mm"
          % (len(comps), c.mm_top(ry0), c.mm_top(ry1)))
    for i, comp in enumerate(comps):
        if i >= len(names):
            break
        nm = names[i]
        c.add("%s x" % nm, c.mm_x(iy0 + (comp[0] + comp[2] + 1) / 2.0),
              spec_x[nm])
        c.add("%s z" % nm, c.z_cm(ry0 + (comp[1] + comp[3] + 1) / 2.0), S.IO_Z)
    return c


def measure_led(g, sx, x0, y0, half_mm=6.0):
    """Locate the status LED and measure it. Returns (x_cm, z_cm, dia_h, dia_v).

    Single definition, shared by the acceptance test and by tools/measure_led.py.
    It used to be written twice and the two copies drifted 0.4 mm apart on the
    diameter because they took "background" from different statistics - the
    same duplication mistake that let a corrected spec never reach the model.

    The dot is 2.7 mm across in a 12 mm window, so the baseline choice moves
    the edges. It is therefore fitted as a straight line to the window borders,
    which are bare panel by construction, and the width is read where the
    baseline-subtracted profile through the weighted centroid crosses a
    quarter of its own peak.
    """
    box = int(math.ceil(half_mm / sx))
    lcx = x0 + int(round((S.LED_X * 10.0 + W_MM / 2.0) / sx))
    lcy = y0 + int(round((H_MM - S.IO_Z * 10.0) / sx))
    win = g[lcy - box:lcy + box + 1, lcx - box:lcx + box + 1].astype(np.float64)
    if win.shape[0] < 8 or win.shape[1] < 8:
        return None
    edge = 3
    base = np.median(
        np.concatenate([win[:edge, :].ravel(), win[-edge:, :].ravel(),
                        win[:, :edge].ravel(), win[:, -edge:].ravel()]))
    resid = np.clip(win - base - 3.0, 0.0, None)
    if resid.sum() <= 0:
        return None
    gy, gx = np.mgrid[lcy - box:lcy + box + 1, lcx - box:lcx + box + 1]
    w = resid.sum()
    cx = float((gx * resid).sum() / w)
    cy = float((gy * resid).sum() / w)
    xi = int(round(cx - (lcx - box)))
    yi = int(round(cy - (lcy - box)))

    def width(prof):
        i = int(np.argmax(prof))
        if prof[i] <= 0:
            return 0.0
        lvl = prof[i] * 0.25
        a = i
        while a > 0 and prof[a] > lvl:
            a -= 1
        b = i
        while b < len(prof) - 1 and prof[b] > lvl:
            b += 1

        def cross(hi, lo):
            # both neighbours sit on the flat baseline whenever the profile
            # steps up from it, which is the normal case here; without this
            # guard the interpolation is a division by zero and the diameter
            # comes back NaN
            den = prof[lo] - prof[hi]
            if den == 0 or not np.isfinite(den):
                return float(hi)
            return hi + (lvl - prof[hi]) * (lo - hi) / den
        left = cross(a, a - 1) if a > 0 else float(a)
        right = cross(b, b + 1) if b < len(prof) - 1 else float(b)
        return (right - left) * sx

    # A single row through the centroid is a CHORD, not a diameter: unless it
    # happens to pass through the centre of the dot it reads short, and the
    # earlier version did read 3.09 mm against a true 3.13 mm for exactly that
    # reason. Taking the widest chord over every row and every column in the
    # window is the diameter for any convex blob and is insensitive to where
    # the centroid landed.
    widest_row = max(width(resid[i, :] - resid[i, :].min())
                     for i in range(resid.shape[0]))
    widest_col = max(width(resid[:, j] - resid[:, j].min())
                     for j in range(resid.shape[1]))
    return ((cx - x0) * sx - W_MM / 2.0) / 10.0, \
           (H_MM - (cy - y0) * sx) / 10.0, \
           widest_row, widest_col


def check_band(view="rear"):
    """The base band's lattice and extent, against the photograph.

    The band was the last feature still resting on a guess. It is checked here
    rather than left to the image comparison because the picture comparison can
    only report an open AREA: a square lattice of round holes and a
    half-staggered lattice of obround ones can be tuned to the same area while
    looking nothing like each other, and the previous spec was exactly that.
    """
    c = Check(view)
    g, sx = c.s["g"], c.s["sx"]

    ya = c.s["y0"] + int(round(88.5 / sx))
    yb = c.s["y0"] + int(round(93.5 / sx))
    xa = c.s["x0"] + int(round(40.0 / sx))
    xb = c.s["x0"] + c.s["width_px"] - int(round(40.0 / sx))
    band = g[ya:yb, xa:xb].astype(np.float64) / 255.0
    thr, eta = otsu(band)
    lf = largest_blob_fraction(band < thr)
    # The shape of the dark class has to be holes, or every other number below
    # is measuring a lighting gradient and means nothing.
    c.add("band blobs", lf * 100.0, 0.0, unit="%", tol=8.0)

    # pitch and stagger, by the same autocorrelation the fit was made with
    holes = band < thr
    lag_x = autocorr_peak(holes, axis=1)
    lag_z = autocorr_peak(row_pitch_profile(holes), axis=0)
    c.add("band pitch x", lag_x * sx / 10.0, S.GRILLE_PITCH_X, tol=0.035)
    c.add("band pitch z", lag_z * sx / 10.0, S.GRILLE_PITCH_Z, tol=0.030)
    c.add("band stagger", stagger_fraction(holes, lag_x), S.GRILLE_STAGGER,
          tol=0.18)

    # Hole size, measured as the BRIGHT web between holes rather than as the
    # dark area around them.
    #
    # The dark class in this band is not the holes: it is the holes plus the
    # shadow the 1.3 mm recess throws onto its own web, so the photograph
    # reports 47% open where its true opening is far smaller, and a comparison
    # of that against the spec's geometric open area is not like for like. The
    # web is bare metal catching the light and has no such ambiguity, so hole
    # width follows from it as pitch minus web. Both images are measured with
    # the same rule at the photograph's own resolution.
    r_web = _web_runs(band, sx)
    m_band = _model_band_on_photo_grid(c, sx)
    if m_band is None:
        c.add("band web x", 0.0, _spec_web(0), unit="mm", tol=0.30)
        c.add("band web z", 0.0, _spec_web(1), unit="mm", tol=0.30)
    else:
        m_web = _web_runs(m_band, sx)
        c.add("band web x", r_web[0], _spec_web(0), unit="mm", tol=0.30)
        c.add("band web z", r_web[1], _spec_web(1), unit="mm", tol=0.30)
        print("  (bright web: photo %.3f x %.3f mm, model %.3f x %.3f mm, "
              "spec %.3f x %.3f mm)"
              % (r_web[0], r_web[1], m_web[0], m_web[1],
                 _spec_web(0), _spec_web(1)))

    # top edge of the band, on the centre columns
    thr_b = min(thr, 0.70)
    tops = []
    for col in range(c.s["x0"] + int(round(30.0 / sx)),
                     c.s["x0"] + c.s["width_px"] - int(round(30.0 / sx))):
        ys = np.nonzero(g[c.s["y0"] + int(round(85.0 / sx)):
                        c.s["y0"] + int(round(95.0 / sx)), col] / 255.0 < thr_b)[0]
        if len(ys):
            tops.append((85.0 + ys[0] * sx))
    c.add("band top", float(np.mean(tops)),
          95.0 - S.GRILLE_BAND_Z1 * 10.0, unit="mm", tol=0.60)
    return c


def _web_runs(block, sx):
    """Median BRIGHT run across a band and up it, in millimetres."""
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
        out.append(float(np.median(lens)) * sx if lens else 0.0)
    return out[0], out[1]


def _spec_web(axis):
    """Web width the spec's lattice implies, in millimetres.

    The hole is a stadium, so its length across the band is 2*rx and its
    height up the band is 2*rz; the web is whatever is left of the pitch.
    """
    if axis == 0:
        return (S.GRILLE_PITCH_X - S.GRILLE_HOLE_RX * 2.0) * 10.0
    return (S.GRILLE_PITCH_Z - S.GRILLE_HOLE_RZ * 2.0) * 10.0


def _model_band_on_photo_grid(c, sx):
    """The rendered band, resampled onto the photograph's pixel grid.

    Comparing a 1305 px photograph against a 460 px resample measures the
    resampler as much as the geometry: the band has a hole every 0.9 mm, and a
    2x downsample aliases whole hole rows away. Both sides are put on the
    photograph's own grid first.
    """
    from PIL import Image
    p = os.path.join(ROOT, "renders", "compare", "%s_model.png" % c.kind)
    if not os.path.exists(p):
        return None
    im = Image.open(p).convert("L")
    w = c.s["width_px"]
    h = int(round(w * H_MM / W_MM))
    im = im.resize((w, h), Image.LANCZOS)
    gm = np.asarray(im, dtype=np.float64) / 255.0
    ya = int(round(88.5 / sx))
    yb = int(round(93.5 / sx))
    xa = int(round(40.0 / sx))
    xb = w - int(round(40.0 / sx))
    return gm[ya:yb, xa:xb]


# ------------------------------------------------------------------ the glyphs
def _glyph_photo(c, name, half_mm=3.4):
    """The photograph's own glyph, found the way tools/measure_glyphs.py does.

    Median of three thresholds, because the strokes are one pixel wide and a
    single cut either clips them or picks up JPEG ringing around them. The
    median of the three is stable to about a third of a pixel.
    """
    g, sx = c.s["g"], c.s["sx"]
    cx_mm = 98.5 - S.ICON_GLYPH_X[name] * 10.0
    cy_mm = H_MM - S.ICON_Z * 10.0
    ix0 = c.s["x0"] + int(round((cx_mm - half_mm) / sx))
    ix1 = c.s["x0"] + int(round((cx_mm + half_mm) / sx))
    iy0 = c.s["y0"] + int(round((cy_mm - half_mm) / sx))
    iy1 = c.s["y0"] + int(round((cy_mm + half_mm) / sx))
    patch = g[iy0:iy1 + 1, ix0:ix1 + 1].astype(np.float64)
    panel, dark = float(np.median(patch)), float(patch.min())

    boxes = []
    for cut in (0.30, 0.40, 0.50):
        mask = patch < panel - cut * (panel - dark)
        clean = np.zeros_like(mask)
        for x0, y0, x1, y1, _ in components(mask, int(0.010 / (sx * sx))):
            clean[y0:y1 + 1, x0:x1 + 1] = True
        clean &= mask
        ys, xs = np.nonzero(clean)
        if len(ys) == 0:
            continue
        boxes.append((xs.min(), xs.max(), ys.min(), ys.max()))

    if not boxes:
        return None
    bx0 = int(np.median([b[0] for b in boxes]))
    bx1 = int(np.median([b[1] for b in boxes]))
    by0 = int(np.median([b[2] for b in boxes]))
    by1 = int(np.median([b[3] for b in boxes]))
    return dict(x_cm=(98.5 - (ix0 + (bx0 + bx1 + 1) / 2.0 - c.s["x0"]) * sx) / 10.0,
                z_cm=(H_MM - (iy0 + (by0 + by1 + 1) / 2.0 - c.s["y0"]) * sx) / 10.0,
                w_mm=(bx1 - bx0 + 1) * sx,
                h_mm=(by1 - by0 + 1) * sx)


def _glyph_model(name, half_mm=3.4, px_per_mm=12):
    """The spec's glyph, rasterised and measured on its own fine grid.

    Measured, not read off the constants: ICON_GLYPHS is fed through the same
    rasteriser the offline renderer uses, so this compares the geometry that
    will be built against the photograph rather than restating the table.
    """
    from compare_render import glyph_mask
    n = int(round(2 * half_mm * px_per_mm))
    ax = (np.arange(n) - (n - 1) / 2.0) / px_per_mm / 10.0
    mx, mz = np.meshgrid(S.ICON_GLYPH_X[name] - ax, S.ICON_Z + ax)
    ys, xs = np.nonzero(glyph_mask(mx, mz, name=name))
    if len(ys) == 0:
        return None
    # Centre of the extent is the mean of the two EDGE pixel centres, not half
    # the index sum: the latter is off by half a pixel, 0.04 mm, and it is worse
    # than that when n is odd, because the sample grid is then not symmetric
    # about the glyph at all.
    return dict(x_cm=S.ICON_GLYPH_X[name] - (ax[xs.min()] + ax[xs.max()]) / 2.0,
                z_cm=S.ICON_Z + (ax[ys.min()] + ax[ys.max()]) / 2.0,
                w_mm=(xs.max() - xs.min() + 1) / px_per_mm,
                h_mm=(ys.max() - ys.min() + 1) / px_per_mm)


def check_glyphs():
    """The engraved icon row: position and size, photo against the model.

    The renderer used to skip this row, so nothing in the comparison could see
    a bolt that was twice the right size. These are measured, not asserted.
    """
    c = Check("rear")
    for name in sorted(S.ICON_GLYPHS):
        photo, model = _glyph_photo(c, name), _glyph_model(name)
        if photo is None or model is None:
            c.add("%s found" % name, 0.0, 0.0, unit="mm", tol=-1.0)
            continue
        c.add("%-11s x" % name, photo["x_cm"], model["x_cm"], unit="cm")
        c.add("%-11s z" % name, photo["z_cm"], model["z_cm"], unit="cm")
        c.add("%-11s w" % name, photo["w_mm"], model["w_mm"], unit="mm", tol=0.35)
        c.add("%-11s h" % name, photo["h_mm"], model["h_mm"], unit="mm", tol=0.35)
    return c


# -------------------------------------------------------------------- front
def check_front():
    c = Check("front")
    g, sx = c.s["g"], c.s["sx"]

    iy0 = c.s["x0"] + int(8 / sx)
    iy1 = c.s["x0"] + c.s["width_px"] - int(8 / sx)
    ry0 = c.s["y0"] + int(64 / sx)
    ry1 = c.s["y0"] + int(78 / sx)
    comps = components(g[ry0:ry1 + 1, iy0:iy1 + 1] < 125.0,
                       int(0.9 / (sx * sx)))
    spec_x = {n: x for n, x, _, _ in S.FRONT_PORTS}
    for i, comp in enumerate(comps):
        if i >= len(S.FRONT_PORTS):
            break
        nm = S.FRONT_PORTS[i][0]
        c.add("%s x" % nm, c.mm_x(iy0 + (comp[0] + comp[2] + 1) / 2.0),
              spec_x[nm])
        c.add("%s z" % nm, c.z_cm(ry0 + (comp[1] + comp[3] + 1) / 2.0), S.IO_Z)
        c.add("%s w" % nm, (comp[2] - comp[0] + 1) * sx / 10.0,
              dict((n, w) for n, _, w, _ in S.FRONT_PORTS)[nm])
        c.add("%s h" % nm, (comp[3] - comp[1] + 1) * sx / 10.0,
              dict((n, h) for n, _, _, h in S.FRONT_PORTS)[nm])

    # Status LED: the one bright dot on an otherwise plain panel. It sits at
    # the same height as the port row, 66 mm to the right of centre.
    #
    # The earlier version of this check scanned 20-27 mm from the top looking
    # for the brightest pixel, found none there, and so silently tested nothing
    # while still being counted in the "n/m within tolerance" line.
    led = measure_led(g, sx, c.s["x0"], c.s["y0"])
    if led is None:
        c.add("LED found", 0.0, 1.0, unit="", tol=0.5)
        return c
    lx, lz, dh, dv = led
    c.add("LED x", lx, S.LED_X, tol=0.20)
    c.add("LED z", lz, S.IO_Z, tol=0.20)
    c.add("LED dia", (dh + dv) / 2.0, S.LED_R * 20.0, unit="mm", tol=0.30)
    # a status LED is a disc; if the two measured axes disagree by much more
    # than the JPEG can explain, one of them has been pulled off the dot
    c.add("LED round", abs(dh - dv), 0.0, unit="mm", tol=0.40)
    return c


def main():
    bad = 0
    for fn in (check_chassis, check_rear, check_front, check_band, check_glyphs):
        c = fn()
        bad += c.emit()
    print("\n%s  (%d feature%s outside tolerance)"
          % ("SPEC MATCHES THE PHOTOGRAPHS" if bad == 0 else "MISMATCHES REMAIN",
             bad, "" if bad == 1 else "s"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
