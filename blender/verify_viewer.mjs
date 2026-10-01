// Headless validation of the viewer's logic: no WebGL, no network.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const DOCS = '/Users/sqs/code/mac-studio-model/docs/';

const src = readFileSync('/Users/sqs/code/mac-studio-model/docs/viewer.js', 'utf8');
const html = readFileSync('/Users/sqs/code/mac-studio-model/docs/viewer.html', 'utf8');

const checks = [];
const add = (name, ok, extra='') => checks.push([name, ok, extra]);

// 1. every getElementById target actually exists in the HTML
const ids = [...src.matchAll(/getElementById\(['"]([\w-]+)['"]\)/g)].map(m => m[1]);
const missing = [...new Set(ids)].filter(id => !html.includes(`id="${id}"`));
add('all getElementById targets exist in viewer.html', missing.length === 0,
    missing.length ? 'missing: ' + missing.join(', ') : `${new Set(ids).size} ids`);

// 2. the import map covers every bare specifier used in viewer.js
const imports = [...src.matchAll(/from ['"]([\w@/.-]+)['"]/g)].map(m => m[1]);
const bare = [...new Set(imports.filter(s => !s.startsWith('.')))];
const mapMatch = html.match(/<script type="importmap">([\s\S]*?)<\/script>/);
const map = mapMatch ? JSON.parse(mapMatch[1]).imports : {};
const unresolved = bare.filter(s => {
  if (map[s]) return false;
  // import maps do PREFIX matching: a key ending in '/' replaces that
  // prefix, so 'three/addons/controls/OrbitControls.js' maps via 'three/addons/'
  return !Object.keys(map).some(k => k.endsWith('/') && s.startsWith(k));
});
add('import map resolves every bare import', unresolved.length === 0,
    unresolved.length ? 'unresolved: ' + unresolved.join(', ') : bare.join(' '));

// 2b. every import-map target must be a LOCAL file that exists.
//
// This is the check that was missing, and its absence is why the viewer
// appeared to work. The map pointed at unpkg.com, which "resolves" fine — a
// URL is a perfectly valid import-map value, and the check above only asked
// whether the KEY existed. The page then depended on a third-party CDN for
// its entire rendering engine: it fails closed (blank canvas, spinner
// forever, no error) the moment unpkg is unreachable, which is exactly what
// happened. The Draco decoder was already checked for this; three.js was
// not.
const remote = Object.entries(map).filter(([, v]) => /^https?:/.test(v));
add('import map has no remote (CDN) targets', remote.length === 0,
    remote.length ? remote.map(([k, v]) => `${k} -> ${v}`).join(' ') : 'all local');

// A prefix mapping like "three/addons/" covers many files, so probe the ones
// actually imported rather than trusting the directory to exist.
const mapTargets = [];
for (const spec of bare) {
  if (map[spec]) { mapTargets.push([spec, map[spec]]); continue; }
  const key = Object.keys(map).find(k => k.endsWith('/') && spec.startsWith(k));
  if (key) mapTargets.push([spec, map[key] + spec.slice(key.length)]);
}
const absent = mapTargets
  .filter(([, v]) => !/^https?:/.test(v))
  .filter(([, v]) => !existsSync(join(DOCS, v)));
add('every mapped module exists on disk', absent.length === 0,
    absent.length ? absent.map(([s, v]) => `${s} -> ${v}`).join(' ')
                  : `${mapTargets.length} modules`);

// 2c. the camera framing must be derived from the model, not hardcoded.
//
// The third column of VIEWS was an absolute distance in metres, tuned when
// the export was 84 meshes. At the 84-mesh stage 0.36 m framed the body; with
// the current 247-mesh export the same 0.36 m gives a view half-height of
// 0.124 m against a 0.139 m half-diagonal, so the camera sat inside the
// object's silhouette and every preset showed a cropped, unreadable face.
// The fix was to store a factor and derive the distance from the model's own
// bounding box, so this check now asserts the *mechanism* rather than a
// number that would drift again.
add('camera distance is derived from the model, not hardcoded',
    /fitDistance\s*\(/.test(src) && /modelRadius\s*\(/.test(src) &&
    /setViewImmediate\(\s*OPENING_AZ/.test(src),
    'fitDistance + modelRadius + initial view re-framed on load');

// 2d. every framing value must be a FACTOR, and a factor near 1 means "fit".
//
// A distance in metres and a factor are both decimals, so a regex cannot tell
// them apart and an earlier version of this check flagged the two close-up
// factors (0.62, 0.68) as "hardcoded distances" while the real 0.36 m
// distances passed. What is worth checking is the arithmetic: a fit distance
// for this model works out to ~0.42 m, and the metre distances the table used
// to hold were 0.36 and 0.42 - the same value as a legitimate fit factor. So
// assert the property that actually broke instead: the named constants the
// camera is aimed with must be factors, and 重置 must reuse the opening shot
// rather than passing a number of its own.
//
// The reset button called flyTo(215, 28, 0.42) - the 0.36/0.42 metre distance
// from the deleted table, passed where a framing factor belongs, so 重置
// zoomed the camera to 42% of the fit instead of restoring the opening view.
// It read as a plausible decimal, which is why nothing caught it.
//
// Scan CODE, not comments: the comment that records the bug quotes the very
// call this is looking for, and matching it would have kept the check red for
// ever while the bug was fixed. Every line whose first non-space character is
// / or * is dropped first.
const code = src.split('\n')
  .filter(l => !/^\s*(\/\/|\/\*|\*)/.test(l)).join('\n');
// Every call that positions the camera, and the three arguments it was given.
const framings = [...code.matchAll(/(?:flyTo|setViewImmediate)\(([^)]*)\)/g)]
  .map(m => m[1].replace(/\s+/g, ' ').trim());
// The check that actually works. An earlier version asserted only that
// OPENING_FIT was DEFINED somewhere, and the mutant that replaced the reset
// button's use of it with a literal 0.42 sailed straight through: the
// constant was still defined, just unused. So assert on the CALLS - no
// framing call may pass a bare decimal literal in the factor position, and
// 重置 in particular must reuse the named shot.
const literalFactors = framings.filter(f => /,\s*0?\.\d+\s*\)$/.test(f));
const resetFrame = (code.match(/reset[\s\S]{0,900}?\n\};/) || [''])[0];
const resetReuses = /OPENING_FIT/.test(resetFrame);
const resetDetail = !resetReuses
  ? '重置 does not use the opening shot'
  : literalFactors.length
    ? `a framing call passes a bare decimal: ${literalFactors.join(' | ')}`
    : 'all framing calls are named';
add('the reset button restores the opening shot, not a stale distance',
    !literalFactors.length && resetReuses &&
    /setViewImmediate\(\s*OPENING_AZ,\s*OPENING_EL,\s*OPENING_FIT\s*\)/.test(code) &&
    /const OPENING_FIT = 1\.00/.test(code),
    resetDetail);

// the opening shot must be aimed with the model's REAL axes. The export is
// Z-up converted: the front panel is at -Z and the height axis is Y, which
// this file's own comments asserted backwards for three commits.
const frontZ = (src.match(/Front_\*\s+\(USB-C[\s\S]{0,200}?z\s*(-?\d+\.\d+)\.\./) || [])[1];
add('the front/rear axis convention matches the export',
    /the front is -Z, the rear is \+Z/.test(src) && !!frontZ && frontZ.startsWith('-'),
    frontZ ? `front face measured at z ${frontZ}` : 'no measured axis in the comment');

// 3. clip planes are enabled on the renderer (three.js gates this)
add('renderer.localClippingEnabled = true', /localClippingEnabled\s*=\s*true/.test(src));
add('clip plane is applied to materials', /material\.clippingPlanes/.test(src));

// 4. the GLB path the loader requests
const glb = src.match(/loader\.load\(\s*['"]([^'"]+)['"]/);
add('GLTFLoader loads mac-studio.glb', glb && glb[1] === 'mac-studio.glb', glb ? glb[1] : 'not found');

// 5. Draco decoder path is configured and matches what three ships
const dp = src.match(/setDecoderPath\(['"]([^'"]+)['"]/);
add('DRACOLoader decoder path is local (no CDN dependency)',
    !!dp && !/^https?:/.test(dp[1]), dp ? dp[1] : 'not set');
// every local asset the viewer requests must exist on disk
const root = DOCS;
const localDeps = [
  ...(src.match(/setDecoderPath\(['"]([^'"]+)['"]\)/g) || [])
    .map(s => s.match(/['"]([^'"]+)['"]/)[1]),
  ...(src.match(/loader\.load\(\s*['"]([^'"]+)['"]/g) || [])
    .map(s => s.match(/['"]([^'"]+)['"]/)[1]),
];
const missingFiles = localDeps.filter(d => !/^https?:/.test(d) && !existsSync(root + d));
add('local viewer dependencies exist on disk', missingFiles.length === 0,
    missingFiles.length ? 'missing: ' + missingFiles.join(', ') : localDeps.join(' '));
const unused = [...src.matchAll(/^import \{ (\w+) \} from/gm)].map(m => m[1])
  .filter(n => (src.match(new RegExp('\\b' + n + '\\b', 'g')) || []).length < 2);
add('no unused imports', unused.length === 0, unused.length ? unused.join(', ') : '');
add('decoder type wasm (faster, and the .wasm is vendored)',
    /type:\s*['"]wasm['"]/.test(src) && existsSync(root + 'draco/draco_decoder.wasm'));
add('loading progress cannot exceed 100%',
    /Math\.min\(100/.test(src));
add('loader has a hang timeout', /setTimeout\([\s\S]{0,200}45000/.test(src));

// 6. the 8 named views exist
// 6. the view BUTTONS are gone, and nothing that drives them survived.
// d574dcf removed the row of named-view buttons because the mouse already
// orbits. This check used to assert "8 named camera views defined", so it went
// red on the commit that deleted them and stayed red - a gate left red is a
// gate nobody reads, and the two live bugs found next to it (the reset
// button's 0.42, the backwards axis comment) sat behind it.
//
// Assert the shape the page is SUPPOSED to have now: no table, no buttons in
// the markup, and the camera functions the render loop still needs.
const viewTable = /const VIEWS\s*=/.test(src);
const viewButtons = /data-view|VIEW_LABELS|onclick=.*flyTo/.test(src)
                 || /<button[^>]*data-view/.test(html);
add('the named-view table is gone, and nothing still drives it',
    !viewTable && !viewButtons,
    viewTable ? 'a VIEWS table is still defined' : 'no table, no buttons');
add('the camera helpers the render loop needs are all present',
    /function fitDistance\s*\(/.test(src) && /function flyTo\s*\(/.test(src) &&
    /function setViewImmediate\s*\(/.test(src) && /let tween = null/.test(src),
    'fitDistance + flyTo + setViewImmediate + tween');

// 7. classify() covers the toggle groups the panel still offers.
//
// The grille toggle went away with the rest of the honeycomb UI, and the
// perforated field is no longer separate geometry - it is cut into the shell
// itself - so a "hide the grille" branch would now take a piece of the body
// out of the machine. The remaining two groups are the ports and the feet.
const cls = src.match(/function classify\(name\) \{([\s\S]*?)\n\}/);
const clsBody = cls ? cls[1] : '';
add('visibility classification covers ports/feet and no longer the grille',
    /Port_/.test(clsBody) && /Front_/.test(clsBody) && /Foot_/.test(clsBody) &&
    !/Grille/i.test(clsBody),
    clsBody.replace(/\s+/g, ' ').trim().slice(0, 90));

// the panel must not still offer controls whose handler was deleted with the
// feature - the markup and the JS have to agree about what exists
const panelIds = [...html.matchAll(/<input[^>]*id="([\w-]+)"|<button[^>]*id="([\w-]+)"/g)]
  .map(m => m[1] || m[2]);
const deadControls = ['tGrille', 'tGrid', 'tViews', 'tFloor']
  .filter(id => panelIds.includes(id) || new RegExp(`['"]${id}['"]`).test(src));
add('no control markup survives for a feature that was removed',
    deadControls.length === 0,
    deadControls.length ? deadControls.join(' ') : `${panelIds.length} controls, all live`);

// 8. the render loop actually starts
add('animation loop started', /requestAnimationFrame\(animate\)/.test(src));

let fail = 0;
for (const [name, ok, extra] of checks) {
  if (!ok) fail++;
  console.log(`  ${ok ? 'OK  ' : 'FAIL'}  ${name}${extra ? '  (' + extra + ')' : ''}`);
}
console.log(fail ? `\n${fail} CHECK(S) FAILED` : '\nALL CHECKS PASSED');
process.exit(fail ? 1 : 0);
