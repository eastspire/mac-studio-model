"""Exactly one .blend, and it is the one the build just wrote.

There were two. build_mac_studio.py saves next to itself, so the live model
was blender/mac_studio.blend - 255 objects, with the perforated field. A
second, older copy sat at the repo root: 97 objects, no RearField, no
perforations anywhere, no rear panel. Five tools resolved their path to the
root, so the renders and the published GLB were all built from the broken
machine while the gates quietly measured the correct one.

Nothing reported a mismatch, because each tool opened a file successfully
and a .blend always opens successfully. Only a count of what is inside it
tells the two apart.

usage: blender --background --factory-startup --python tools/check_blend.py
"""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
CANON = os.path.join(ROOT, "blender", "mac_studio.blend")
STRAY = os.path.join(ROOT, "mac_studio.blend")

# What a correct build produces. These are floors, not exact counts: a
# legitimate rebuild can add or drop a part, but it can never lose the
# perforated field, the bottom cover, or an order of magnitude of geometry.
MIN_OBJECTS = 200
REQUIRED = ("Body", "RearField", "BaseGrille", "BottomCover", "BottomIntake")


def describe(path):
    bpy.ops.wm.open_mainfile(filepath=path)
    scene = bpy.context.scene
    names = {o.name for o in scene.objects}
    return len(scene.objects), names, os.path.getsize(path)


def main():
    print("canonical: %s" % os.path.relpath(CANON, ROOT))
    if not os.path.exists(CANON):
        print("  MISSING - run blender/build_mac_studio.py")
        return 1
    n_canon, names_canon, size_canon = describe(CANON)
    print("  %d objects, %.1f MB" % (n_canon, size_canon / 1048576.0))
    bad = []
    if n_canon < MIN_OBJECTS:
        bad.append("canonical .blend has only %d objects (< %d) - this is not "
                   "a complete build" % (n_canon, MIN_OBJECTS))
    for r in REQUIRED:
        if r not in names_canon:
            bad.append("canonical .blend is missing %s" % r)
        else:
            print("  has %s" % r)

    print()
    print("stray .blend check:")
    if os.path.exists(STRAY):
        n_stray, names_stray, size_stray = describe(STRAY)
        print("  %s" % os.path.relpath(STRAY, ROOT))
        print("  %d objects, %.1f MB" % (n_stray, size_stray / 1048576.0))
        missing = [r for r in REQUIRED if r not in names_stray]
        if missing:
            print("  it is missing: %s" % ", ".join(missing))
        bad.append("a second .blend exists at the repo root. Two models, and "
                   "the tools disagreed about which one is the model. Delete "
                   "it: rm mac_studio.blend")
    else:
        print("  none at the repo root - good")

    print()
    if bad:
        print("BLEND CHECK FAILED")
        for b in bad:
            print("  - %s" % b)
        return 1
    print("BLEND CHECK OK - one .blend, and it is the built one")
    return 0


if __name__ == "__main__":
    sys.exit(main())
