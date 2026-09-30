#!/usr/bin/env python3
"""Read the internal stack out of Apple's cutaway render, in millimetres.

Every internal constant in the spec (FAN_Z, HEATSINK_Z, PIPE_Z, PCB_Z, PSU_Z,
GRILLE_BAND_Z1 ...) was placed by eye.  This measures them instead, the same way
the exterior panels were measured: find the case silhouette, convert pixels to
millimetres, then read a feature's edges off a row profile taken in an x-window
where that feature is the only thing present.

Two cautions, both real and both worth keeping in the output rather than
quietly dropping:

  * These are Apple's rendered cutaways, not photographs.  The walls are
    semi-transparent, the shading is a studio render, and there is no
    perspective correction, so a silhouette edge is soft by 2-3 px.  At
    0.297 mm/px that is +-0.9 mm per edge.  Nothing here can support the
    0.9 mm gate that the flat-lay panels pass - this is a layout check.
  * Only ONE view exists (all four files are highlight states of the same
    front cutaway), so depth is unobservable.  Everything below is a height
    and a width, never a fore/aft position.

Usage:
    python3 tools/measure_xray.py profile [window ...]
    python3 tools/measure_xray.py grid   <feature> [scale]
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))
REF = os.path.join(ROOT, "reference", "hk")

import mac_studio_spec as S                      # noqa: E402
from xray_grid import chassis_box                 # noqa: E402
from PIL import Image                              # noqa: E402

W_MM, H_MM = 197.0, 95.0
SHOT = "hw_elements_fans_xray.jpg"

# name, x0_mm, x1_mm measured from the case left edge - a window in which the
# feature is unambiguous.  Kept here rather than in the spec: these describe
# where to LOOK in the photo, not what the model is.
WINDOWS = {
    # twin blower: fins fill the whole width, nothing else does
    "blower":   (10.0, 187.0),
    # the copper / board slab runs the full width but is thin, so a wide
    # window averages away JPEG noise without mixing in other layers
    "slab":     (10.0, 187.0),
    # below the slab the left third is empty chassis, so the window sits
    # right of centre where the supply and the board actually are
    "lower":    (70.0, 190.0),
    # the floor grille is the only feature in the last 10 mm
    "grille":   (10.0, 187.0),
    # between the blowers, at the centreline: only the centre duct exists here
    "centre":   (85.0, 112.0),
}


def load(name=SHOT):
    g = np.asarray(Image.open(os.path.join(REF, name)).convert("L"),
                   dtype=np.float64) / 255.0
    x0, y0, x1, y1, h = chassis_box(g)
    crop = g[y0:y1 + 1, x0:x1 + 1]
    return crop, W_MM / crop.shape[1], h


def window_cols(crop, mm_px, a, b):
    return int(round(a / mm_px)), int(round(b / mm_px))


def edges(vals, level, lo, hi):
    """Sub-pixel crossings of `level` between indices lo and hi."""
    out = []
    for i in range(max(1, lo), min(len(vals), hi)):
        if (vals[i - 1] - level) * (vals[i] - level) < 0:
            out.append(i - 1 + (level - vals[i - 1]) / (vals[i] - vals[i - 1]))
    return out


def smooth(v, mm_px, span_mm):
    n = max(1, int(round(span_mm / mm_px)))
    return np.convolve(v, np.ones(n) / n, mode="same")


def spec_layers():
    """(label, z_cm_from_bottom, half_height_cm) exactly as the spec has them."""
    return [
        ("blower top", S.FAN_Z + S.FAN_SHROUD_H / 2, S.FAN_SHROUD_H / 2),
        ("blower axis", S.FAN_Z, 0.0),
        ("blower bot", S.FAN_Z - S.FAN_SHROUD_H / 2, S.FAN_SHROUD_H / 2),
        ("heatsink", S.HEATSINK_Z, 0.45),
        ("pipes", S.PIPE_Z, 0.35),
        ("board", S.PCB_Z, 0.25),
        ("psu", S.PSU_Z, 0.85),
    ]


def cmd_profile(argv):
    crop, mm_px, h = load()
    wins = argv or ["blower", "slab", "grille"]
    marks = {}
    for lab, z, _ in spec_layers():
        marks.setdefault((H_MM - z * 10) / mm_px, lab)
    for wname in wins:
        c0, c1 = window_cols(crop, mm_px, *WINDOWS[wname])
        inner = crop[:, c0:c1]
        edge = texture(inner)
        mean = inner.mean(axis=1)
        # rows are mm from the TOP of the case, which is how the render reads
        print("\n=== window %-7s  x %.0f..%.0f mm   %d rows @ %.4f mm/px"
              % (wname, WINDOWS[wname][0], WINDOWS[wname][1],
                 crop.shape[0], mm_px))
        print("    | texture (0-100, this window's own max) | brightness 0-100")
        for r in range(crop.shape[0]):
            mm_top = r * mm_px
            tag = ""
            for mrow, lab in marks.items():
                if abs(mrow - r) < 0.5 / mm_px:
                    tag = "  <-- spec %s @ %.1f mm" % (lab, mm_top)
            if tag or r % int(round(1.0 / mm_px)) == 0:
                t = "#" * int(round(edge[r] * 30))
                t += " " * (30 - len(t))
                print("   %5.1f |%s| %3d %s"
                      % (mm_top, t, int(mean[r] * 100), tag))


def texture(img):
    """Row-wise vertical edge energy, normalised by THIS image's own 98th pct.

    Normalising by the global max was the first mistake here: the floor grille
    has by far the strongest edges in the frame, so every row above it printed
    as an empty bar and the blower band looked like it had no texture at all.
    """
    e = np.abs(np.diff(img, axis=0, prepend=img[:1])).mean(axis=1)
    ref = np.percentile(e, 98)
    return np.clip(e / max(ref, 1e-9), 0, 1)


def cmd_bands(argv):
    """Row and column texture profiles over an explicit band, in mm."""
    crop, mm_px, h = load()
    y0, y1, x0, x1 = (float(v) for v in argv[:4])
    r0, r1 = int(round(y0 / mm_px)), int(round(y1 / mm_px))
    c0, c1 = int(round(x0 / mm_px)), int(round(x1 / mm_px))
    sub = crop[r0:r1, c0:c1]

    col = texture(sub.T)                       # column-wise, over the row band
    print("\n=== COLUMN profile  y %.1f..%.1f mm, x %.1f..%.1f mm "
          "(%d cols) ===" % (y0, y1, x0, x1, sub.shape[1]))
    for i, v in enumerate(col):
        mm = x0 + i * mm_px
        t = "#" * int(round(v * 30))
        t += " " * (30 - len(t))
        print("   x %5.1f |%s| %3d" % (mm, t, int(v * 100)))

    row = texture(sub)
    print("\n=== ROW profile  x %.1f..%.1f mm, y %.1f..%.1f mm "
          "(%d rows) ===" % (x0, x1, y0, y1, sub.shape[0]))
    for i, v in enumerate(row):
        mm = y0 + i * mm_px
        t = "#" * int(round(v * 30))
        t += " " * (30 - len(t))
        print("   y %5.1f |%s| %3d" % (mm, t, int(v * 100)))


def cmd_eq(argv):
    """Percentile-stretched zoom.  The cutaway is very dark and its fins are
    not all the same contrast, so a plain crop hides the faint half of each
    blower.  Clipping at 1-99% inside the crop and rescaling makes every fin
    visible, which is what lets the block edges be read by eye as well as
    measured."""
    from PIL import ImageDraw
    name = argv[0] if argv else "full"
    scale = int(argv[1]) if len(argv) > 1 else 3
    y0 = float(argv[2]) if len(argv) > 2 else 0.0
    y1 = float(argv[3]) if len(argv) > 3 else H_MM
    x0 = float(argv[4]) if len(argv) > 4 else 0.0
    x1 = float(argv[5]) if len(argv) > 5 else W_MM
    crop, mm_px, h = load()
    r0, r1 = int(round(y0 / mm_px)), int(round(y1 / mm_px))
    c0, c1 = int(round(x0 / mm_px)), int(round(x1 / mm_px))
    sub = crop[r0:r1, c0:c1]
    lo, hi = np.percentile(sub, 1.0), np.percentile(sub, 99.0)
    sub = np.clip((sub - lo) / max(hi - lo, 1e-9), 0, 1)
    im = Image.fromarray((sub * 255).astype(np.uint8)).convert("RGB")
    im = im.resize((sub.shape[1] * scale, sub.shape[0] * scale), Image.NEAREST)
    dr = ImageDraw.Draw(im)
    for mm in range(int(x0 // 5 * 5), int(x1) + 5, 5):
        y = int(round((mm / mm_px - y0) * scale))
        if not (0 <= y < im.height):
            continue
        dr.line([(0, y), (im.width, y)],
                fill=(0, 190, 255) if mm % 10 == 0 else (0, 110, 160))
        if mm % 10 == 0:
            dr.text((2, y + 1), str(mm), fill=(255, 255, 0))
    for mm in range(int(x0 // 5 * 5), int(x1) + 5, 5):
        x = int(round((mm / mm_px - x0) * scale))
        if not (0 <= x < im.width):
            continue
        dr.line([(x, 0), (x, im.height)],
                fill=(0, 190, 255) if mm % 20 == 0 else (0, 110, 160))
        if mm % 20 == 0:
            dr.text((x + 1, 2), str(mm), fill=(255, 255, 0))
    out = os.path.join(ROOT, "renders", "compare", "xrayeq_%s.png" % name)
    im.save(out)
    print("wrote", out, " clip 1%%=%.3f 99%%=%.3f" % (lo, hi))


def cmd_grid(argv):
    from PIL import ImageDraw
    name = argv[0] if argv else "full"
    scale = int(argv[1]) if len(argv) > 1 else 3
    crop, mm_px, h = load()
    # (row0, row1, col0, col1)
    regions = {
        "full": (0, crop.shape[0], 0, crop.shape[1]),
        "blower": (0, int(round(60 / mm_px)))
                  + window_cols(crop, mm_px, *WINDOWS["blower"]),
        "slab": (int(round(45 / mm_px)), int(round(80 / mm_px)))
                + window_cols(crop, mm_px, *WINDOWS["slab"]),
        "lower": (int(round(55 / mm_px)), int(round(95 / mm_px)))
                 + window_cols(crop, mm_px, *WINDOWS["lower"]),
        "grille": (crop.shape[0] - int(round(16 / mm_px)), crop.shape[0])
                  + window_cols(crop, mm_px, *WINDOWS["grille"]),
    }
    a, b, c, d = regions[name]
    sub = crop[a:b, c:d]
    im = Image.fromarray((sub * 255).astype(np.uint8)).convert("RGB")
    im = im.resize((sub.shape[1] * scale, sub.shape[0] * scale), Image.NEAREST)
    dr = ImageDraw.Draw(im)
    for mm in range(0, int(H_MM) + 1, 5):
        for xx in (0, crop.shape[1]):
            y = int(round((mm / mm_px - a) * scale))
            if not (0 <= y < im.height):
                continue
            col = (0, 190, 255) if mm % 10 == 0 else (0, 110, 160)
            dr.line([(0, y), (im.width, y)], fill=col)
            if mm % 10 == 0:
                dr.text((2, y + 1), str(mm), fill=(255, 255, 0))
    for mm in range(0, int(W_MM) + 1, 10):
        x = int(round((mm / mm_px - b) * scale))
        if not (0 <= x < im.width):
            continue
        col = (0, 190, 255) if mm % 20 == 0 else (0, 110, 160)
        dr.line([(x, 0), (x, im.height)], fill=col)
        if mm % 20 == 0:
            dr.text((x + 1, 2), str(mm), fill=(255, 255, 0))
    out = os.path.join(ROOT, "renders", "compare",
                       "xraygrid_%s.png" % name)
    im.save(out)
    print("wrote", out)


_MM_PX = [1.0]


def set_mm_px(v):
    _MM_PX[0] = v


def p2p(img, axis):
    """Peak-to-peak per 1 mm block along `axis`.

    Three threshold-based attempts came first and all three inherited the
    studio lighting instead of the geometry: the fins are shaded, so "brighter
    than half the peak" cuts several millimetres INSIDE the real fan at the dim
    end, and a texture-energy measure inherits the same ramp where the centre
    spine shadows the inner fins.  Peak-to-peak amplitude on a single scanline
    does not care about absolute level at all - a fin is a stripe, so it shows
    up as amplitude whatever the light is doing to it.  Mirroring about the
    case centreline then cancels the residual left-to-right gradient.
    """
    n = max(1, int(round(1.0 / _MM_PX[0])))
    m = img.shape[axis] // n
    trimmed = np.take(img, range(m * n), axis=axis)
    if axis == 1:
        return trimmed.reshape(trimmed.shape[0], m, n).max(axis=2) \
            - trimmed.reshape(trimmed.shape[0], m, n).min(axis=2)
    return trimmed.reshape(m, n, -1).max(axis=2) \
        - trimmed.reshape(m, n, -1).min(axis=2)


def runs_of(on, min_px):
    out, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j + 1 < len(on) and on[j + 1]:
                j += 1
            if j - i + 1 >= min_px:
                out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def cmd_measure(argv):
    """The definitive table: every internal feature, one stated criterion each.

    Criteria, stated so they can be argued with:

      blower x    fin field = columns whose peak brightness over rows 8..32 mm
                  beats half the band's own dynamic range.  Averaged over four
                  6 mm row bands, then each edge is a half-height crossing.
      blower y    fin field = rows whose HORIZONTAL edge energy over the fin
                  columns beats 40% of that band's 95th percentile.  Vertical
                  fins put no energy in a row max, which is why the first
                  attempt at this returned a 89 mm "fan".
      slab        the copper / logic-board stack = the one bright full-width
                  horizontal band below the blowers, found on the row mean
                  over a window that excludes the case walls.
      grille      the floor band = the same channel at the bottom of the case.

    Uncertainty: +-2 px = +-0.6 mm per edge, plus whatever the shading ramp
    adds.  Averaging the two blowers against each other is the symmetry check;
    if they disagree by more than a few mm the render's own lighting is biasing
    the edge, and the number should not be trusted to better than that.
    """
    crop, mm_px, h = load()
    set_mm_px(mm_px)
    out = {}
    mid = W_MM / 2.0

    # --- twin blowers, horizontal -------------------------------------------
    # The one criterion that worked cleanly: over the band the fans occupy,
    # a column belongs to a fan if its brightest pixel beats half that band's
    # own dynamic range.  The band is rows 8..32 mm, taken whole, because
    # narrower bands let the studio's brightness ramp decide where the edge
    # falls.  Averaged over four sub-bands and mirrored about the centreline.
    masks = []
    for y0 in (8.0, 14.0, 20.0, 26.0):
        r0, r1 = int(round(y0 / mm_px)), int(round((y0 + 6.0) / mm_px))
        b = crop[r0:r1]
        lo, hi = np.percentile(b, 2), np.percentile(b, 98)
        m = (b.max(axis=0) > lo + 0.5 * (hi - lo)).astype(float)
        masks.append(m)
    col = smooth(np.mean(masks, axis=0), mm_px, 1.5)
    on = col > 0.5
    near_runs = [r for r in runs_of(on[:len(on) // 2], 8)]
    far_runs = [r for r in runs_of(on[len(on) // 2:], 8)]
    out["near"] = (near_runs[0][0] * mm_px, near_runs[-1][1] * mm_px)
    out["far"] = ((len(on) // 2 + far_runs[0][0]) * mm_px,
                  (len(on) // 2 + far_runs[-1][1]) * mm_px)
    out["asym"] = abs((out["far"][1] - out["far"][0])
                      - (out["near"][1] - out["near"][0]))

    # --- the centre spine: a hard edge on BOTH sides ------------------------
    # Averaged over the rows the spine actually occupies. Averaged over the
    # full height it washes out completely, because the spine is absent from
    # the lower half of the machine and the dark rows dominate the mean.
    r0, r1 = int(round(3.0 / mm_px)), int(round(34.0 / mm_px))
    band = crop[r0:r1, int(round(93.0 / mm_px)):int(round(105.0 / mm_px))]
    band = band.mean(axis=0)
    xs = np.arange(len(band)) * mm_px + 93.0
    med = np.median(band)
    pk = [x for x, v in zip(xs, band) if v > med * 1.8]
    out["spine"] = (min(pk), max(pk)) if len(pk) > 1 else (None, None)

    # --- twin blowers, vertical ---------------------------------------------
    # For the vertical extent the measurement has to be ACROSS the fin columns
    # within each row, not along the rows: the fins are vertical stripes, so a
    # per-row peak-to-peak across the fin field is the signal and a per-row
    # edge energy down the column is not. (Asking p2p() for axis=0 here
    # blocked the rows instead and returned 106 bands of 3.)
    c0, c1 = int(round(18.0 / mm_px)), int(round(45.0 / mm_px))
    field = crop[:, c0:c1]
    rowp = field.max(axis=1) - field.min(axis=1)
    hi = int(round(55.0 / mm_px))
    half = rowp[:hi]
    # the fin band is far brighter than the case rim above and the open bay
    # below, so half of the band maximum brackets both edges
    e = edges(half, 0.5 * half.max(), 0, hi)
    out["fin_y"] = (e[0] * mm_px, e[-1] * mm_px)

    # --- bright horizontal layers below the blowers ------------------------
    c0, c1 = window_cols(crop, mm_px, 12.0, 185.0)
    row = smooth(crop[:, c0:c1].mean(axis=1), mm_px, 1.5)
    lo_lim, hi_lim = int(round(38 / mm_px)), int(round(80 / mm_px))
    base = np.median(row[int(round(44 / mm_px)):int(round(49 / mm_px))])
    e = edges(row, base + 0.35 * (row[lo_lim:hi_lim].max() - base), lo_lim, hi_lim)
    if e:
        out["slab"] = (e[0] * mm_px, e[-1] * mm_px)

    print("=== measured from %s, %d rows @ %.4f mm/px, case %g x %g mm ==="
          % (SHOT, crop.shape[0], mm_px, W_MM, H_MM))
    fy0, fy1 = out["fin_y"]
    fa = (fy0 + fy1) / 2
    n0, n1 = out["near"]
    f0, f1 = out["far"]
    lines = [
        ("blower fin field, near", "x %.1f .. %.1f mm  (width %.1f mm)"
         % (n0, n1, n1 - n0)),
        ("blower fin field, far", "x %.1f .. %.1f mm  (width %.1f mm)"
         % (f0, f1, f1 - f0)),
        ("blower fin field, span",
         "x %.1f .. %.1f mm overall  (robust: the field is unmistakable "
         "anywhere inside this span)"
         % (min(n0, f0), max(n1, f1))),
        ("blower width / offset",
         "near %.0f mm wide at %.0f mm, far %.0f mm at %.0f mm -- the two "
         "DISAGREE by %.1f mm, which is the honest error bar: the fins are "
         "shaded and any threshold inherits that ramp"
         % (n1 - n0, mid - (n0 + n1) / 2, f1 - f0, (f0 + f1) / 2 - mid,
            out["asym"])),
        ("blower fin height",
         "y %.1f .. %.1f mm from top -> %.1f mm tall (hard edges both ends)"
         % (fy0, fy1, fy1 - fy0)),
        ("blower axis",
         "%.1f mm from top -> z %.2f cm from the floor" % (fa, (H_MM - fa) / 10)),
    ]
    if out["spine"][0] is not None:
        s0, s1 = out["spine"]
        lines.append(
            ("centre spine",
             "x %.1f .. %.1f mm -> %.1f mm wide, centred %.2f mm from the "
             "case centre (hard edge on BOTH sides)"
             % (s0, s1, s1 - s0, (s0 + s1) / 2 - mid)))
    for lab, val in lines:
        print("   %-24s %s" % (lab, val))
    if "slab" in out:
        s0, s1 = out["slab"]
        print("   %-24s y %.1f .. %.1f mm from top -> z %.2f cm"
              % ("bright slab below fans", s0, s1, (H_MM - (s0 + s1) / 2) / 10))
    print("\n   spec now: FAN_X %.2f cm  FAN_SHROUD_W %.2f cm  "
          "FAN_SHROUD_H %.2f cm  FAN_Z %.2f cm  SPINE_W %.2f cm"
          % (S.FAN_X, S.FAN_SHROUD_W, S.FAN_SHROUD_H, S.FAN_Z, S.SPINE_W))


if __name__ == "__main__":
    if not sys.argv[1:]:
        print(__doc__)
        raise SystemExit(0)
    if sys.argv[1] == "profile":
        cmd_profile(sys.argv[2:])
    elif sys.argv[1] == "bands":
        cmd_bands(sys.argv[2:])
    elif sys.argv[1] == "grid":
        cmd_grid(sys.argv[2:])
    elif sys.argv[1] == "eq":
        cmd_eq(sys.argv[2:])
    elif sys.argv[1] == "measure":
        cmd_measure(sys.argv[2:])
    else:
        print(__doc__)
        raise SystemExit(2)
