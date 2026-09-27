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
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.localClippingEnabled = true;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
viewport.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x808080);

// Generated environment: a metal at roughness 0.19 is a mirror, and a flat
// background gives it nothing to reflect, which reads as matte plastic.
const pmrem = new THREE.PMREMGenerator(renderer);
const roomEnv = new RoomEnvironment();
const envRT = pmrem.fromScene(roomEnv, 0.04);
scene.environment = envRT.texture;

// ------------------------------------------------------------------ camera
const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 100);
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
const draco = new DRACOLoader();
draco.setDecoderPath('https://unpkg.com/three@0.169.0/examples/jsm/libs/draco/');
draco.setDecoderConfig({ type: 'js' });
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
    if (evt.lengthComputable && evt.total) {
      loading.textContent = `加载模型… ${Math.round(evt.loaded / evt.total * 100)}%`;
    }
  },
  (err) => {
    loading.innerHTML = `模型加载失败<br><small>${err.message || err}</small>`;
    console.error(err);
  }
);

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
// azimuth (deg, 270 = -Y = front), elevation (deg)
const VIEWS = [
  ['3/4 透视',  215, 28, 0.42],
  ['正面',      270,  8, 0.36],
  ['侧面',      180,  6, 0.36],
  ['背面',       90,  8, 0.36],
  ['顶视',      270, 78, 0.40],
  ['底视',      270, -62, 0.40],
  ['前脸特写',  270,  4, 0.20],
  ['接口特写',   90, 14, 0.22],
];

const viewsEl = document.getElementById('views');
let tween = null;

VIEWS.forEach(([label, az, el, dist], i) => {
  const b = document.createElement('button');
  b.className = 'btn' + (i === 0 ? ' on' : '');
  b.textContent = label;
  b.onclick = () => {
    viewsEl.querySelectorAll('.btn').forEach(x => x.classList.remove('on'));
    b.classList.add('on');
    flyTo(az, el, dist);
  };
  viewsEl.appendChild(b);
});

function flyTo(azDeg, elDeg, dist) {
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

function setViewImmediate(azDeg, elDeg, dist) {
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
