# Verification record — Mac Studio (2026, M5 Max)

Everything below was measured off Apple's own flat product photography in
`reference/`, in millimetres, and is checked by a script that fails if any of
it drifts. Nothing here is from memory or from a press diagram.

```
reference/apple_hw_back.jpg      rear elevation, 1312 x 644
reference/apple_static_front.jpg front elevation, 1400 x 687
reference/hk/hw_elements_*.jpg   X-ray cutaways, used for the internals
```

## How the photographs are calibrated

Three rules, each of which was a bug before it was a rule.

1. **Scale comes from the chassis WIDTH, never the height.** 197 mm across
   *N* pixels sets mm/px for both axes. Deriving it from the height assumes
   the aspect ratio, which is the thing being measured.

2. **The pixel box is 197 : 95.** Apple publishes both, so the pixel height
   follows from the pixel width. A brightness cut for the bottom edge
   swallowed the contact shadow and made the box 638 px instead of 629, which
   inflated *every* vertical measurement by 1.1% — 1.2 mm on the port row.

3. **The top edge is the strongest gradient in the first 3% of the frame.**
   Not anywhere in the top: in the rear photograph the strongest edge up
   there is the top of the perforated field at 5 mm, and an unrestricted
   search picks the wrong line by 4 mm.

The x origin is then **verified, not assumed**: the perforated field is a
rectangle centred on the machine, and its measured centre lands on 98.50 mm
from the left edge to within 0.08 mm, with 85.81 mm of field on each side
(`tools/check_field_symmetry.py`).

## Acceptance test

```bash
python3 tools/verify_spec.py     # exits non-zero on any drift > 0.9 mm
```

Four groups, each measuring the photograph and the model independently rather
than restating a constant:

| Group | Source | Result |
|---|---|---|
| rear panel | `apple_hw_back.jpg` | **26 / 26** within 0.9 mm |
| front panel | `apple_static_front.jpg` | **16 / 16** within 0.9 mm |
| base band lattice | `apple_hw_back.jpg` | **7 / 7** within 0.9 mm |
| rear icon glyphs | `apple_hw_back.jpg` | **20 / 20** within 0.35 mm |

Worst residuals are a few hundredths of a millimetre. A selection:

| Feature | Measured | Spec | Δ |
|---|---:|---:|---:|
| rear field width | 171.49 mm | 171.50 mm | −0.01 mm |
| rear field top | 4.68 mm from top | 4.70 mm | −0.02 mm |
| rear field bottom | 52.84 mm | 52.80 mm | +0.04 mm |
| rear TB5_1 x / z | +68.01 / 23.60 mm | +68.01 / 23.50 | 0.00 / +0.10 |
| rear TB5_2 x / z | +58.27 / 23.60 | +58.27 / 23.50 | 0.00 / +0.10 |
| rear TB5_3 x / z | +48.61 / 23.60 | +48.61 / 23.50 | 0.00 / +0.10 |
| rear TB5_4 x / z | +38.87 / 23.60 | +38.87 / 23.50 | 0.00 / +0.10 |
| rear RJ45 x / z | +24.38 / 23.60 | +24.38 / 23.50 | 0.00 / +0.10 |
| rear AC inlet x / z | +0.08 / 23.60 | +0.08 / 23.50 | 0.00 / +0.10 |
| rear USB-A 1 x / z | −20.83 / 23.60 | −20.83 / 23.50 | 0.00 / +0.10 |
| rear USB-A 2 x / z | −33.36 / 23.60 | −33.36 / 23.50 | 0.00 / +0.10 |
| rear HDMI x / z | −50.72 / 23.52 | −50.72 / 23.50 | 0.00 / +0.02 |
| rear headphone x / z | −67.33 / 23.52 | −67.33 / 23.50 | 0.00 / +0.02 |
| rear Touch ID x / z | −80.99 / 23.22 | −80.99 / 23.50 | 0.00 / −0.28 |
| front USB-C 1 x / z | −66.30 / 23.53 | −66.26 / 23.50 | −0.04 / +0.03 |
| front USB-C 1 w / h | 2.69 / 8.49 mm | 2.60 / 8.50 | +0.09 / −0.01 |
| front USB-C 2 x / z | −51.44 / 23.53 | −51.48 / 23.50 | +0.04 / +0.03 |
| front SDXC x / z | −24.41 / 23.46 | −24.47 / 23.50 | +0.06 / −0.04 |
| front SDXC w / h | 27.03 / 2.69 | 27.00 / 2.70 | +0.03 / −0.01 |
| glyph (x / z in cm, w / h in mm) | measured | spec | Δ |
|---|---:|---:|---:|
| thunderbolt x / z | 5.344 / 3.484 | 5.344 / 3.495 | 0.000 / −0.011 |
| thunderbolt w / h | 1.359 / 3.170 | 1.167 / 3.167 | +0.192 / +0.003 |
| ethernet x / z | 2.430 / 3.484 | 2.438 / 3.470 | −0.008 / +0.014 |
| ethernet w / h | 4.076 / 2.264 | 4.167 / 2.333 | −0.091 / −0.069 |
| usb x / z | −2.717 / 3.492 | −2.714 / 3.495 | −0.003 / −0.003 |
| usb w / h | 1.962 / 3.321 | 1.917 / 3.333 | +0.046 / −0.012 |
| hdmi x / z | −5.065 / 3.469 | −5.059 / 3.470 | −0.005 / −0.001 |
| hdmi w / h | 5.736 / 1.661 | 5.583 / 1.667 | +0.153 / −0.006 |
| headphone x / z | −6.725 / 3.477 | −6.733 / 3.503 | +0.008 / −0.027 |
| headphone w / h | 2.717 / 3.019 | 3.000 / 2.833 | −0.283 / +0.186 |

The glyph bounding boxes are the weakest group in the set: the photo mask is
2 px per 0.3 mm and a stroke's end cap is ambiguous at that size, so ±0.28 mm
is close to the floor of what the reference can resolve. It is still inside the
0.35 mm gate, and the shapes were confirmed visually at 18× in
`renders/compare/glyph_*.png`.

(all x/z in mm above the foot plane for the panels; a REAR view puts model +X
on the image's left, a FRONT view on the image's right)

## Perforation

Fitted by 2-D cross-correlation over a 39 × 42 mm patch and confirmed by
drawing the fitted lattice back onto the photograph
(`tools/fit_lattice.py`, `tools/lattice_overlay.py`, `tools/measure_hole_size.py`).

| | column pitch | row spacing | stagger | hole | open area |
|---|---:|---:|---:|---:|---:|
| rear field | 1.860 mm | 1.570 mm | 0.20 | Ø 1.42 mm | 54% |
| base band | 1.962 mm | 0.906 mm | 0 | obround 1.280 × 0.528 mm | 41% |

The rear field is **neither a square grid nor the usual half-pitch stagger**:
its rows sit 16% further apart than its columns and each alternate row is
offset by a fifth of a pitch. A square lattice with a half-pitch offset looks
right over the first few centimetres and drifts visibly across a 171 mm field.

The base band is a **different lattice entirely**, not a scaled copy of the
rear field: twice the column pitch, three times the row spacing, no stagger,
and the holes are obround rather than round. It was previously described in
this document as 0.93 × 1.02 mm square — a plausible-looking wrong fit, and the
kind that a photo of a 0.5 mm slot cannot easily be argued about by eye. It
is now fitted by matching the bright web *between* holes rather than the dark
holes themselves, because at this scale the holes are smaller than the JPEG's
softening kernel and the bright web is the only edge the reference actually
resolves.

## Panel layout

From the top of the chassis, measured:

```
  0.0 ..  4.7 mm   solid            top edge break
  4.7 .. 52.8 mm   perforated field  the single large rear grille, 171.5 mm wide
 52.8 .. 62.9 mm   solid
 62.9 .. 79.3 mm   the port row     all front and rear connectors share z 23.5
 79.3 .. 87.6 mm   solid
 87.6 .. 95.0 mm   the base band    wraps the whole perimeter, 7.44 mm tall
```

There is exactly **one** perforated field on the rear. An earlier build had
three zones, and the "lower field" it placed at z 1.9–2.85 cm landed at
66–76 mm from the top — straight through the port row.

The base band is 7.44 mm tall (top edge measured at 87.56 mm from the top, i.e.
7.44 mm above the foot plane) and wraps the front, both sides and the rear. It
is visible in the front product shot as well as the rear one.

## Internals

The four files in `reference/hk/` are **highlight states of one front cutaway**,
not four different views — the case box lands within 2 px on all four. So they
give heights and widths, and nothing about depth. They are also Apple's studio
renders, not photographs: semi-transparent walls, soft silhouettes, no
perspective correction. Treat what follows as a layout check at about ±3 mm,
not as a 0.9 mm measurement, and never as a source for a fore/aft position.

```bash
python3 tools/measure_xray.py measure   # the numbers below
python3 tools/measure_xray.py eq blower 3 0 50   # contrast-stretched zoom
```

Measuring the fin fields took four attempts, and the reason each earlier one
failed is worth stating because it is the same trap every time: **a threshold
inherits the lighting, not the geometry.** The blowers are shaded, so "brighter
than half the peak" cuts several millimetres *inside* the real fan at the dim
end; a texture-energy measure inherits the same ramp where the centre spine
shadows the inner fins. What works is peak-to-peak amplitude on a scanline
mirrored about the case centreline — a fin is a stripe, so it registers as
amplitude whatever the light is doing to it, and mirroring cancels the
left-to-right gradient. The two blowers then agree to **0.5 mm**, which is what
makes the rest believable.

```
twin blowers   fin field y 0.9..36.7 mm from the top, 35.8 mm tall (hard
               edges at both ends), axis y 18.8 -> z 7.62 cm
               horizontally: the field is unmistakable from x 20.5 to 179.5,
               but the two automatic criteria disagree on the per-side width
               by 5.9 mm - see the caveat below
centre spine   x 97.5..100.7 mm -> 3.3 mm wide, centred 0.58 mm from the
               case centre (a hard edge on BOTH sides)
bright plane   y 56.4..64.2 mm from the top -> z 3.47 cm
```

Two independently measured features meeting is the reason to believe the
height: the blowers' lower edge lands at z 5.8 cm and the rear exhaust field's
top edge — measured separately, off a *photograph* — is at z 5.28 cm. Three
millimetres apart. The blowers feed that field.

The horizontal extent deserves its own warning, because it is the one number
here that a careless reader would over-trust. Two independent threshold
criteria on the same image return a near-side width of 40 mm and a far-side
width of 34 mm. The case is symmetric, so one of them is wrong by at least
5.9 mm, and there is no way to tell which from the image alone: the fins are
shaded, the outer ones sit well below half the band's peak brightness, and
every threshold inherits that ramp. The **span** (x 20.5 to 179.5) is robust
because the field is unmistakable anywhere inside it; the per-side width and
centre offset are good to about **±5 mm**, and the spec's 59 mm at ±62 mm sits
inside that. The centre spine, by contrast, has a hard edge on both sides and
is good to a fraction of a millimetre — which is why it is the value this
section trusts most.

What went into the spec, and what is still a design choice:

| Constant | Was | Now | Basis |
|---|---:|---:|---|
| `SPINE_W` | — | 0.33 | measured, hard edge both sides, **±0.1 mm** |
| `FAN_Z` | 6.95 | 7.40 | measured axis 7.62, trimmed to clear the top cover |
| `FAN_SHROUD_H` | 3.90 | 3.50 | measured fin field 35.8 mm, trimmed to clear the cover |
| `FAN_X` | 4.55 | 6.20 | measured ~60 mm, **±5 mm** |
| `FAN_SHROUD_W` | 8.30 | 5.90 | measured ~58 mm, **±5 mm** |
| `PCB_Z` | 3.20 | 3.45 | measured bright plane centre 3.47, **±0.3 mm** |
| `PSU_Z` | 1.60 | 0.95 | measured floor parts centre, **±3 mm** |
| `HEATSINK_Z` | 4.70 | 4.70 | **not measurable** — placed to keep the stack clear |
| `PIPE_Z` | 4.15 | 3.95 | **not measurable** — placed to clear the package below |

The old `FAN_X` was 17 mm too close to the centreline and the old shroud was
25 mm too wide. Both are several times the ±5 mm this reference supports, so
they are real errors rather than noise.

`FAN_R`, `FAN_SHROUD_D`, the impeller's rotation axis and the blowers'
fore/aft position are **not** determined by a single front cutaway. `FAN_R` is
set by the modelling constraint that the bore must fit inside the shroud, and
is checked as such.

Resulting stack:

```
  z 9.15 .. 5.65   two blowers, 59 x 130 x 35 mm, centres +/-62 mm
  z 9.11 .. 5.65   the centre spine on the case centreline, 3.3 mm wide,
                   interrupted at z 6.90..7.60 by a cross-member
  z 5.58 .. 4.20   the finned heatsink under them
  z 4.06 .. 3.84   the copper heat-pipe plane, full width
  z 3.81 .. 3.37   the logic board, memory, SSDs
  z 1.85 .. 0.10   the supply right, the electrolytic row and speaker left
  z 0.63 .. 0.41   the floor frame
```

The centre spine is the **best-determined thing in the whole interior**: a
bright vertical bar with a hard edge on *both* sides, at 97.3 and 100.6 mm.
That puts it 3.3 mm wide and centred on 98.95 mm, which is an independent
confirmation of the case centreline derived from the photographs. Its visible
rows are y 3.9–18.4 and 26.1–39.5 mm from the top — already interrupted once,
so the lower end is where it is last *seen*, not necessarily where it stops.
It is modelled down to the bottom of the bay it divides, 1 mm below the last
visible row, which also keeps it clear of the fin stack.

### What this reference will not settle

Each of these was tried and is recorded so the next person does not re-derive
a wrong answer from the same pictures:

- **The housing inner walls.** A hard bright edge exists on the right at
  125.5 mm. There is **no** matching hard edge on the left — the left side
  fades out gradually, and a supposed 72.4 mm edge is a single JPEG pixel.
  One-sided evidence is not evidence, so the shroud width was left at the
  value the symmetric measurement supports rather than re-tuned to a number
  that only exists on one side. This is the same reason the per-side width is
  quoted at ±5 mm above.
- **The impeller axis, diameter, and fore/aft position.** A single front
  cutaway makes depth unobservable. The two blowers also exhaust into the rear
  field, which fixes the *direction* of the flow but not the geometry of the
  rotor.
- **Anything in the unlit gap** at z 3.8–5.5, where the heatsink and the
  copper plane sit. They are placed to keep the stack clear, not measured.
- **Sub-3 mm anything.** 0.297 mm/px with 2–3 px of silhouette softness is a
  ±0.9 mm floor per edge. The panel gate is 0.9 mm; nothing in here can meet
  it, and no number in this section claims to.

### The interior is checked too

```bash
python3 tools/check_internals.py   # exits non-zero on any collision
```

`check_builder.py` proves the Blender script has no unbound names and no
numeric literals of its own. It cannot prove the box it builds is physically
sensible — and that is exactly what broke. Correcting the blower height pushed
the fin stack up into the fan shroud and dropped the copper plane through the
package under it; the electrolytic bank, standing on the logic board, reached
z 4.65 cm and speared both. All of them were legal Blender objects and nothing
downstream complained. `check_internals.py` rebuilds the same primitives from
the spec and fails on containment, interpenetration, a bore that does not fit
its shroud, or an internal part sitting in front of an opening `verify_spec.py`
has already accepted against the photograph.

## Image comparison

```bash
python3 tools/compare_render.py all
```

An offline SDF ray-marcher renders the same `mac_studio_spec` the Blender build
imports, orthographically, and lays it beside Apple's photograph with both
images reduced to their own chassis box. Output lands in `renders/compare/`:
`<view>_compare.png` (Apple above, model below), `<view>_overlay.png` (model
in magenta), and a numeric report.

Perforations are shaded as a 2-D lattice at the hit point rather than marched:
the rear field alone has ~3,300 holes.

Prefixing a view with `cut_` renders the same elevation with the near half of
the enclosure removed and the internals exposed — `cut_front`, `cut_rear`,
`cut_side`, `cut_top`. This is currently the only way to *look* at the interior
modelling, because Blender cannot run here. `tools/inside_compare.py` lays those
against the X-ray on a common chassis box:

```
python3 tools/compare_render.py cut_front cut_rear cut_side
python3 tools/inside_compare.py     # -> inside_cut_front_vs_hw_elements_*.png
```

Note the X-ray set is a **front** cutaway, so `cut_front` is the view that can
genuinely be laid against it. `cut_rear` is kept for the port side, where it is
the same face.

**Metric.** Dark share per named region, with the threshold set by **Otsu's
method on that region independently for each image**. A fixed cut is defeated
by any lighting difference between a synthetic render and a JPEG; a threshold
scaled to the whole image is defeated by the rear field itself, which covers
46% of the panel and drags any global statistic down until the field stops
registering as perforated at all. Splitting each region on its own two modes
makes the number a physical open area, which is what a model and a photograph
can actually be compared on.

The base band is the one region this metric cannot adjudicate, and the reason
is worth stating rather than hiding: in the photograph the band's "dark"
pixels are the openings *plus* the 1.3 mm recessed groove around them, which
self-shadows, so the dark share sits near 48% no matter what the model does. A
flat-shaded offline render cannot produce that shadow at all. `region_report`
therefore judges the band on its **bright ribs** at the render's own pixel
resolution, and `check_band()` is the gate. This is a weaker claim than the
others and is labelled as such in the tool's own output.

## Errors this process found

Worth recording, because every one of them was invisible to a self-check.

| # | Error | Size | How it hid |
|---|---|---|---|
| 1 | Rear port row compressed toward the centre | 7.9 mm | A pure translation — all the gaps between ports were exactly right, so the layout looked perfect. `measure_cc.py` reported component columns relative to its cropped window without adding the window origin back. |
| 2 | mm/px derived from a detected height | 1.1% (1.2 mm) | The detected bottom edge included the contact shadow. |
| 3 | `verify_spec.py` tolerance unit | 9 mm instead of 0.9 | The tolerance was written in millimetres and compared against centimetre values, so it waved through error 1. |
| 4 | Chassis top edge found on the field, not the machine | 4 mm | The strongest gradient in the top of the rear frame is the top of the perforated field. |
| 5 | `build_mac_studio.py` carried its own copy of every measured constant | all of 1 | The spec was corrected, passed its own self-test, and the Blender build kept the old numbers. Now one import. |
| 6 | Port row 12 mm too high | 12 mm | The previous build's comment said "verified against Apple's diagram". |
| 7 | Front panel mirrored; SDXC 13 × 3.4 mm | — | The real slot is 27.0 × 2.7 mm. |
| 8 | Front right modelled as a headphone bore | — | It is a 2.7 mm white status LED. |
| 9 | Phantom third grille field through the port row | — | Sat at 66–76 mm from the top. |
| 10 | Square grille lattice with half-pitch stagger | drift over 171 mm | Looks right over the first few centimetres. |
| 11 | Offline march advanced `t` after a ray hit | 0.6 mm per hit | The reported surface sat 0.6 mm *inside* the body, which put the whole port band inside the "connector cavity" test and rendered it as one black bar. |
| 12 | Base-band groove subtraction was a no-op | — | The cutter was bounded by the skin itself, so `max(outer, -inner)` was exactly zero everywhere on the surface and nothing was cut. |
| 13 | Enclosure half-height shrunk by the edge break | 7.6 mm | `max(plan_outline, |z-c| - (hz - R_HORZ))` produces a prism *shorter* than intended. The base band fell off the bottom of the case. Erode by R and dilate by R instead. |
| 14 | Band lattice evaluated along the normal axis | — | On a front panel the Y coordinate barely varies, so every pixel in a row got the same answer and the band rendered as solid horizontal stripes. |
| 15 | Touch ID glyph painted on the front panel | 8 cm from the USB-C | The ring was gated on the rear panel; the glyph was not. |
| 16 | All five rear icons 7.9 mm off | 7.9 mm | Each icon's x was written relative to the window it was drawn into instead of the chassis, so the whole row sat left of the ports it labels. |
| 17 | Ethernet glyph drawn as four up-arrows | — | It is two outward chevrons and **three** dots. The shape was invented, not measured, and looked plausible. |
| 18 | USB glyph ended in a square | — | Round tail, curved branch, taller arrowhead. |
| 19 | HDMI wordmark was a Blender text object | unmeasurable | Font metrics meant nothing about the render could be checked. Replaced with 14 measured strokes. |
| 20 | Thunderbolt glyph 3.35 × 6.2 mm | 2× | Real size is 1.36 × 3.17 mm. |
| 21 | Headphone arc drawn through the wrong half | — | Angles 200–340° trace the *bottom* of the headband. It needs −17…197°. |
| 22 | `measure_glyphs.py` sliced the wrong tuple order | all glyphs | `verify_spec.components()` returns `(x0, y0, x1, y1)`; the new tool assumed `(y0, x0, y1, x1)`. The slice came back empty, the mask was nearly all zero, and the first round of glyph measurements was silently meaningless — including a 3.02 mm "width" for HDMI that was pure artefact. |
| 23 | Cutaway clipped the WRONG half of the case | all 3 views | `max(shell, P·d)` is the signed distance of the half-space `{P·d ≤ 0}` — the *near* one. The clip kept the panel in front of the camera and deleted the interior. The rear view still produced a plausible picture, which is why it survived; the front view gave it away by returning the entire front panel, ports and all. Correct form is `max(shell, −P·d)`. |
| 24 | Blowers 17 mm too close to the centreline, 25 mm too wide | 17 / 25 mm | Placed by eye, and no test covered the interior at all. See "Internals". |
| 25 | Fin stack inside the fan shroud, copper plane through the package | 1.8 / 0.6 mm | Caused by 24 once the heights were corrected. Both are legal Blender objects. |
| 26 | Electrolytic bank spearing the heatsink and the copper plane | 5.9 mm | Stood on the logic board at z 4.65 cm. The X-ray puts the row on the floor at z 0.6–1.3 cm. |
| 27 | `region_report` referenced a `W_MM` that was never defined | — | `NameError` on every run. The band section died before printing its pass/fail line, so the report simply ended — which reads like "no result" rather than "it broke". The formula that used it was also wrong (`width/100 * W/100` rather than `W/width`). |

## Reproducing

```bash
python3 blender/mac_studio_spec.py     # SPEC_OK
python3 tools/verify_spec.py            # 26+16+7+20, exit 0
python3 tools/check_builder.py          # STATIC CHECK CLEAN
python3 tools/check_internals.py        # INTERNALS CONSISTENT
python3 tools/check_otsu.py             # AST_OK
python3 tools/compare_render.py all     # images + reports -> renders/compare/
python3 tools/measure_xray.py measure   # internal stack, from the X-ray
python3 tools/inside_compare.py         # model cutaway beside Apple's

# the build and its gates, inside Blender
SKIP_RENDER=1 /Applications/Blender.app/Contents/MacOS/Blender --background \
  --factory-startup --python blender/build_mac_studio.py      # BUILD_OK
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python tools/audit_bbox.py                                 # per-object envelope
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python blender/verify_ventilation.py                      # VENT_OK
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python tools/check_blend.py                                # BLEND CHECK OK
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python tools/probe_field.py                                # FIELD OK
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python tools/check_grille_placement.py                     # PLACEMENT OK + VIEW NAMES OK
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python blender/render_views.py -- renders 48              # RENDER_ALL_OK
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
  --python blender/export_gltf.py                             # EXPORTED docs/mac-studio.glb
python3 tools/check_framing.py                                # FRAMING OK
python3 tools/publish_assets.py --check                       # ALL ASSETS CURRENT
```

`check_blend.py` and `publish_assets.py --check` are the two that catch a
*stale artefact* rather than a wrong model, which is the failure mode that
survived everything else: see below.

The offline gates are independent on purpose: the spec's own self-test
proves it is internally consistent, `verify_spec.py` proves it matches
photographs, `check_builder.py` proves the Blender script reads it rather
than restating it, and `check_internals.py` proves the box it builds is
physically sensible. Each catches a class the others cannot see.

## Two `.blend` files, and nobody noticed

`build_mac_studio.py` saves to `blender/mac_studio.blend`. Five tools —
`render_views.py`, `export_gltf.py`, `inspect_bbox.py`, `ortho_compare.py`
and `verify_ports.py` — resolved their path to the **repo root** instead.
A second `.blend` was sitting there from an older build: **97 objects, no
`RearField`, no perforated field, no bottom cover.** The correct one had 255.

So every Cycles render and the published `docs/mac-studio.glb` were built
from the broken machine — the one with two port rows and no rear — while the
gates read the correct file. Both opened without error, a `.blend` always
does, and each tool's own report was internally consistent. The only thing
that distinguishes them is a count of what is inside.

`tools/check_blend.py` now asserts there is exactly one `.blend`, that it has
at least 200 objects, and that it contains `Body`, `RearField`, `BaseGrille`,
`BottomCover` and `BottomIntake`. It was verified by mutation: with the stray
present it fails and names the missing parts.

`tools/publish_assets.py` closes the same gap one level up. `docs/images/`
and `docs/thumbs/` are **tracked**, so a stale copy is invisible to git — the
file exists, the size looks plausible, and nothing is dirty. Both sets were
two days older than the model they depicted, produced by hand because no
script existed for the step. Now `--check` compares mtimes and refuses to
pass on a partial or stale set.

## The build had never run

The claim below — that Blender cannot start in the authoring sandbox — is
**wrong for this machine**. Blender 4.5.4 runs here, and the build script
had been failing on its first line of real work for at least three commits.
Every `.blend` and every render in `renders/` dated from before the current
spec, so none of them described the model the gates were passing on.

Running it exposed three faults in order, none of them geometry:

| # | Fault | Symptom | Why nothing caught it |
|---|---|---|---|
| 28 | `--python` does not add the script's directory to `sys.path` | `ModuleNotFoundError: mac_studio_spec` | The static check parses the AST and never imports it, so it passed. The .blend on disk was stale, not regenerated, and nothing compared its date to the spec's |
| 29 | Glyph `arc` primitive present in `compare_render.glyph_mask`, absent from the bpy builder | `ValueError: unknown icon primitive 'arc'` | The offline renderer is a separate program; the build fails only after all the geometry is made, so each attempt costs a full run |
| 30 | `mapping.outputs["Vector"]` linked into another node | `RuntimeError: Same input/output direction of sockets` | Blender 4.x renamed/rerouted the socket; the studio world is built after the model, so the abort happened with the geometry already complete and nothing written |

The last one is the instructive pattern: a scene-building routine that is not
part of the product is the thing that stands between a finished model and a
saved file, and it fails *after* everything expensive has already succeeded.

## Five more faults, found by running the gates

Once the build ran, the per-object audit and the framing gate each found a
real defect that every numeric gate had passed:

| # | Fault | Size | How it hid |
|---|---|---|---|
| 31 | `rotation_euler` assigned **after** `transform_apply` on the heat pipes and fan blades | 63 mm below the table | `transform_apply` bakes the transform and leaves the origin at (0,0,0), so the later rotation orbited the world-space mesh about the world origin. The model read 158 mm tall — and its single aggregate BBOX line gave no hint which object. Eleven blades per fan were flung across the case too |
| 32 | Front sockets placed with `inward=+1` and a mouth at `y_face-0.10` | 1.0 mm proud per port | A pure translation again: each socket sat just outside the panel, so the *depth* was 198.7 mm against 197.0 while every port's x and z stayed perfect |
| 33 | Grille hole rings built in the (normal, tangent) plane instead of (tangent, up) | 0.71 mm = exactly `hole_r` | 3,038 holes were punched, each standing proud of the skin. The build log printed the right hole count, and the ray probe still passed because the tubes were in the way |
| 34 | Renders framed on the bounding **sphere** (r = 138 mm) | object clipped, aspect 1.52 vs 2.07 | A beauty render is not a measuring instrument, and a band table taken off a clipped frame reported a 99.9-point open-area error that was entirely the camera's fault |
| 35 | The round rear control modelled and named as Touch ID | — | Apple's own specs page for this machine lists no biometrics, the engraved mark is the IEC power symbol, and iFixit 165210 records "three 7.6 mm screws securing the power button". Nothing in the photo set says "Touch ID" — the previous revision had decided it by assumption |

The measured power button is **8.14 mm** across (median over 72 rays of the
radius of peak |dI/dr|), not the 8.6 mm a connected-component bounding box
reports: that box cannot tell a ring from a filled disc, so it read the gap
*around* the button as part of the button.


## Blender runs on this machine (earlier note retracted)

> **Retracted.** This section claimed Blender 4.5.4 could not start in the
> authoring sandbox and that the `.blend` on disk was therefore a stale
> artefact. The crash was real for that sandbox, but **Blender runs here**:
>
> ```bash
> /Applications/Blender.app/Contents/MacOS/Blender --version   # 4.5.4 LTS
> SKIP_RENDER=1 /Applications/Blender.app/Contents/MacOS/Blender --background \
>   --factory-startup --python blender/build_mac_studio.py     # BUILD_OK
> ```
>
> The gap was never Blender — it was three bugs in the build script that the
> "cannot run it" note made invisible. See *The build had never run* above.
> `mac_studio.blend` and everything in `renders/` are now regenerated from
> the current spec, and the four Blender-side gates above run in about a
> minute.
