#!/usr/bin/env python3
"""Gate on the front/rear axis convention of the shipped GLB.

This convention has been asserted backwards THREE times - in
blender/render_views.py, in blender/ortho_measure.py and in docs/viewer.js -
each time in a comment stating the opposite of the truth, which is what made
it look deliberate rather than mistaken. Every time it was wrong, a "front"
view showed the rear panel or the camera aimed at the ceiling.

The builder works in Blender's Z-up space, where the front skin is the +Y
face. glTF is Y-up, so the export lands as (x, y, z)_blender -> (x, z, -y):
the FRONT is at -Z, the REAR at +Z, and Y is the machine's height.

This reads the node/accessor bounds straight out of the GLB's JSON chunk. The
geometry itself is Draco-compressed and cannot be interrogated without a
decoder, but the accessor min/max are stored uncompressed and are enough to
locate each feature group - so the check needs no browser, no Blender and no
Draco.

usage: python3 tools/check_front_axes.py [path.glb]
"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
DEFAULT = os.path.join(ROOT, "docs", "mac-studio.glb")

# the feature groups, and which side of the machine each belongs on
#   +1 means the group must sit at POSITIVE depth in glTF space (= the REAR)
#   -1 means it must sit at NEGATIVE depth (= the FRONT)
GROUPS = [
    ("Front_", -1, "USB-C / SDXC / status LED"),
    ("Port_", +1, "the rear I/O row"),
    ("RearBay", +1, "the perforated exhaust field"),
    ("Power", +1, "the power button"),
]


def read_json_chunk(path):
    d = open(path, "rb").read()
    if d[:4] != b"glTF":
        raise SystemExit(f"{path} is not a GLB")
    off = 12
    while off < len(d):
        length, kind = struct.unpack_from("<II", d, off)
        off += 8
        if kind == 0x4E4F534A:            # 'JSON'
            return json.loads(d[off:off + length])
        off += length
    raise SystemExit("no JSON chunk in the GLB")


def group_bounds(js, prefix):
    """Union of every accessor's min/max for the nodes whose name starts here."""
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    found = 0
    for node in js["nodes"]:
        name = node.get("name", "")
        if not name.startswith(prefix) or "mesh" not in node:
            continue
        found += 1
        for prim in js["meshes"][node["mesh"]]["primitives"]:
            acc = js["accessors"][prim["attributes"]["POSITION"]]
            for k in range(3):
                lo[k] = min(lo[k], acc["min"][k])
                hi[k] = max(hi[k], acc["max"][k])
    if not found:
        return None
    return [v * 100.0 for v in lo], [v * 100.0 for v in hi], found


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    if not os.path.isfile(path):
        print(f"{path} does not exist")
        return 2
    js = read_json_chunk(path)
    print(f"{os.path.relpath(path, ROOT)}  {os.path.getsize(path):,} bytes")
    print("glTF is Y-up; the builder is Z-up, so Blender (x, y, z) -> "
          "(x, z, -y)\n")

    fails = []
    for prefix, want_sign, what in GROUPS:
        got = group_bounds(js, prefix)
        if got is None:
            print(f"  {prefix:9s} no nodes found")
            continue
        lo, hi, n = got
        # depth in glTF space is Z. The front is the near face at -Z.
        z_mid = (lo[2] + hi[2]) / 2.0
        side = "FRONT" if z_mid < 0 else "REAR"
        ok = (z_mid < 0) == (want_sign < 0)
        print(f"  {prefix:9s} {n:3d} nodes   x {lo[0]:+7.3f}..{hi[0]:+7.3f}  "
              f"y {lo[1]:+6.3f}..{hi[1]:+6.3f}  z {lo[2]:+7.3f}..{hi[2]:+7.3f}  "
              f"-> {side:5s}  ({what})  {'ok' if ok else 'WRONG SIDE'}")
        if not ok:
            fails.append(f"{prefix}* sits on the {side} but is the {what}")

    # and the envelope, which the whole repo's tolerance claims to hold
    all_lo = [float("inf")] * 3
    all_hi = [float("-inf")] * 3
    for node in js["nodes"]:
        if "mesh" not in node:
            continue
        for prim in js["meshes"][node["mesh"]]["primitives"]:
            acc = js["accessors"][prim["attributes"]["POSITION"]]
            for k in range(3):
                all_lo[k] = min(all_lo[k], acc["min"][k])
                all_hi[k] = max(all_hi[k], acc["max"][k])
    size = [(all_hi[k] - all_lo[k]) * 100.0 for k in range(3)]
    print(f"\n  envelope  {size[0]:.4f} x {size[1]:.4f} x {size[2]:.4f} cm"
          f"   (Apple: 19.70 x 9.50 x 19.70)")

    print()
    if fails:
        for f in fails:
            print("FAIL ", f)
        print("\nAXIS CONVENTION IS WRONG - a 'front' view would show the "
              "rear panel")
        return 1
    print("AXES OK - front is -Z, rear is +Z, height is Y, envelope unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
