/**
 * Interactive WebGL viewer for the Mac Studio model.
 *
 * Loads the GLB exported by blender/export_gltf.py and provides orbit
 * navigation, named camera views, per-part visibility, a real clipping plane
 * for cutaway inspection, and live PBR parameter control.
 *
 * Units: the GLB is authored in metres (Blender centimetres x 0.01), so the
 * model measures 0.197 x 0.197 x 0.095 m — real-world scale.
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const viewport = document.getElementById('viewport');
const loading = document.getElementById('loading');

// ---------------------------------------------------------------- renderer
// alpha:true and NO scene.background, so the canvas composites over the page
// instead of painting an opaque colour of its own.
//
// The combination this replaces was scene.background = 0x808080 with alpha
// false, and it had two consequences. From any angle the backdrop was a flat
// slab of grey at a fixed distance, so orbiting below the machine the ground
// simply was not there - the view filled with the same grey the walls had and
// the machine read as floating in a void. And because the backdrop was opaque,
// every drop of black the geometry produced landed on grey, which is how the
// rear panel's 16%-of-frame black came to read as a hole cut in the picture
// rather than as shadow.
//
// scene.environment still comes from RoomEnvironment below, so the aluminium
// has something to reflect. That is a LIGHTING source, not a backdrop, and it
// does not draw.
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.localClippingEnabled = true;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
// With nothing behind it the canvas would sit on the page's own background.
// Stating it explicitly keeps the page background in charge if the CSS changes.
renderer.setClearColor(0x000000, 0);
viewport.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = null;

// Generated environment: a metal at roughness 0.19 is a mirror, and a flat
// background gives it nothing to reflect, which reads as matte plastic.
const pmrem = new THREE.PMREMGenerator(renderer);
const roomEnv = new RoomEnvironment();
const envRT = pmrem.fromScene(roomEnv, 0.04);
scene.environment = envRT.texture;

// ------------------------------------------------------------------ camera
const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 100);
// The opening position is a placeholder; setViewImmediate() re-frames it from
// the model's real bounding box as soon as the GLB is parsed. A hardcoded
// value here is what left the first render cropped - the initial framing has
// to come from the model, not from a number typed before the model existed.
camera.position.set(0.34, -0.34, 0.24);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.minDistance = 0.12;
controls.maxDistance = 2.0;
controls.target.set(0, 0, 0.045);

// ------------------------------------------------------------------ lights
const key = new THREE.DirectionalLight(0xffffff, 2.6);
key.position.set(-0.5, -0.55, 0.7);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
key.shadow.camera.near = 0.05;
key.shadow.camera.far = 3;
const d = 0.35;
key.shadow.camera.left = -d; key.shadow.camera.right = d;
key.shadow.camera.top = d;   key.shadow.camera.bottom = -d;
key.shadow.bias = -0.0008;
scene.add(key);

const fill = new THREE.DirectionalLight(0xffffff, 0.9);
fill.position.set(0.6, -0.35, 0.3);
scene.add(fill);

const rim = new THREE.DirectionalLight(0xffffff, 1.4);
rim.position.set(0.1, 0.6, 0.45);
scene.add(rim);

const hemi = new THREE.HemisphereLight(0xf2f4f8, 0x4a4a4a, 0.35);
scene.add(hemi);

// -------------------------------------------------------------------- floor
const floor = new THREE.Mesh(
  new THREE.PlaneGeometry(4, 4),
  new THREE.MeshStandardMaterial({ color: 0x9a9a9c, roughness: 0.55, metalness: 0 })
);
floor.rotation.x = -Math.PI / 2;
floor.position.y = -0.0001;
floor.receiveShadow = true;
scene.add(floor);

const grid = new THREE.GridHelper(1.2, 24, 0x606060, 0x8a8a8a);
grid.position.y = 0.0002;
grid.material.transparent = true;
grid.material.opacity = 0.35;
grid.visible = false;
scene.add(grid);

// ------------------------------------------------------------------- model
const modelRoot = new THREE.Group();
scene.add(modelRoot);

const parts = { grille: [], ports: [], feet: [] };
const aluMaterials = new Set();
let wireGroup = null;
let boxSize = null;

/** Classify a node by name so the visibility toggles can address it. */
function classify(name) {
  if (/Grille/i.test(name)) return 'grille';
  if (/^Port_|^Front_|^RearBay/.test(name)) return 'ports';
  if (/^Foot_|^Power/.test(name)) return 'feet';
  return null;
}

const loader = new GLTFLoader();
// The Draco decoder is served from this origin, not a CDN. A CDN fetch here is
// a hard dependency for the model to appear at all: if unpkg is slow or
// blocked, the GLB never decodes and the viewer sits on the loading screen
// forever with no error.
const draco = new DRACOLoader();
draco.setDecoderPath('draco/');
draco.setDecoderConfig({ type: 'wasm' });
loader.setDRACOLoader(draco);

loader.load(
  'mac-studio.glb',
  (gltf) => {
    const root = gltf.scene;
    modelRoot.add(root);

    const box = new THREE.Box3().setFromObject(root);
    boxSize = box.getSize(new THREE.Vector3());
    const centre = box.getCenter(new THREE.Vector3());
    controls.target.set(centre.x, centre.y, centre.z);
    document.getElementById('dims').dataset.ready = '1';
    // Frame the opening shot from the box we just measured, using the same
    // fit every preset button uses. Without this the camera keeps whatever
    // position it was constructed with, and that number predates the model.
    setViewImmediate(...VIEWS[0].slice(1));

    root.traverse((o) => {
      if (!o.isMesh) return;
      o.castShadow = true;
      o.receiveShadow = true;
      const key = classify(o.name);
      if (key) parts[key].push(o);
      const m = o.material;
      if (m && !key) {
        if (m.isMeshStandardMaterial && m.metalness > 0.5) aluMaterials.add(m);
      }
    });

    buildWireframe(root);
    console.log('[viewer] loaded', root.name,
      'size(cm)=', boxSize.clone().multiplyScalar(100).toArray().map(v => v.toFixed(2)));
    loading.style.display = 'none';
    animate();
  },
  (evt) => {
    // Only trust the percentage when the browser reports a real total.
    // A Draco-compressed GLB streams through several fetches, and
    // lengthComputable is false for most of them — dividing by an unset
    // total yields nonsense like "568%".
    if (evt.lengthComputable && evt.total > 0) {
      const pct = Math.min(100, Math.round(evt.loaded / evt.total * 100));
      loading.innerHTML = `<span class="spinner"></span>加载模型… ${pct}%`;
    } else if (evt.loaded > 0) {
      loading.innerHTML = `<span class="spinner"></span>加载模型… ${(evt.loaded / 1048576).toFixed(1)} MB`;
    }
  },
  (err) => {
    loading.innerHTML = `模型加载失败<br><small>${err.message || err}</small>`;
    console.error(err);
  }
);

// A silent hang is worse than an error: if the GLB or the Draco decoder never
// arrives, the viewer would otherwise sit on the loading screen indefinitely
// with no explanation. Give it 45 s, then say so.
setTimeout(() => {
  if (loading.style.display !== 'none') {
    loading.innerHTML =
      '模型加载超时（45 秒）<br><small>GLB 或 Draco 解码器未能加载。<br>请检查网络后刷新。</small>';
  }
}, 45000);

/** Duplicate every mesh as a wireframe overlay (hidden by default). */
function buildWireframe(root) {
  wireGroup = new THREE.Group();
  wireGroup.visible = false;
  root.traverse((o) => {
    if (!o.isMesh) return;
    const wire = new THREE.Mesh(
      o.geometry,
      new THREE.MeshBasicMaterial({
        color: 0x00aaff, wireframe: true, transparent: true, opacity: 0.22,
        depthWrite: false,
      })
    );
    o.updateWorldMatrix(true, false);
    wire.applyMatrix4(o.matrixWorld);
    wireGroup.add(wire);
  });
  scene.add(wireGroup);
}

// ------------------------------------------------------------- camera views
// azimuth (deg), elevation (deg), and a FRAMING FACTOR - not a distance.
//
// Convention, and this is the third file to get it backwards: the exported
// GLB is +Y = FRONT (2x USB-C, SDXC, status LED) and -Y = REAR (the I/O row,
// the exhaust field, the power button), so
//   az  90 -> camera on +Y, looking at the FRONT
//   az 270 -> camera on -Y, looking at the REAR
// 正面 (front) and 背面 (rear) were swapped here exactly as they were in
// blender/render_views.py and blender/ortho_measure.py, and the comment above
// asserted the wrong convention, which is what made it look deliberate. The
// symptom: the 背面 button flew to the smooth front panel, so the one view
// that exists to show the ports and the perforated field showed a blank face.
//
// The third column used to be an absolute distance in metres (0.36, 0.42...)
// and every view was CROPPED: at a 38 deg vertical fov, 0.36 m gives a
// half-height of 0.124 m against the machine's 0.139 m half-diagonal, so the
// camera sat inside the object's own silhouette. Those numbers were tuned for
// an earlier 84-mesh export and were never re-derived. It is now a factor
// applied to the distance that actually fits the loaded bounding box, so the
// framing survives a change of model or of fov.
const VIEWS = [
  ['3/4 透视',  215, 28, 1.00],
  ['正面',       90,  8, 1.00],
  ['侧面',      180,  6, 1.00],
  ['背面',      270,  8, 1.00],
  ['顶视',       90, 78, 1.00],
  // -78, not -62: at -62 the camera is still well above the horizon, so this
  // showed the base band edge-on instead of the perforated bottom cover.
  ['底视',       90, -78, 1.00],
  // the two close-ups deliberately sit inside the object, so their factors
  // are well below 1 - they are meant to crop.
  ['前脸特写',   90,  4, 0.62],
  ['接口特写',  270, 14, 0.68],
];

/**
 * The distance at which a box of the given size exactly fills the frame.
 * Derived from the model's own bounding box, so it tracks the export.
 */
function fitDistance(radius, factor) {
  const vFov = THREE.MathUtils.degToRad(camera.fov);
  const hFov = 2 * Math.atan(Math.tan(vFov / 2) * camera.aspect);
  const limiting = Math.max(vFov, hFov);
  return (radius / Math.sin(limiting / 2)) * factor;
}

const viewsEl = document.getElementById('views');
let tween = null;

VIEWS.forEach(([label, az, el, factor], i) => {
  const b = document.createElement('button');
  b.className = 'btn' + (i === 0 ? ' on' : '');
  b.textContent = label;
  b.onclick = () => {
    viewsEl.querySelectorAll('.btn').forEach(x => x.classList.remove('on'));
    b.classList.add('on');
    flyTo(az, el, factor);
  };
  viewsEl.appendChild(b);
});

/** The model's bounding-sphere radius, once it has loaded. */
function modelRadius() {
  return boxSize ? boxSize.length() / 2 : 0.2;
}

function flyTo(azDeg, elDeg, factor) {
  const dist = fitDistance(modelRadius(), factor);
  const t = controls.target;
  const az = THREE.MathUtils.degToRad(azDeg);
  const el = THREE.MathUtils.degToRad(elDeg);
  const to = new THREE.Vector3(
    t.x + dist * Math.cos(el) * Math.cos(az),
    t.y + dist * Math.cos(el) * Math.sin(az),
    t.z + dist * Math.sin(el)
  );
  tween = { from: camera.position.clone(), to, t0: performance.now(), dur: 700 };
}

function setViewImmediate(azDeg, elDeg, factor) {
  const dist = fitDistance(modelRadius(), factor);
  const t = controls.target;
  const az = THREE.MathUtils.degToRad(azDeg);
  const el = THREE.MathUtils.degToRad(elDeg);
  camera.position.set(
    t.x + dist * Math.cos(el) * Math.cos(az),
    t.y + dist * Math.cos(el) * Math.sin(az),
    t.z + dist * Math.sin(el)
  );
  controls.update();
}

// -------------------------------------------------------------- visibility
function bindToggle(id, list) {
  const el = document.getElementById(id);
  el.onchange = () => list.forEach(o => { o.visible = el.checked; });
}

bindToggle('tGrille', parts.grille);
bindToggle('tPorts', parts.ports);
bindToggle('tFeet', parts.feet);

document.getElementById('tGrid').onchange = e => { grid.visible = e.target.checked; };
document.getElementById('tWire').onchange = e => { wireGroup.visible = e.target.checked; };

// ---------------------------------------------------------------- clipping
const clipPlane = new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0.05);
let clipEnabled = false;
let clipAxis = 'x';

const clipOn = document.getElementById('clipOn');
const clipPos = document.getElementById('clipPos');
const clipVal = document.getElementById('clipVal');
const clipAxisEl = document.getElementById('clipAxis');

function applyClip() {
  const half = 0.1;                       // 10 cm — covers the whole model
  const t = (clipPos.value / 100) * half;
  const normal = clipAxis === 'x' ? new THREE.Vector3(-1, 0, 0)
    : clipAxis === 'y' ? new THREE.Vector3(0, -1, 0)
    : new THREE.Vector3(0, 0, -1);
  clipPlane.normal.copy(normal);
  clipPlane.constant = t;
  const on = clipEnabled;
  modelRoot.traverse(o => {
    if (o.isMesh) {
      o.material.clippingPlanes = on ? [clipPlane] : null;
      o.material.clipShadows = on;
    }
  });
  if (wireGroup) {
    wireGroup.traverse(o => {
      if (o.isMesh) o.material.clippingPlanes = on ? [clipPlane] : null;
    });
  }
  clipVal.textContent = `${t.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')} cm`;
}

clipOn.onchange = e => { clipEnabled = e.target.checked; applyClip(); };
clipPos.oninput = () => applyClip();
clipAxisEl.querySelectorAll('button').forEach(b => {
  b.onclick = () => {
    clipAxisEl.querySelectorAll('button').forEach(x => x.classList.remove('on'));
    b.classList.add('on');
    applyClip();
  };
});

// ---------------------------------------------------------------- material
function bindSlider(id, outId, fn, fmt) {
  const el = document.getElementById(id);
  const out = document.getElementById(outId);
  const run = () => { const v = el.value / 100; fn(v); out.textContent = fmt(v); };
  el.oninput = run;
  run();
}

bindSlider('rough', 'roughVal', v => aluMaterials.forEach(m => { m.roughness = v; }), v => v.toFixed(2));
bindSlider('metal', 'metalVal', v => aluMaterials.forEach(m => { m.metalness = v; }), v => v.toFixed(2));
bindSlider('env', 'envVal', v => { scene.environmentIntensity = v; }, v => v.toFixed(2));
bindSlider('exposure', 'expVal', v => { renderer.toneMappingExposure = v; }, v => v.toFixed(2));

document.getElementById('reset').onclick = () => {
  document.getElementById('rough').value = 19;
  document.getElementById('metal').value = 100;
  document.getElementById('env').value = 100;
  document.getElementById('exposure').value = 100;
  ['rough', 'metal', 'env', 'exposure'].forEach(id => {
    document.getElementById(id).dispatchEvent(new Event('input'));
  });
  ['tGrille', 'tPorts', 'tFeet', 'tGrid', 'tWire', 'clipOn']
    .forEach(id => { document.getElementById(id).checked = (id === 'tGrille' || id === 'tPorts' || id === 'tFeet'); });
  parts.grille.concat(parts.ports, parts.feet).forEach(o => { o.visible = true; });
  grid.visible = false;
  wireGroup.visible = false;
  clipEnabled = false;
  clipPos.value = 0;
  applyClip();
  clipVal.textContent = '0.0 cm';
  flyTo(215, 28, 0.42);
  viewsEl.querySelectorAll('.btn').forEach((x, i) => x.classList.toggle('on', i === 0));
};

// -------------------------------------------------------------------- loop
function resize() {
  const w = viewport.clientWidth;
  const h = viewport.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
addEventListener('resize', resize);
resize();

function animate() {
  requestAnimationFrame(animate);
  if (tween) {
    const k = Math.min(1, (performance.now() - tween.t0) / tween.dur);
    const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
    camera.position.lerpVectors(tween.from, tween.to, e);
    if (k >= 1) tween = null;
  }
  controls.update();
  renderer.render(scene, camera);
}

// keyboard shortcuts
addEventListener('keydown', e => {
  if (e.key >= '1' && e.key <= '8') {
    const b = viewsEl.children[+e.key - 1];
    if (b) b.click();
  }
});
