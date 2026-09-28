#!/usr/bin/env node
/**
 * Capture an Apple product page as a sequence of scrolled screenshots.
 *
 * Apple's product pages present the machine from a different angle as you
 * scroll, so a single screenshot is not enough: the hero shows one face, and
 * further down the page the same machine rotates to show the ports, the
 * underside and the corner details. This walks the page in viewport-sized
 * steps, waits for images to decode at each stop, and writes one PNG per step.
 *
 * Usage: node capture.mjs <url> <outDir> [maxSteps] [width] [height]
 */
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
import { setTimeout as sleep } from "node:timers/promises";

const [, , url, outDir, maxStepsArg, wArg, hArg] = process.argv;
const maxSteps = Number(maxStepsArg || 24);
const W = Number(wArg || 1600);
const H = Number(hArg || 1000);

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const profile = "/Users/sqs/.hermes/cache/scratch/apple-cdp-profile";
const port = 9333;

rmSync(profile, { recursive: true, force: true });
mkdirSync(outDir, { recursive: true });

const child = spawn(CHROME, [
  "--headless=new",
  "--disable-gpu",
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`,
  "--no-first-run",
  "--no-default-browser-check",
  "--hide-scrollbars",
  `--window-size=${W},${H}`,
  "about:blank",
], { stdio: "ignore" });

async function cdpTargets() {
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/json/list`);
      const j = await r.json();
      const page = j.find(t => t.type === "page");
      if (page?.webSocketDebuggerUrl) return page.webSocketDebuggerUrl;
    } catch { /* not up yet */ }
    await sleep(250);
  }
  throw new Error("devtools endpoint never came up");
}

const wsUrl = await cdpTargets();
const ws = new WebSocket(wsUrl);
await new Promise(res => (ws.onopen = res));

let nextId = 1;
const pending = new Map();
const events = [];
ws.onmessage = ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const { resolve, reject } = pending.get(m.id);
    pending.delete(m.id);
    m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result);
  } else if (m.method) {
    events.push(m);
  }
};
function send(method, params = {}) {
  const id = nextId++;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

async function evalJs(expr) {
  const r = await send("Runtime.evaluate", {
    expression: expr, returnByValue: true, awaitPromise: true,
  });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text);
  return r.result.value;
}

async function shot(path) {
  const r = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(path, Buffer.from(r.data, "base64"));
}

await send("Page.enable");
await send("Runtime.enable");
await send("Network.enable");
await send("Emulation.setDeviceMetricsOverride", {
  width: W, height: H, deviceScaleFactor: 1, mobile: false,
});

console.log("navigating:", url);
await send("Page.navigate", { url });
// wait for load event
for (let i = 0; i < 80; i++) {
  const st = await evalJs("document.readyState");
  if (st === "complete") break;
  await sleep(500);
}
await sleep(3000);

const info = await evalJs(`JSON.stringify({
  title: document.title,
  url: location.href,
  scrollHeight: document.documentElement.scrollHeight,
  innerW: innerWidth, innerH: innerHeight,
})`);
console.log("page:", info);

let step = 0;
for (step = 0; step < maxSteps; step++) {
  const y = await evalJs("window.scrollY");
  const name = `${outDir}/${String(step).padStart(2, "0")}_y${Math.round(y)}.png`;
  await shot(name);
  const frac = await evalJs(
    "Math.round((window.scrollY + innerHeight) / document.documentElement.scrollHeight * 100)"
  );
  console.log(`step ${step}  scrollY=${Math.round(y)}  (${frac}% down)  -> ${name.split("/").pop()}`);
  if (frac >= 99) break;
  await evalJs("window.scrollBy(0, Math.round(innerHeight * 0.92))");
  await sleep(1800);
}

// also grab the machine-bearing images directly, at full resolution
const imgs = await evalJs(`JSON.stringify(
  Array.from(document.images)
    .map(i => ({src: i.currentSrc || i.src, w: i.naturalWidth, h: i.naturalHeight, alt: (i.alt||'').slice(0,80)}))
    .filter(i => i.w >= 500)
)`);
writeFileSync(`${outDir}/_images.json`, imgs);
console.log("images manifest ->", `${outDir}/_images.json`);

ws.close();
child.kill();
console.log("done:", step + 1, "screenshots");
process.exit(0);
