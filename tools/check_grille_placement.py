"""A grille is on the face it was named for, and nowhere else.

The rear perforated field was being built on the FRONT panel, for a whole
session, while still being called "RearField" and still printing a plausible
hole count. Nothing caught it: the log was right, the object name was right,
and the only symptom was dark horizontal bands in the front render that
Apple's front panel does not have.

So this gate asserts placement directly, in millimetres, from the built
blend - not from the source, because the source of a sign error looks
perfectly reasonable.

usage: blender --background --factory-startup --python tools/check_grille_placement.py
"""
import math
import os
import re
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "blender"))
import mac_studio_spec as S  # noqa: E402

BLEND = os.path.join(ROOT, "blender", "mac_studio.blend")
TOL = 0.02          # cm: how far onto the wrong face counts as "on it"


def span(obj):
    ws = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return (min(w.x for w in ws), max(w.x for w in ws),
            min(w.y for w in ws), max(w.y for w in ws),
            min(w.z for w in ws), max(w.z for w in ws))


def main():
    bpy.ops.wm.open_mainfile(filepath=BLEND)
    d2 = S.D / 2.0
    names = {o.name: o for o in bpy.context.scene.objects if o.type == "MESH"}
    bad = []

    print("chassis: W %.1f  D %.1f  H %.1f mm   (+Y = FRONT, -Y = REAR)"
          % (S.W * 10, S.D * 10, S.H_TOTAL * 10))
    print()
    print("%-12s %-24s %s" % ("object", "measured y span (mm)", "verdict"))
    print("%-12s %-24s %s" % ("", "", ""))

    for nm, want, label in (("RearField", "rear", "rear perforated field"),
                            ("BaseGrille", "both", "base band (wraps)")):
        o = names.get(nm)
        if o is None:
            bad.append("%s is missing entirely" % nm)
            print("%-12s %-24s %s" % (nm, "-", "MISSING"))
            continue
        _, _, y0, y1, _, _ = span(o)
        f, b = y0 * 10, y1 * 10
        # Work in CM to match the spec and the object data exactly. A
        # millimetre-scale float comparison put the field's rear edge at
        # exactly -98.5 and the tolerance test landed on the boundary, which
        # reported a correctly-placed object as misplaced.
        rear_face, front_face = -S.D / 2.0, S.D / 2.0
        if want == "rear":
            # The field is a RECESS: it sits `depth` in from the skin, so its
            # rear edge is at the face and its front edge is depth behind it.
            # Judge it by which face it TOUCHES, not by which edge is larger.
            on_rear = abs(y0 - rear_face) < TOL
            leaks_front = y1 > front_face - TOL
            ok = on_rear and not leaks_front
            v = "OK - rear face only" if ok else (
                "LEAKED ONTO FRONT" if leaks_front
                else "not on the rear face")
            if not ok:
                bad.append("%s: y %.1f..%.1f mm; rear face is %.1f mm"
                           % (nm, f, b, rear_face * 10))
        else:
            # The base band is a band: a few mm tall, wrapping the whole
            # perimeter, so it must reach BOTH faces.
            wraps = (y0 < rear_face + TOL) and (y1 > front_face - TOL)
            ok = wraps
            v = "OK - wraps front and rear" if ok else "does not wrap"
            if not ok:
                bad.append("%s does not wrap: y %.1f..%.1f mm" % (nm, f, b))
        print("%-12s %-24s %s" % (nm, "%7.1f .. %7.1f" % (f, b), v))

    # The front panel is plain aluminium apart from two USB-C, one SDXC and
    # the status LED. Any other object spanning the width and reaching the
    # front face is a grille that escaped.
    print()
    print("objects spanning the full width AND reaching the front face:")
    escapers = []
    for o in bpy.context.scene.objects:
        if o.type != "MESH" or o.name in ("Floor",):
            continue
        x0, x1, y0, y1, z0, z1 = span(o)
        if (x1 - x0) > S.W * 0.85 and y1 > d2 - TOL and z0 > 1.0:
            escapers.append(o.name)
    if escapers:
        print("   %s" % ", ".join(sorted(escapers)))
        bad.append("grille geometry on the plain front panel: %s"
                   % ", ".join(sorted(escapers)))
    else:
        print("   none - the front panel is plain")

    print()
    if bad:
        print("PLACEMENT FAILED")
        for b in bad:
            print("  - %s" % b)
        return 1
    print("PLACEMENT OK")
    return 0


def _views_of(module_name):
    """Read a VIEWS list out of a render script without importing bpy.

    These files are only importable inside Blender, so the list is parsed
    with a regex instead. Three rigs had front/rear swapped, so the check has
    to cover all of them, and it has to work from outside Blender.

    The elevation is parsed as well as the azimuth, and it is not optional:
    a top view is az 90, el 89, which without its elevation looks exactly
    like a dead-on front elevation. Dropping it made the first version of
    this check fail "top" and "bottom".

    docs/viewer.js writes the same table with single quotes and Chinese
    labels, and its "front"/"rear" are 正面/背面, so the label is mapped
    before it is compared.
    """
    import re
    path = os.path.abspath(os.path.join(ROOT, "blender", module_name))
    if not os.path.exists(path):
        return None
    src = open(path, encoding="utf-8").read()
    # `const VIEWS` in viewer.js, bare `VIEWS` in the two Python rigs.
    # Non-greedy up to a line that is ONLY the closing bracket, so a "]," on a
    # view tuple cannot end the capture early. A first attempt used a plain
    # `.*?^\]`, which stopped at the first `]` inside the table and made all
    # three files report "no VIEWS list found" - a vacuous pass, which is the
    # one outcome this check must never produce.
    m = re.search(r"^(?:const\s+)?VIEWS\s*=\s*\[(.*?)^\]\s*;?\s*$",
                  src, re.S | re.M)
    if not m:
        return None
    body = m.group(1)
    out = []
    for name, az, el in re.findall(
            r"['\"]([^'\"]+)['\"]\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)", body):
        out.append((CN_LABELS.get(name, name), float(az), float(el)))
    return out or None


# The viewer's labels are Chinese; map them to the same tokens the two Python
# rigs use, so one table of expectations covers all three.
CN_LABELS = {
    "正面": "front",        # front
    "背面": "rear",         # rear
    "侧面": "side",         # side
    "顶视": "top",          # top
    "底视": "bottom",       # bottom
    "前脸特写": "front_closeup",
    "接口特写": "rear_closeup",
    "3/4 透视": "hero",     # three-quarter
}


def check_view_names():
    """Every named view must actually look at the face it is named for.

    Three render rigs had "front" and "rear" swapped - ortho_measure.py,
    render_views.py and docs/viewer.js - so a view called front was rendering
    the rear elevation and vice versa. Every published image carried the wrong
    label, and the viewer's 背面 button flew to the smooth front panel, hiding
    the one face with the ports and the perforated field. The names look
    correct in the source and the renders are all plausible, so nothing else
    catches it.
    """
    print("view-name check (+Y = FRONT, -Y = REAR):")
    bad = []
    for module in ("ortho_measure.py", "render_views.py", "../docs/viewer.js"):
        views = _views_of(module)
        if not views:
            # A file whose VIEWS cannot be parsed is a FAILED check, not a
            # skip. Reporting "no VIEWS list found" and then exiting 0 is how
            # a broken regex turns this into a gate that always passes - which
            # is the exact failure it exists to prevent, reproduced inside the
            # check itself.
            print("  %-22s COULD NOT PARSE VIEWS" % module)
            bad.append("%s: unparseable VIEWS" % module)
            continue
        print("  %s:" % module)
        for name, az, el in views:
            ar, er = math.radians(az), math.radians(el)
            dx = math.cos(er) * math.cos(ar)
            dy = math.cos(er) * math.sin(ar)
            if abs(math.sin(er)) > 0.9:
                face = "top" if math.sin(er) > 0 else "bottom"
            elif dy > 0.5:
                face = "+Y"
            elif dy < -0.5:
                face = "-Y"
            elif dx > 0.5:
                face = "+X"
            elif dx < -0.5:
                face = "-X"
            else:
                face = "oblique"
            # Match the leading token, so a numbered name like "01_front" or
            # "12_rear_flat" is still checked. Keying on the exact string let
            # every view in render_views.py fall through as "oblique", and
            # that file would have reported OK while checking nothing - the
            # same vacuous pass this check exists to prevent.
            base = re.sub(r"^\d+_", "", name)
            want = {"front": "+Y", "rear": "-Y", "right": "+X", "left": "-X",
                    "top": "top", "bottom": "bottom"}.get(base)
            if want is None:
                # a three-quarter or macro shot: it shows the whole machine, so
                # it has no single face to contradict
                print("    %-18s az %6.1f el %5.1f  -> %-7s  (oblique, no face)"
                      % (name, az, el, face))
                continue
            ok = face == want
            print("    %-18s az %6.1f el %5.1f  -> %-7s expect %-7s %s"
                  % (name, az, el, face, want, "OK" if ok else "MISMATCH"))
            if not ok:
                bad.append("%s:%s" % (module, name))
    if bad:
        print("VIEW NAMES FAILED: %s" % ", ".join(bad))
        return 1
    print("VIEW NAMES OK")
    return 0


if __name__ == "__main__":
    sys.exit(main() or check_view_names())
