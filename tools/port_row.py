#!/usr/bin/env python3
"""Close the last open residual: the port row is 2.5% more open in the model.

`region_report` has converged on one number that is not lighting and not the
perforation: the rear port row reads 41.5% dark in the render against 39.0% in
the photograph (+2.5 points), and the front port row +2.6. Every other
comparable region is inside 1.1. Positions are already verified to 0.9 mm by
tools/verify_spec.py, so the row is in the right place with each opening the
right size on paper; what is unexplained is how much of it reads as open.

The reason this file exists rather than a guess: the dark share is a RATIO, and
a ratio can be wrong for two completely different reasons that need opposite
fixes.

  A. the openings really are wider - then the spec is wrong and the fix is
     geometric;
  B. the openings are the right width but the model paints their interiors
     uniformly black while the photograph shows a lit back wall and a bright
     chamfer along each edge - then the spec is right and the fix is in how
     the offline renderer shades a cavity.

The two are told apart by one measurement that both predict differently: the
total length of DARK RUNS along the band, in millimetres. Cause A makes the
runs too long; cause B leaves the runs the right length and the share moves
anyway, because pixels just inside an opening sit on the bright side of the
threshold in the photograph and on the dark side in the render.

So this measures, per connector and for the whole row:

  * the dark runs inside the band, as run count and total millimetres;
  * the opening's own bbox from the spec, in the same millimetres;
  * the brightness of the bare panel between the openings, which is what sets
    Otsu's threshold from the bright side.

The last one matters: Otsu is fitted per region, so if the model's panel is
darker than the photograph's, the threshold moves down with it and the dark
share changes without any geometry changing at all.

Run:  python3 tools/port_row.py [rear|front]
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "blender"))
REF = os.path.join(ROOT, "reference")

import mac_studio_spec as S                    # noqa: E402
import compare_render as CR                    # noqa: E402

W_MM, H_MM = 197.0, 95.0
BAND_HALF_MM = 1.1        # region_report's port row is IO_Z +/- 1.1 mm
MARGIN_FRAC = 0.02        # ... and drops 2% of the width at each end


# ------------------------------------------------------------------ the row
def ports_of(view):
    """(name, x_cm, half_w_mm, half_h_mm) taken from the spec's own port table.

    Read from the table rather than restated so this cannot drift from the
    model. Width and height in that table are centimetres, hence x5 for a
    half-extent in millimetres; the radii are already radii, so x10.
    """
    if view == "rear":
        rows = [(n, x, w * 5.0, h * 5.0) for n, x, w, h in S.REAR_PORTS]
        rows += [("AC", S.AC_INLET_X, S.AC_INLET_W * 5.0, S.AC_INLET_H * 5.0),
                 ("PHONE", S.HEADPHONE_X, S.HEADPHONE_R * 10.0,
                  S.HEADPHONE_R * 10.0)]
        # Touch ID sits at IO_Z with the ports, so the port-row band cuts
        # straight through it. It is not a port, but it is a large dark disc in
        # that band and leaving it out makes the "sum of the opening widths"
        # below come up tens of millimetres short of either image, which then
        # looks like a modelling error in everything else.
        rows += [("TOUCHID", S.TOUCHID_X, S.TOUCHID_R * 10.0,
                  S.TOUCHID_R * 10.0)]
        return rows
    return [(n, x, w * 5.0, h * 5.0) for n, x, w, h in S.FRONT_PORTS]


# ------------------------------------------------------------- image plumbing
def _load(view, out_h=460):
    """Photograph and render, both cropped to the chassis and grey.

    The render comes back as an (H, W, 3) float array in 0..1. Handing THAT to
    numpy without converting gives an (H, W, 3) "greyscale", and any statistic
    taken over it - a percentile, an Otsu threshold, a dark share - is computed
    over three interleaved colour channels rather than over brightness. The
    percentiles then come out as per-channel values, which is how an earlier
    version of this file reported a cavity floor of 0.024 sitting BELOW a rim of
    0.024 from the same patch: those were two different channels of one pixel
    block, not two levels of a profile. Everything below is converted to "L"
    first, so both sides are the same kind of number.
    """
    ref = ("apple_hw_back.jpg" if view == "rear" else "apple_static_front.jpg")
    rp = CR.normalise_ref(os.path.join(REF, ref), out_h)
    gr = np.asarray(rp.convert("L"), dtype=np.float64) / 255.0

    arr = CR.render(view, W=760)
    box = CR.model_chassis_box(view, arr.shape[1], arr.shape[0])
    mp = CR.to_pil(arr[box[1]:box[3] + 1, box[0]:box[2] + 1])
    gm = np.asarray(mp.convert("L").resize(rp.size, Image.LANCZOS),
                    dtype=np.float64) / 255.0
    return gr, gm


def band_rows(px_h):
    """Image rows of the port-row band, for a chassis crop `px_h` tall.

    The row is addressed in millimetres above the base and converted with the
    crop's own scale, px_h / H_MM. Dividing by px_h instead is the same
    arithmetic with the two units swapped, and it collapses the band to zero
    rows because 22.4 / 460 rounds to 0 - which is how this function managed to
    hand an empty array to Otsu on the first run.
    """
    z0 = S.IO_Z * 10.0 - BAND_HALF_MM
    z1 = S.IO_Z * 10.0 + BAND_HALF_MM
    return (int(round((H_MM - z1) * px_h / H_MM)),
            int(round((H_MM - z0) * px_h / H_MM)))


def dark_runs(mask):
    """Maximal True runs of a BOOLEAN mask, as (start, end) inclusive indices.

    The argument is the mask itself, not a value and a threshold. Taking a
    threshold against a boolean array is not a no-op: `True < 0.5` is False and
    `False < 0.5` is True, so every call silently returned the COMPLEMENT. That
    is what reported the 12.4 mm RJ45 as having no opening at all and the
    14.6 mm HDMI as having none either - both are wider than the +/- 3 mm
    window, so every column in the window was open and the inverted mask came
    back empty. The band total was wrong the same way: it measured 114.8 mm of
    BRIGHT panel and printed it as open.
    """
    m = np.asarray(mask, dtype=np.int8)
    if not m.any():
        return []
    d = np.diff(np.concatenate(([0], m, [0])))
    return list(zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0] - 1))


def _load_native(view):
    """Photograph and render cropped to the chassis but NOT resampled.

    The comparison crops above are both resampled onto one common grid, and that
    is the right thing for a ratio but the wrong thing for a width: a dark
    opening has a soft edge, and resampling it - in the render's case an
    UPSCALE, since the chassis crop is narrower than the 954 px comparison -
    spreads that soft edge by about a pixel per side. At this grid a pixel is
    0.21 mm, so a 0.6 mm error is three pixels, and a per-port width read off the
    comparison grid cannot tell "the opening is 0.6 mm too wide" from "the
    resampler smeared its edge". Each image is therefore also measured on its
    own pixels, where the render's chassis crop is 0.15-0.2 mm/px and the
    photograph's is 0.151 mm/px, and a real width error would show up on both.
    """
    ref = ("apple_hw_back.jpg" if view == "rear" else "apple_static_front.jpg")
    im = Image.open(os.path.join(REF, ref)).convert("RGB")
    g = np.asarray(im.convert("L"), dtype=np.float32)
    x0, y0, x1, y1 = CR.chassis_box(g)
    pr = np.asarray(im.crop((x0, y0, x1 + 1, y1 + 1)).convert("L"),
                   dtype=np.float64) / 255.0

    arr = CR.render(view, W=760)
    box = CR.model_chassis_box(view, arr.shape[1], arr.shape[0])
    mr = np.asarray(CR.to_pil(arr[box[1]:box[3] + 1, box[0]:box[2] + 1])
                    .convert("L"), dtype=np.float64) / 255.0
    return pr, mr


def native_widths(view, ports, max_half_mm=4.0):
    """Open width per narrow connector, in mm, on each image's own pixels.

    Returns [(name, photo_mm, model_mm, spec_mm)]. Connectors wider than
    `max_half_mm` are skipped: they fill the +/- 3 mm window and the measurement
    saturates.
    """
    pr, mr = _load_native(view)
    sgn = -1.0 if view == "rear" else 1.0
    out = []
    for name, x, hw, hh in ports:
        if hw > max_half_mm:
            continue
        row = {"r": 0.0, "m": 0.0}
        for tag, g in (("r", pr), ("m", mr)):
            mm_px = W_MM / g.shape[1]
            c = (sgn * x * 10.0 + W_MM / 2.0) / mm_px
            r0, r1 = band_rows(g.shape[0])
            win = int(round(3.0 / mm_px))
            lo = max(0, int(round(c)) - win)
            hi = min(g.shape[1], int(round(c)) + win)
            blk = g[r0:r1, lo:hi]
            thr, _ = CR.otsu(blk)
            runs = dark_runs((blk < thr).mean(axis=0) >= 0.5)
            if not runs:
                continue
            # the run nearest the connector's own centre: a +/- 3 mm window on
            # a 2.6 mm opening can still catch a neighbour's edge
            mid = c - lo
            best = min(runs, key=lambda se: abs((se[0] + se[1]) / 2.0 - mid))
            row[tag] = (best[1] - best[0] + 1) * mm_px
        out.append((name, row["r"], row["m"], 2 * hw))
    return out


# ----------------------------------------------------------------- the report
def analyse(view):
    gr, gm = _load(view)
    sgn = -1.0 if view == "rear" else 1.0
    # both images were resized to the same chassis crop, so they share one
    # millimetre scale and one column origin - there is no second conversion
    # for the two sides to disagree about
    mm_px = W_MM / gr.shape[1]
    # a rear view puts model +X on the image's left
    col_of = lambda x_cm: (sgn * x_cm * 10.0 + W_MM / 2.0) * gr.shape[1] / W_MM

    r0, r1 = band_rows(gr.shape[0])
    m0, m1 = band_rows(gm.shape[0])
    mg = max(2, int(MARGIN_FRAC * gr.shape[1]))

    print("=== port row, %s view ===" % view)
    print("    %.4f mm/px, %d px wide, both images on one chassis crop"
          % (mm_px, gr.shape[1]))
    print("    band %.1f mm tall at z %.1f..%.1f mm;  bare panel (85th pct) "
          "%.3f photo / %.3f model"
          % (2 * BAND_HALF_MM, S.IO_Z * 10 - BAND_HALF_MM,
             S.IO_Z * 10 + BAND_HALF_MM,
             float(np.percentile(gr[r0:r1, mg:gr.shape[1] - mg], 85.0)),
             float(np.percentile(gm[m0:m1, mg:gm.shape[1] - mg], 85.0))))

    # --- the whole-row ratio, exactly as region_report computes it ---------
    rr = gr[r0:r1, mg:gr.shape[1] - mg]
    rm = gm[m0:m1, mg:gm.shape[1] - mg]
    tr, er = CR.otsu(rr)
    tm, em = CR.otsu(rm)
    dr = float((rr < tr).mean())
    dm = float((rm < tm).mean())
    print("    dark share   photo %.3f (thr %.3f eta %.2f)   "
          "model %.3f (thr %.3f eta %.2f)   %+.1f points"
          % (dr, tr, er, dm, tm, em, 100 * (dm - dr)))

    # --- per connector: dark runs against the spec's own opening ----------
    #
    # A column counts as OPEN when at least half the band's rows are dark.
    # Requiring every row to be dark instead - which is what this did first -
    # is far too strict and reported RJ45 and HDMI as having no opening at
    # all: both are taller than the band, and both have bright parts inside
    # them (the jack's contacts, the HDMI tongue) that lift a row or two above
    # the threshold. A real opening is not solid black all the way down.
    print()
    print("    %-8s %-25s %-25s %s"
          % ("port", "photo open  mm  lit%", "model open  mm  lit%",
             "spec opening"))
    tot = {"r": [0, 0.0], "m": [0, 0.0]}
    spec_sum = 0.0
    for name, x, hw, hh in ports_of(view):
        c = col_of(x)
        # a +/- 3 mm window: wide enough to hold the opening and the panel on
        # both sides of it, narrow enough that the neighbouring connector does
        # not leak in. The spec's self-test keeps them over 1 mm apart at the
        # closest and the widest opening here is 14.6 mm.
        lo = max(mg, int(round(c - 3.0 / mm_px)))
        hi = min(gr.shape[1] - mg, int(round(c + 3.0 / mm_px)))
        if hi - lo < 4:
            print("    %-8s  (outside the frame)" % name)
            continue
        row = {}
        for tag, g, y0, y1, t in (("r", gr, r0, r1, tr), ("m", gm, m0, m1, tm)):
            blk = g[y0:y1, lo:hi]
            open_col = (blk < t).mean(axis=0) >= 0.5
            runs = dark_runs(open_col)
            npx = float(hi - lo)
            # "lit" is the fraction of the pixels INSIDE the spec's own opening
            # that sit on the bright side of the threshold. This is the part of
            # the opening that does not read as open at all.
            ilo = int(round(c - hw / mm_px))
            ihi = int(round(c + hw / mm_px))
            ilo, ihi = max(lo, ilo), min(hi, ihi)
            inner = g[y0:y1, ilo:ihi]
            row[tag] = {
                "n": len(runs),
                "mm": sum(e - s + 1 for s, e in runs) * mm_px,
                "lit": float((inner >= t).mean()),
            }
            tot[tag][0] += row[tag]["n"]
            tot[tag][1] += row[tag]["mm"]
        spec_sum += 2 * hw
        print("    %-8s %2d runs %7.3f mm %5.1f    "
              "%2d runs %7.3f mm %5.1f    %6.3f x %6.3f mm"
              % (name, row["r"]["n"], row["r"]["mm"], row["r"]["lit"] * 100,
                 row["m"]["n"], row["m"]["mm"], row["m"]["lit"] * 100,
                 2 * hw, 2 * hh))

    # --- the whole band, decomposed --------------------------------------
    #
    # The sum of the spec's opening widths is the geometry. Whatever each
    # image's dark runs add on top of that is shading: shadow cast onto the
    # panel around the opening, or a lit interior that does not read as open.
    # Comparing the two excesses says whether the model is missing light or is
    # missing metal.
    rr_runs = dark_runs((rr < tr).mean(axis=0) >= 0.5)
    rm_runs = dark_runs((rm < tm).mean(axis=0) >= 0.5)
    ar = sum(e - s + 1 for s, e in rr_runs) * mm_px
    am = sum(e - s + 1 for s, e in rm_runs) * mm_px
    band_mm = rr.shape[1] * mm_px

    print()
    print("    whole band, %.1f mm wide (%.1f mm of chassis minus the 2%%"
          " margins)" % (band_mm, W_MM))
    print("    %-26s %9s %9s %9s"
          % ("", "open mm", "vs spec", "share"))
    print("    %-26s %9.3f %+9.3f %8.1f%%"
          % ("spec opening widths", spec_sum, 0.0, spec_sum / band_mm * 100))
    print("    %-26s %9.3f %+9.3f %8.1f%%"
          % ("photograph open", ar, ar - spec_sum, dr * 100))
    print("    %-26s %9.3f %+9.3f %8.1f%%"
          % ("model open", am, am - spec_sum, dm * 100))
    print()
    print("  narrow connectors, each image on its OWN pixels (no resampling),")
    print("  so a soft edge cannot be mistaken for a wide opening:")
    print("    %-8s %10s %10s %10s" % ("port", "photo mm", "model mm", "spec mm"))
    worst = 0.0
    for name, a, b, sp in native_widths(view, ports):
        worst = max(worst, abs(b - sp))
        print("    %-8s %10.3f %10.3f %10.3f   model %+0.3f"
              % (name, a, b, sp, b - sp))
    print("    worst model-vs-spec error %.3f mm on an image whose pixel is"
          % worst)
    print("    %.3f/%.3f mm (photo/model)"
          % (W_MM / _load_native(view)[0].shape[1],
             W_MM / _load_native(view)[1].shape[1]))
    print()
    print("    The whole-band share above is measured on a common grid, where a")
    print("    dark edge costs a pixel per side on BOTH images; the widths here")
    print("    are not affected by it and are the ones that decide whether the")
    print("    geometry is right.")
    return dr, dm


def main():
    view = sys.argv[1] if len(sys.argv) > 1 else "rear"
    analyse(view)


if __name__ == "__main__":
    main()
