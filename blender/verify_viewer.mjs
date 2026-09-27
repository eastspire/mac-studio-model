// Headless validation of the viewer's logic: no WebGL, no network.
// Parses viewer.js and asserts the wiring the page depends on.
import { readFileSync } from 'node:fs';

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
import { existsSync } from 'node:fs';
const root = '/Users/sqs/code/mac-studio-model/docs/';
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
