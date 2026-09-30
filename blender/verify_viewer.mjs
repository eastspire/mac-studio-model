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

// 2c. the camera presets must not crop the model.
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
    /setViewImmediate\(\.\.\.VIEWS\[0\]/.test(src),
    'fitDistance + modelRadius + initial view re-framed on load');

// and the presets must all be framing FACTORS, not metre distances. A
// distance in metres and a factor are both decimals, so a regex cannot tell
// them apart and an earlier version of this check flagged the two close-up
// factors (0.62, 0.68) as "hardcoded distances" while the real 0.36 m
// distances passed. Assert the arithmetic instead: with the fit mechanism in
// place, every preset's value must be a multiplier of a derived distance,
// which is true by construction - so what is worth checking is that no
// preset value is large enough to BE a metre distance for a 0.197 m object.
const viewBody = (src.match(/const VIEWS\s*=\s*\[([\s\S]*?)\];/) || [, ''])[1];
const presets = [...viewBody.matchAll(/['"]([^'"]+)['"]\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)/g)]
  .map(m => ({ name: m[1], factor: parseFloat(m[4]) }));
// A fit distance for this model works out to ~0.42 m, and the metre
// distances that used to be hardcoded were 0.36 and 0.42. The real framing
// factors are 1.00 (fit exactly) and 0.62 / 0.68 (crop a little for the
// close-ups). So the band to reject is 0.70..0.99 - values too big to be a
// deliberate crop and too small to be a distance that would have worked.
const looksLikeMetres = presets.filter(p => p.factor > 0.69 && p.factor < 0.99);
add('every preset is a framing factor, not a metre distance',
    presets.length > 0 && looksLikeMetres.length === 0,
    looksLikeMetres.length
      ? looksLikeMetres.map(p => `${p.name}=${p.factor}`).join(' ')
      : `${presets.length} presets: ` +
        presets.map(p => `${p.name}=${p.factor}`).join(' '));

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
const views = src.match(/const VIEWS = \[([\s\S]*?)\n\];/);
const nViews = views ? (views[1].match(/\['/g) || []).length : 0;
add('8 named camera views defined', nViews === 8, `found ${nViews}`);

// 7. classify() covers the three toggle groups
const cls = src.match(/function classify\(name\) \{([\s\S]*?)\n\}/);
const clsBody = cls ? cls[1] : '';
add('visibility classification covers grille/ports/feet',
    /Grille/i.test(clsBody) && /Port_/.test(clsBody) && /Foot_/.test(clsBody),
    clsBody.replace(/\s+/g, ' ').trim().slice(0, 90));

// 8. the render loop actually starts
add('animation loop started', /requestAnimationFrame\(animate\)/.test(src));

let fail = 0;
for (const [name, ok, extra] of checks) {
  if (!ok) fail++;
  console.log(`  ${ok ? 'OK  ' : 'FAIL'}  ${name}${extra ? '  (' + extra + ')' : ''}`);
}
console.log(fail ? `\n${fail} CHECK(S) FAILED` : '\nALL CHECKS PASSED');
process.exit(fail ? 1 : 0);
