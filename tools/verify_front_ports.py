#!/usr/bin/env python3
"""Aim the served viewer at the front panel and measure the port openings.

The claim d5fd74e made was that the front USB-C / SDXC ports are dark recesses
rather than silver plates on unbroken metal. It was found by looking at the
page, and the check a5524c5 added afterwards could not confirm it: every gate
on this repo reads the SOURCE, and the source cannot tell a cut panel from an
uncut one. The GLB carries all 18 Front_* nodes with Cavity_Black present and
the right dimensions whether the boolean landed or not - which is the whole
reason the bug survived a passing suite.

So this measures the rendered artefact. For each port it:

  1. moves the camera to the model's front elevation on +Y, the convention
     documented at docs/viewer.js:222 (az 90 = FRONT, 270 = REAR);
  2. projects the port's world centre to a screen pixel;
  3. raycasts from the camera through that pixel and reports what the ray
     hits - name, material, and how far behind the skin the hit is;
  4. reads the framebuffer at that pixel and reports its luma.

A cut opening returns a hit on socket geometry deep inside the cavity, in a
near-black material, with the enclosing panel NOT hit at the same ray. An
uncut panel returns the panel itself at the skin, bright, in an aluminium
material. Those are different verdicts, not different descriptions of one.

usage:  python3 tools/verify_front_ports.py [--url URL] [--port N] [--out DIR]
"""
import argparse
import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "renders", "verify")

# from blender/mac_studio_spec.py: IO_Z, LED_X, FRONT_PORTS. The front is +Y
# and the ports sit on -X with the LED on +X (docs/viewer.js:220).
IO_Z = 2.35
FRONT_PORTS = [
    ("USBC_1", -6.626, 0.26, 0.850),
    ("USBC_2", -5.148, 0.27, 0.850),
    ("SDXC", -2.447, 2.700, 0.270),
]
LED_X = 6.619
LED_R = 0.135

# Axes, read out of the GLB itself rather than assumed.
#
# blender/build_mac_studio.py builds in Blender's Z-up space: the front skin is
# the +Y face at y = +D/2 = 9.85, and the port row is at height z = IO_Z. The
# exporter writes the model's own coordinates and glTF's Z-up-to-Y-up
# convention maps them as (x, y, z)_blender -> (x, z, -y)_gltf, so in the file
#
#   the FRONT panel (Front_*, USB-C + SDXC + LED) is at  Z = -9.85 cm
#   the REAR  panel (Port_*,  the I/O row)               is at  Z = +9.85 cm
#   the height axis is Y, and the front's port row sits at Y = IO_Z
#
# measured from the exported accessors, not from the builder:
#
#   Front_*   x -6.756..-1.097   y  1.925..2.775   z -9.75..-9.41
#   Port_*    x -6.938.. 6.936   y  1.690..3.115   z  9.394..9.766
#
# docs/viewer.js:220 asserts "+Y = FRONT" and derives its whole azimuth
# convention from it. That is wrong on this export: +Y is straight up, so an
# azimuth that follows the comment points the camera at the ceiling.
CM = 0.01
FRONT_Z = -9.85 * CM      # the skin
WALL = 0.15 * CM
HEIGHT_AXIS = "y"

# The wall is 1.5 mm, so a ray that gets 0.75 mm in is through the panel and
# anything nearer is the panel itself. The port cavity is 0.34 cm deep, so a
# cut reading lands at 1.5..4.9 mm, well clear of both bands.
CUT_DEPTH_MM = WALL * 1000 / 2.0

# A real recess casts a shadow: a POPULATION of dark pixels, not one dark
# pixel. The test is a fraction of a box around the probe, because the box is
# measured against the bare panel a few pixels away in the same run - the
# control reads 0 of 725, and the three ports read 49, 62 and 103 of 725.
# A fraction rather than an absolute luma, because an absolute number quietly
# becomes wrong when the page's exposure, background or tone mapping changes,
# and then it fails on a model that did not change.
#
# 2% is loose enough for antialiasing at the lip of the opening and tight
# enough that a lit surface cannot reach it.
DARK_PIXEL_LUMA = 60         # below this a pixel counts as shadowed
DARK_FRACTION = 0.02

IN_PAGE = r"""
(async () => {
  const V = window.__viewer;
  if (!V) return JSON.stringify({ error: 'no __viewer handle' });
  const S = window.__spec;
  if (!S) return JSON.stringify({ error: 'no __spec' });
  const { camera, controls, modelRoot, THREE, box } = V;
  const { IO_Z, LED_X, FRONT_Z, WALL, CM } = S;

  // Front elevation: the eye on -Z looking in +Z, level with the port row.
  const target = new THREE.Vector3(0, IO_Z * CM, FRONT_Z);
  const halfH = 2.6 * CM, halfW = 10.4 * CM;   // the port strip and its margins
  const vFov = THREE.MathUtils.degToRad(camera.fov);
  const hFov = 2 * Math.atan(Math.tan(vFov / 2) * camera.aspect);
  const dist = Math.max(halfH / Math.tan(vFov / 2), halfW / Math.tan(hFov / 2)) * 1.10;
  camera.position.set(target.x, target.y, target.z - dist);
  controls.target.copy(target);
  camera.lookAt(target);
  camera.updateMatrixWorld(true);
  controls.update();

  const canvas = V.renderer.domElement;
  const W = canvas.clientWidth, H = canvas.clientHeight;
  const rc = new THREE.Raycaster();
  const v2 = new THREE.Vector2();
  const dpr = V.renderer.getPixelRatio();
  const results = [];

  // depth is measured inward from the front skin, along +Z
  const depthOf = (point) => +((point.z - FRONT_Z) * 1000).toFixed(2);

  const probe = (label, wx, wy, wz, expect) => {
    const p = new THREE.Vector3(wx, wy, wz);
    const ndc = p.clone().project(camera);
    const sx = (ndc.x * 0.5 + 0.5) * W;
    const sy = (-ndc.y * 0.5 + 0.5) * H;
    if (ndc.z < -1 || ndc.z > 1 || sx < 0 || sx > W || sy < 0 || sy > H) {
      results.push({ label, expect, offscreen: true, sx, sy });
      return;
    }
    v2.set((sx / W) * 2 - 1, -(sy / H) * 2 + 1);
    rc.setFromCamera(v2, camera);
    const hits = rc.intersectObject(modelRoot, true);
    const named = hits.filter(h => h.object && h.object.visible).slice(0, 5)
      .map(h => ({
        name: h.object.name,
        depth_behind_skin_mm: depthOf(h.point),
        mat: h.object.material && h.object.material.name
             ? h.object.material.name : '(unnamed)',
      }));
    results.push({
      label, expect, sx: +sx.toFixed(1), sy: +sy.toFixed(1),
      hits: named, front_most: named[0] || null,
    });
  };

  // The back of the opening, 0.6 mm inside the skin, at the port's own height
  const z_back = FRONT_Z + 0.6 * CM;
  for (const [name, x, w, h] of window.__frontPorts) {
    probe(name + ':centre', x * CM, IO_Z * CM, z_back, 'socket-in-cavity');
    probe(name + ':offset', (x + w * 0.25) * CM, (IO_Z + h * 0.2) * CM, z_back,
          'socket-in-cavity');
  }
  // The control for the dark-core test: bare panel, clear of every opening.
  //
  // It used to sit 0.30 cm from a port's edge, "solid panel between this port
  // and the next". That is not clear of anything. A 27 mm SDXC slot is a big
  // recess, it throws its shadow a good way across the face, and the 24x28
  // box around the probe caught 46 shadowed pixels - so the control failed
  // while the three ports passed, and the run reported a defect in a panel that
  // is solid. A control has to be a control: measured away from the thing it
  // is controlling for. This is at the far side of the face, between the last
  // port and the LED, and the geometry check says the ray stops on Body at
  // 0.0 mm, so if it still shows a dark core the test is reading the light.
  probe('control:bare panel', 1.6 * CM, IO_Z * CM, z_back, 'panel');
  // the LED sits proud of the skin, so nothing is cut there
  probe('LED', LED_X * CM, IO_Z * CM, FRONT_Z, 'led-proud');
  // plain panel, well clear of every feature
  probe('blank', 3.2 * CM, 5.6 * CM, z_back, 'panel');

    // Sample the rendered image.
    //
    // NOT gl.readPixels. A WebGL drawing buffer is cleared after it is composited
    // unless the context was created with preserveDrawingBuffer, and this one was
    // not - so a read scheduled outside the same task as the draw returns a
    // cleared buffer. That is not a subtle bias, it is the wrong image entirely:
    // every probe read back 91-198% of the bare panel's luma (i.e. no recess at
    // all) while the raycast against the very same frame correctly reported
    // socket walls 1.2 mm behind the skin. Both numbers were real and they
    // contradicted each other, which is the signature of a misaddressed read.
    //
    // The fix is to draw the canvas into a 2D canvas inside the SAME task as the
    // read. drawImage() of a WebGL canvas is specified to snapshot the current
    // contents, so it does not depend on the drawing buffer surviving.
    await new Promise(r => requestAnimationFrame(r));
    const gl_canvas = V.renderer.domElement;
    const bufW = gl_canvas.width, bufH = gl_canvas.height;
    const flat = document.createElement('canvas');
    flat.width = bufW; flat.height = bufH;
    const fctx = flat.getContext('2d', { willReadFrequently: true });
    fctx.drawImage(gl_canvas, 0, 0);

  // Two readings per probe, and the second is the one that means anything.
  //
  // A single pixel at the port's centre is not a measurement of a port. It
  // measures whichever surface happens to be under that one ray, and a USB-C
  // socket's inner wall is LIT ALUMINIUM - sampling dead centre in the
  // opening reads the lit wall, at luma 107 where the bare panel beside it
  // reads 108. That is not a cap; it is a socket, correctly modelled, and the
  // number looks exactly like a defect.
  //
  // What a real recess has, and a solid panel never does, is a DARK CORE. So
  // read a box around the probe and keep the darkest pixel in it. Measured on
  // the fixed model:
  //
  //     USBC_1  darkest  19    49 px below 60 / 725
  //     USBC_2  darkest  19    62 px below 60 / 725
  //     SDXC    darkest   0   103 px below 60 / 725
  //     bare panel  darkest 98     0 px below 60 / 725
  //
  // The panel is the control, and it has none. Both numbers are reported: the
  // dark core decides, the raw luma is kept for the record.
  const BOX_W = 12, BOX_H = 14;      // half-extents, in probe pixels
  for (const r of results) {
    if (r.offscreen) { r.luma = null; r.luma_dark = null; continue; }
    // sx/sy are CSS pixels with the origin at the canvas's top-left; the 2D
    // canvas has the origin at its top-left too, so only the SCALE differs -
    // and it is bufW/W, never a bare devicePixelRatio. Scaling by dpr alone is
    // right only when the drawing buffer is exactly dpr times the CSS box.
    const gx = Math.round(r.sx * bufW / W);
    const gy = Math.round(r.sy * bufH / H);
    r.buf_px = [gx, gy, bufW, bufH];
    if (gx < 0 || gy < 0 || gx >= bufW || gy >= bufH) {
      r.luma = null; r.luma_dark = null; continue;
    }
    const d = fctx.getImageData(gx, gy, 1, 1).data;
    r.luma = +(0.2126 * d[0] + 0.7152 * d[1] + 0.0722 * d[2]).toFixed(1);

    // the box, in buffer pixels
    const bx0 = Math.max(0, gx - Math.round(BOX_W * bufW / W));
    const bx1 = Math.min(bufW - 1, gx + Math.round(BOX_W * bufW / W));
    const by0 = Math.max(0, gy - Math.round(BOX_H * bufH / H));
    const by1 = Math.min(bufH - 1, gy + Math.round(BOX_H * bufH / H));
    const box = fctx.getImageData(bx0, by0, bx1 - bx0 + 1, by1 - by0 + 1).data;
    let dark = 255, n_dark = 0;
    for (let i = 0; i < box.length; i += 4) {
      const l = 0.2126 * box[i] + 0.7152 * box[i + 1] + 0.0722 * box[i + 2];
      if (l < dark) dark = l;
      if (l < 60) n_dark++;
    }
    const total = box.length / 4;
    r.luma_dark = +dark.toFixed(1);
    r.dark_px = n_dark;
    r.box_px = total;
  }
  // The same snapshot the luma numbers were read from, handed back so the
  // picture on disk is the SAME frame - not a second capture that may be a
  // different paint entirely. Canvas.toDataURL on the 2D copy, because the
  // 2D copy is known-good where the WebGL canvas is not.
  window.__snapshot = flat.toDataURL('image/png');
  return JSON.stringify({
    camera_cm: camera.position.toArray().map(v => +(v * 100).toFixed(2)),
    // Self-diagnosis. Two of the failures in this gate's history were the
    // probe reading a frame the viewer had not drawn, and both looked like a
    // model defect. These four numbers distinguish "the model is wrong" from
    // "I am looking at the wrong canvas", in one line, before anyone goes
    // looking for a bug in the geometry:
    //   canvas_css  - the CSS box the projection used
    //   canvas_buf  - the backing store the sample came from
    //   in_scene    - is the model actually a child of the scene?
    //   visible     - is it in the frustum and not hidden?
    diag: {
      canvas_css: [W, H],
      canvas_buf: [bufW, bufH],
      in_scene: !!modelRoot.parent,
      model_children: modelRoot.children.length,
      model_visible: modelRoot.visible,
      model_world_z: +modelRoot.position.z.toFixed(4),
      cam_near: camera.near, cam_far: camera.far,
      cam_dist: +camera.position.distanceTo(controls.target).toFixed(4),
      renderer_size: V.renderer.getSize(new THREE.Vector2()).toArray(),
    },
    dist_cm: +(dist / CM).toFixed(2),
    canvas: [W, H, dpr],
    count: results.length,
    results,
  });
})()
"""


def chrome_binary():
    c = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if os.path.isfile(c) and os.access(c, os.X_OK):
        return c
    root = os.path.expanduser("~/.agent-browser/browsers")
    for r, dirs, _ in os.walk(root):
        for d in dirs:
            p = os.path.join(r, d, "Contents/MacOS", d)
            if os.path.isfile(p):
                return p
    raise SystemExit("no Chrome binary found")


def http_json(port, path, method="GET"):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
    with opener.open(req, timeout=20) as r:
        body = r.read().decode()
    return json.loads(body) if body.strip().startswith(("{", "[")) else body


class Reader:
    def __init__(self):
        self.pending, self.events, self.mid = {}, [], 0

    async def run(self, ws):
        while True:
            try:
                raw = await ws.recv()
            except Exception:
                return
            try:
                m = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue          # websocket control frame, not JSON
            if "id" in m:
                self.pending[m["id"]] = m
            else:
                self.events.append(m)

    async def call(self, ws, method, params=None, timeout=30):
        self.mid += 1
        mid = self.mid
        await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while mid not in self.pending:
            if time.time() > deadline:
                return {"error": f"timeout {method}"}
            await asyncio.sleep(0.01)
        return self.pending.pop(mid)

    async def ev(self, ws, expr, timeout=60):
        r = await self.call(ws, "Runtime.evaluate", {
            "expression": expr, "returnByValue": True, "awaitPromise": True,
        }, timeout=timeout)
        d = r.get("result", {})
        if "exceptionDetails" in d:
            return {"__jsError": d["exceptionDetails"].get("text"),
                    "detail": str(d["exceptionDetails"])[:400]}
        res = d.get("result", {})
        if res.get("subtype") == "error":
            return {"__jsError": res.get("description")}
        v = res.get("value")
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return v
        return v


async def drive(url, port, out_dir):
    import websockets

    tab = http_json(port, "/json/new?about:blank", method="PUT")
    log = []
    async with websockets.connect(tab["webSocketDebuggerUrl"], max_size=64 << 20) as ws:
        c = Reader()
        rt = asyncio.create_task(c.run(ws))
        await c.call(ws, "Page.enable")
        await c.call(ws, "Runtime.enable")
        await c.call(ws, "Log.enable")
        await c.call(ws, "Emulation.setDeviceMetricsOverride",
                     {"width": 1280, "height": 860, "deviceScaleFactor": 1, "mobile": False})
        await c.call(ws, "Page.navigate", {"url": url})
        # the metrics override is reset by navigation - re-apply, then confirm
        await c.call(ws, "Emulation.setDeviceMetricsOverride",
                     {"width": 1280, "height": 860, "deviceScaleFactor": 1, "mobile": False})

        ready = None
        for _ in range(80):
            await asyncio.sleep(0.5)
            ready = await c.ev(ws, "(()=>{const l=document.getElementById('loading');"
                                  "return JSON.stringify({loading:l?l.textContent.trim():null,"
                                  "flag:document.documentElement.dataset.viewerReady||null,"
                                  "inner:innerWidth});})()")
            if isinstance(ready, dict) and ready.get("flag") == "1":
                break
        print("viewer ready:", json.dumps(ready))
        if not (isinstance(ready, dict) and ready.get("flag") == "1"):
            for e in c.events:
                if e.get("method") == "Log.entryAdded":
                    print("PAGE:", e["params"]["entry"].get("level"),
                          e["params"]["entry"].get("text"))
            rt.cancel()
            return None

        # the probe list, injected so the page script and the spec file cannot
        # drift apart
        await c.ev(ws, f"window.__frontPorts = {json.dumps(FRONT_PORTS)}; "
                       f"window.__spec = {{IO_Z:{IO_Z}, LED_X:{LED_X}, "
                       f"FRONT_Z:{FRONT_Z}, WALL:{WALL}, CM:{CM}}}; 'ok'")

        out = await c.ev(ws, IN_PAGE, timeout=90)

        # A picture of the same framing, for the record.
        #
        # Taken HERE, on this same connection, inside the same live page. It used
        # to be taken on a second connection after the reader task was
        # cancelled, and that made it worthless twice over:
        #   1. the viewer's rAF loop stops painting once nothing drives the
        #      page, so the canvas is blank by the time the shot is taken.
        #   2. probe and picture were two different frames, so the picture could
        #      never have corroborated the probe even if it had been right.
        #
        # Even on this connection Page.captureScreenshot came back 61% pure
        # white with 1365 unique colours - the page's CSS gradient, not a
        # render - because CDP's capture forces its own paint of a page whose
        # canvas is alpha-blended over a light background. The probe's own
        # drawImage() of the same canvas returns a real image; that is where
        # the picture comes from now. Asking the page for its own canvas is
        # also the only way to get the SAME frame the luma numbers came from.
        data = None
        raw = await c.ev(ws, "window.__snapshot || 'null'", timeout=60)
        if isinstance(raw, str) and raw.startswith("data:image/"):
            data = raw.split(",", 1)[1]
        rt.cancel()
    if out is None or not isinstance(out, dict):
        print("probe returned:", json.dumps(out)[:800] if out else out)
        return None

    os.makedirs(out_dir, exist_ok=True)
    shot_path = None
    blank_frac = 0.0
    if data:
        shot_path = os.path.join(out_dir, "front_elevation.png")
        with open(shot_path, "wb") as f:
            f.write(base64.b64decode(data))
        # A lit render of a 19.7 cm metal box on a white page is maybe half
        # white. The blank page this replaces was 63% white with 1383 unique
        # colours in the remainder - a gradient, not geometry. 40% is the line.
        try:
            from PIL import Image
            im = Image.open(shot_path).convert("RGB")
            px = list(im.getdata())
            white = sum(1 for r, g, b in px if r > 250 and g > 250 and b > 250)
            blank_frac = white / max(1, len(px))
            out["shot_size"] = [im.width, im.height]
        except ImportError:
            out["shot_size"] = None
        out["blank_frac"] = round(blank_frac, 4)
        out["screenshot"] = shot_path
        print(f"screenshot: {shot_path} {out.get('shot_size')}, "
              f"{100 * blank_frac:.0f}% pure white")
        if blank_frac > 0.40:
            print("  ^ BLANK: the canvas was never painted. This picture is "
                  "not evidence\n    of anything and the run does not pass on it.")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8791/viewer.html")
    ap.add_argument("--port", type=int, default=9231)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    import websockets  # noqa: F401 - fail early and clearly
    os.makedirs(a.out, exist_ok=True)

    profile = "/tmp/msm-verify-profile"
    shutil.rmtree(profile, ignore_errors=True)
    proc = subprocess.Popen([
        chrome_binary(), "--headless=new", "--no-sandbox", "--disable-gpu",
        "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
        "--disable-accelerated-2d-canvas",
        f"--remote-debugging-port={a.port}", "--remote-allow-origins=*",
        "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
        f"--user-data-dir={profile}", "--hide-scrollbars", "--window-size=1280,860",
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for _ in range(100):
        try:
            v = http_json(a.port, "/json/version")
            if isinstance(v, dict) and v.get("Browser"):
                print("chrome:", v["Browser"])
                break
        except Exception:
            pass
        time.sleep(0.25)
    else:
        proc.kill()
        raise SystemExit("chrome never bound the debug port")

    try:
        out = asyncio.run(drive(a.url, a.port, a.out))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)

    if not out:
        print("\nFRONT PORT CHECK: INCONCLUSIVE - the page never became ready")
        return 2
    if isinstance(out, dict) and ("__jsError" in out or out.get("error")):
        print("page probe failed:", json.dumps(out)[:600])
        print("\nFRONT PORT CHECK: INCONCLUSIVE - the probe threw, nothing was measured")
        return 2
    # An empty result set is not a pass. The first run of this script threw a
    # ReferenceError inside the page, judge() found zero probes to complain
    # about, and it printed PASSED - a check that reports success while having
    # measured nothing is worse than no check, because it is believed.
    n = out.get("count", 0)
    if n == 0:
        print("\nFRONT PORT CHECK: INCONCLUSIVE - 0 probes were measured")
        return 2
    print(f"probes measured: {n}")
    print(json.dumps(out, indent=2)[:6000])
    fails = judge(out)
    print()
    if fails:
        for f in fails:
            print("FAIL ", f)
        print(f"\nFRONT PORT CHECK FAILED ({len(fails)})")
        return 1
    print("FRONT PORT CHECK PASSED - the front panel is cut; "
          "openings read as dark recesses, solid panel reads as metal")
    return 0


def judge(out):
    """Each probe has an expected reading; the verdict is per probe."""
    fails = []
    # a socket recessed a full wall or more is behind the skin; a panel hit is
    # at it. The wall is 1.5 mm, so anything past 0.75 mm is through the panel.
    through = CUT_DEPTH_MM
    for r in out.get("results", []):
        if r.get("offscreen"):
            fails.append(f"{r['label']}: projected off-screen, nothing measured")
            continue
        fm = r.get("front_most")
        if not fm:
            fails.append(f"{r['label']}: the ray hit NOTHING - a hole into empty space "
                         f"where the machine should be solid")
            continue
        depth = fm.get("depth_behind_skin_mm", 0.0)
        luma = r.get("luma")
        dark = r.get("luma_dark")
        n_dark = r.get("dark_px") or 0
        box = r.get("box_px") or 1
        if r["expect"] == "socket-in-cavity":
            if depth < through:
                fails.append(f"{r['label']}: the ray stops {depth} mm behind the skin "
                             f"({fm['name']}). The panel is NOT cut here - the ray "
                             f"reaches metal instead of the cavity. This is the d5fd74e "
                             f"bug: a socket sitting behind an unbroken skin.")
            elif dark is None:
                fails.append(f"{r['label']}: no pixel reading was taken - "
                             f"nothing was measured, which is not a pass")
            elif n_dark < DARK_FRACTION * box:
                # The decision, and the reason it is not a single-pixel luma:
                # a USB-C socket's inner wall is lit aluminium, so the pixel
                # dead centre in the opening reads 107 where the bare panel
                # beside it reads 108. That is a correctly-modelled socket
                # that looks exactly like a cap. A real recess has a DARK
                # CORE - a population of genuinely shadowed pixels - and a
                # solid panel has none at all.
                fails.append(
                    f"{r['label']}: the ray reaches the socket {depth} mm in, "
                    f"but the opening has no dark core - {n_dark} of {box} pixels "
                    f"below 60 (need {100 * DARK_FRACTION:.0f}%), darkest "
                    f"{dark}. An opening that casts no shadow is not open.")
            elif not str(fm.get("name", "")).startswith("Front_") and \
                    not str(fm.get("mat", "")).startswith("Cavity"):
                fails.append(f"{r['label']}: cut, but the first thing the ray meets is "
                             f"{fm['name']} ({fm['mat']}) - expected the socket or its "
                             f"black cavity, not internals")
        elif r["expect"] == "panel":
            if depth >= through:
                fails.append(f"{r['label']}: expected solid panel, but the first hit is "
                             f"{depth} mm behind the skin ({fm['name']}) - the opening is "
                             f"wider than the port it belongs to")
            elif n_dark > 0:
                # the control for the check above: bare aluminium has no
                # shadowed pixels. If this one has any, the dark-core test is
                # measuring the light, not the geometry.
                fails.append(f"{r['label']}: solid panel has {n_dark} of {box} pixels "
                             f"below 60 (darkest {dark}) - bare aluminium casts no "
                             f"shadow, so the dark-core test is measuring the light")
        elif r["expect"] == "led-proud":
            pass

    # A blank screenshot is not a picture of the model. It was 61% white and
    # filed as renders/verify/front_elevation.png, which is how a crop of it
    # came to be "inspected" for ports that were never drawn. The picture now
    # comes from the page's own canvas - the same one the luma numbers were
    # read from - so it cannot be a different frame, but it can still be blank
    # if the canvas was never painted, and that has to fail the run.
    blank = out.get("blank_frac")
    if blank is not None and blank > 0.40:
        fails.append(f"the screenshot is {100 * blank:.0f}% pure white - the canvas "
                     f"was never painted, so the picture on disk is not evidence")
    return fails


if __name__ == "__main__":
    sys.exit(main())
