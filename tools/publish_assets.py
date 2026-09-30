#!/usr/bin/env python3
"""Publish the site assets from renders/: web JPEGs and thumbnails.

There was no script for this step - docs/images/*.jpg and docs/thumbs/*.jpg
were produced by hand, which is how they came to be two days older than the
model they depict. Both sets are tracked, so a stale copy is invisible to
git: the file exists, the size looks plausible, and nothing is dirty.

This runs after blender/render_views.py and blender/export_gltf.py, and it
fails rather than publishing a partial set: a missing render must not leave
the site serving yesterday's picture of a machine whose rear panel moved.

usage: python3 tools/publish_assets.py [--check]

  --check   verify docs/images and docs/thumbs match renders/ without
            rewriting anything; exits 1 if any asset is stale
"""
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
RENDERS = os.path.join(ROOT, "renders")
IMAGES = os.path.join(ROOT, "docs", "images")
THUMBS = os.path.join(ROOT, "docs", "thumbs")

# The full-width render is 1500 px. Ship it at a size a gallery can hold and
# a retina screen still looks sharp on, and keep the thumbnail small enough to
# stay in the HTML without being a separate download worth avoiding.
IMG_W, IMG_Q = 1400, 88
THUMB_W, THUMB_Q = 420, 82


def sources():
    """Every render the site references, paired with its two outputs."""
    if not os.path.isdir(RENDERS):
        return []
    out = []
    for fn in sorted(os.listdir(RENDERS)):
        if not fn.endswith(".png") or fn.startswith("_"):
            continue
        stem = fn[:-4]
        # the live-render directory is a verification output, not site content
        if stem.startswith(("ortho_", "10_cutaway")):
            continue
        out.append((os.path.join(RENDERS, fn),
                    os.path.join(IMAGES, stem + ".jpg"),
                    os.path.join(THUMBS, stem + ".jpg")))
    return out


def view_names():
    """The views render_views.py actually defines, read without importing bpy.

    This is what makes the freshness check honest. An earlier version compared
    each published image against its own render file and called the result
    "current" - but two of those renders (20_front_ports, 21_rear_ports) are
    not in VIEWS at all, so nothing had regenerated them. Their images were
    therefore a day older than the model, and the check passed, because the
    question it was asking ("is this image newer than its source?") was not
    the question that mattered ("is this source part of the current build?").

    The published images come from Sep 28 and the renders from Sep 30, and
    both were internally consistent - which is exactly the shape of bug a
    per-file mtime check cannot see.
    """
    import re
    path = os.path.join(ROOT, "blender", "render_views.py")
    if not os.path.exists(path):
        return None
    src = open(path, encoding="utf-8").read()
    m = re.search(r"^VIEWS\s*=\s*\[(.*?)^\]", src, re.S | re.M)
    if not m:
        return None
    return {n for n in re.findall(r'\(\s*"([^"]+)"', m.group(1))}


def emit(src, dst, width, quality):
    im = Image.open(src)
    # PNG carries alpha; the site sits on a light page, so flatten onto white
    # rather than shipping a transparent JPEG (which cannot exist anyway).
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        im = im.convert("RGBA")
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    if im.width > width:
        h = round(im.height * width / im.width)
        im = im.resize((width, h), Image.Resampling.LANCZOS)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    im.save(dst, "JPEG", quality=quality, optimize=True, progressive=True)
    return os.path.getsize(dst)


def stale(path, src_stat):
    """A destination is stale if it is missing or older than its render."""
    if not os.path.exists(path):
        return True
    return os.path.getmtime(path) < src_stat


def main():
    check_only = "--check" in sys.argv
    pairs = sources()
    if not pairs:
        print("no renders found in %s - run blender/render_views.py first"
              % RENDERS)
        return 1
    views = view_names()
    if views is None:
        print("cannot read VIEWS from blender/render_views.py")
        return 1

    print("%-24s %-10s %s" % ("render", "in VIEWS", "status"))
    bad = []
    for src, img, thumb in pairs:
        stem = os.path.basename(src)[:-4]
        known = stem in views
        if not known:
            # Published from a render no script regenerates, so it can never
            # be proven fresh. Treat as stale and say why, rather than
            # comparing it against its own unchanged file and passing.
            print("  %-22s %-10s %s" % (os.path.basename(src), "NO",
                                        "ORPHAN - not in render_views.VIEWS"))
            bad.append(src)
            continue
        st = os.stat(src)
        if not (stale(img, st.st_mtime) or stale(thumb, st.st_mtime)):
            print("  %-22s %-10s %s" % (os.path.basename(src), "yes", "current"))
            continue
        if check_only:
            print("  %-22s %-10s %s" % (os.path.basename(src), "yes", "STALE"))
            bad.append(src)
            continue
        a = emit(src, img, IMG_W, IMG_Q)
        b = emit(src, thumb, THUMB_W, THUMB_Q)
        print("  %-22s %-10s written (%.0f KB / %.0f KB)"
              % (os.path.basename(src), "yes", a / 1024, b / 1024))

    # A view in VIEWS with no render at all is the other half of the problem.
    have = {os.path.basename(s)[:-4] for s, _, _ in pairs}
    for missing in sorted(views - have):
        print("  %-22s %-10s %s" % (missing + ".png", "-",
                                    "MISSING - defined but never rendered"))
        bad.append(missing)

    print()
    if bad:
        print("STALE ASSETS: %d problem(s)" % len(bad))
        for s in bad:
            print("  %s" % s)
        print("run: blender/render_views.py, then python3 tools/publish_assets.py")
        return 1
    if check_only:
        print("ALL ASSETS CURRENT")
    else:
        print("PUBLISHED %d view(s)" % len(pairs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
