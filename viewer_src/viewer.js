// 3D VRM viewport for Ultimate Outfitter's Interact tab.
// Bundled with esbuild into assets/viewer/viewer.bundle.js (run `npm run build` here).
// The Python side drives it through window.UO.* calls (QWebEnginePage.runJavaScript).
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { FBXLoader } from 'three/examples/jsm/loaders/FBXLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

// ---------------------------------------------------------------------------
// scene setup
// ---------------------------------------------------------------------------
const canvas = document.getElementById('view');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, preserveDrawingBuffer: true });
renderer.setPixelRatio(window.devicePixelRatio || 1);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(30, 1, 0.05, 200);
camera.position.set(0, 1.35, 2.6);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 1.2, 0);
controls.enableDamping = true;
controls.dampingFactor = 0.12;
controls.screenSpacePanning = true;
controls.minDistance = 0.2;
controls.maxDistance = 30;
controls.update();

const hemi = new THREE.HemisphereLight(0xffffff, 0x444444, 1.0);
scene.add(hemi);
const sun = new THREE.DirectionalLight(0xffffff, 2.0);
sun.position.set(1.5, 3, 2);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.near = 0.1;
sun.shadow.camera.far = 12;
sun.shadow.camera.left = -2; sun.shadow.camera.right = 2;
sun.shadow.camera.top = 3; sun.shadow.camera.bottom = -1;
sun.shadow.bias = -0.0005;
scene.add(sun);
const fill = new THREE.DirectionalLight(0xffffff, 0.5);
fill.position.set(-2, 1.5, -1);
scene.add(fill);

const floor = new THREE.Mesh(new THREE.CircleGeometry(1.6, 64),
  new THREE.ShadowMaterial({ opacity: 0.25 }));
floor.rotation.x = -Math.PI / 2;
floor.receiveShadow = true;
scene.add(floor);

// ---------------------------------------------------------------------------
// state
// ---------------------------------------------------------------------------
let vrm = null;
let mixer = null;
let currentAction = null;
let idleClip = null;
let emoteTimer = null;
let expressionWeights = {};       // mood expression {name: weight}
let reactionWeights = null;       // temporary reaction expression
let reactionUntil = 0;
let autoBlink = true;
let blinkTimer = 2 + Math.random() * 3;
let blinkPhase = 0;
let lookAtCamera = true;
let precipitation = null;
const clock = new THREE.Clock();
const status = document.getElementById('status');

function setStatus(text) {
  status.textContent = text || '';
  status.style.display = text ? 'block' : 'none';
}

// ---------------------------------------------------------------------------
// resize & render loop
// ---------------------------------------------------------------------------
function resize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / Math.max(h, 1);
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);
resize();

function applyExpressions(dt) {
  if (!vrm) return;
  const now = performance.now() / 1000;
  const weights = (reactionWeights && now < reactionUntil) ? reactionWeights : expressionWeights;
  const em = vrm.expressionManager;
  // reset everything we control
  if (em) {
    for (const exp of em.expressions) em.setValue(exp.expressionName, 0);
  }
  resetRawMorphs();
  let blinkSet = false;
  for (const [name, w] of Object.entries(weights || {})) {
    if (/^blink/i.test(name)) blinkSet = true;
    setNamedWeight(name, w);
  }
  // automatic blinking unless the mood already controls the eyelids
  if (autoBlink && !blinkSet && em && em.getExpression('blink')) {
    blinkTimer -= dt;
    if (blinkTimer <= 0) {
      blinkPhase += dt;
      const t = blinkPhase / 0.15;
      const v = t < 1 ? t : Math.max(0, 2 - t);
      em.setValue('blink', v);
      if (t >= 2) { blinkPhase = 0; blinkTimer = 2 + Math.random() * 4; }
    }
  }
}

const rawMorphCache = [];  // [{mesh, index}] touched last frame
function resetRawMorphs() {
  for (const { mesh, index } of rawMorphCache) mesh.morphTargetInfluences[index] = 0;
  rawMorphCache.length = 0;
}

function setNamedWeight(name, w) {
  const em = vrm.expressionManager;
  if (em && em.getExpression(name)) { em.setValue(name, w); return; }
  // not a VRM expression: try a raw blend shape (morph target) such as Fcl_ALL_Joy
  vrm.scene.traverse((obj) => {
    if (obj.isMesh && obj.morphTargetDictionary && name in obj.morphTargetDictionary) {
      const idx = obj.morphTargetDictionary[name];
      obj.morphTargetInfluences[idx] = w;
      rawMorphCache.push({ mesh: obj, index: idx });
    }
  });
}

function animate() {
  requestAnimationFrame(animate);
  const dt = Math.min(clock.getDelta(), 0.1);
  controls.update();
  if (mixer) mixer.update(dt);
  if (vrm) {
    if (vrm.lookAt) vrm.lookAt.target = lookAtCamera ? camera : null;
    applyExpressions(dt);
    vrm.update(dt);
  }
  if (precipitation) updatePrecipitation(dt);
  renderer.render(scene, camera);
}
animate();

// ---------------------------------------------------------------------------
// model loading
// ---------------------------------------------------------------------------
function frameModel() {
  if (!vrm) return;
  const box = new THREE.Box3().setFromObject(vrm.scene);
  const size = box.getSize(new THREE.Vector3());
  const head = vrm.humanoid && vrm.humanoid.getNormalizedBoneNode('head');
  const target = new THREE.Vector3();
  if (head) head.getWorldPosition(target); else box.getCenter(target);
  target.y -= size.y * 0.12;
  controls.target.copy(target);
  const dist = size.y * 1.15 + 0.4;
  camera.position.set(target.x, target.y + size.y * 0.05, target.z + dist);
  controls.update();
}

async function loadVRM(url) {
  setStatus('Loading model…');
  const loader = new GLTFLoader();
  loader.register((parser) => new VRMLoaderPlugin(parser));
  try {
    const gltf = await loader.loadAsync(url);
    const newVrm = gltf.userData.vrm;
    if (!newVrm) throw new Error('This file has no VRM data');
    VRMUtils.removeUnnecessaryVertices(gltf.scene);
    if (VRMUtils.combineSkeletons) VRMUtils.combineSkeletons(gltf.scene);
    VRMUtils.rotateVRM0(newVrm);
    newVrm.scene.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; } });
    if (vrm) { scene.remove(vrm.scene); VRMUtils.deepDispose(vrm.scene); }
    vrm = newVrm;
    scene.add(vrm.scene);
    mixer = new THREE.AnimationMixer(vrm.scene);
    currentAction = null;
    idleClip = null;
    relaxArms();
    frameModel();
    setStatus('');
    return { ok: true, expressions: listExpressions() };
  } catch (e) {
    setStatus('Could not load model: ' + e.message);
    return { ok: false, error: String(e.message || e) };
  }
}

function clearModel() {
  if (vrm) { scene.remove(vrm.scene); VRMUtils.deepDispose(vrm.scene); }
  vrm = null; mixer = null; currentAction = null; idleClip = null;
}

// arms down instead of a T-pose when no animation is playing
function relaxArms() {
  if (!vrm || !vrm.humanoid) return;
  const l = vrm.humanoid.getNormalizedBoneNode('leftUpperArm');
  const r = vrm.humanoid.getNormalizedBoneNode('rightUpperArm');
  if (l) l.rotation.z = -1.2;
  if (r) r.rotation.z = 1.2;
  const la = vrm.humanoid.getNormalizedBoneNode('leftLowerArm');
  const ra = vrm.humanoid.getNormalizedBoneNode('rightLowerArm');
  if (la) la.rotation.z = -0.15;
  if (ra) ra.rotation.z = 0.15;
}

function listExpressions() {
  const out = [];
  if (vrm && vrm.expressionManager) for (const e of vrm.expressionManager.expressions) out.push(e.expressionName);
  const morphs = new Set();
  if (vrm) vrm.scene.traverse((o) => {
    if (o.isMesh && o.morphTargetDictionary) for (const k of Object.keys(o.morphTargetDictionary)) morphs.add(k);
  });
  return { expressions: out, morphs: [...morphs] };
}

// ---------------------------------------------------------------------------
// FBX animations (Mixamo-style rigs) retargeted onto the VRM humanoid
// ---------------------------------------------------------------------------
const MIXAMO_TO_VRM = {
  Hips: 'hips', Spine: 'spine', Spine1: 'chest', Spine2: 'upperChest', Neck: 'neck', Head: 'head',
  LeftShoulder: 'leftShoulder', LeftArm: 'leftUpperArm', LeftForeArm: 'leftLowerArm', LeftHand: 'leftHand',
  LeftHandThumb1: 'leftThumbMetacarpal', LeftHandThumb2: 'leftThumbProximal', LeftHandThumb3: 'leftThumbDistal',
  LeftHandIndex1: 'leftIndexProximal', LeftHandIndex2: 'leftIndexIntermediate', LeftHandIndex3: 'leftIndexDistal',
  LeftHandMiddle1: 'leftMiddleProximal', LeftHandMiddle2: 'leftMiddleIntermediate', LeftHandMiddle3: 'leftMiddleDistal',
  LeftHandRing1: 'leftRingProximal', LeftHandRing2: 'leftRingIntermediate', LeftHandRing3: 'leftRingDistal',
  LeftHandPinky1: 'leftLittleProximal', LeftHandPinky2: 'leftLittleIntermediate', LeftHandPinky3: 'leftLittleDistal',
  RightShoulder: 'rightShoulder', RightArm: 'rightUpperArm', RightForeArm: 'rightLowerArm', RightHand: 'rightHand',
  RightHandThumb1: 'rightThumbMetacarpal', RightHandThumb2: 'rightThumbProximal', RightHandThumb3: 'rightThumbDistal',
  RightHandIndex1: 'rightIndexProximal', RightHandIndex2: 'rightIndexIntermediate', RightHandIndex3: 'rightIndexDistal',
  RightHandMiddle1: 'rightMiddleProximal', RightHandMiddle2: 'rightMiddleIntermediate', RightHandMiddle3: 'rightMiddleDistal',
  RightHandRing1: 'rightRingProximal', RightHandRing2: 'rightRingIntermediate', RightHandRing3: 'rightRingDistal',
  RightHandPinky1: 'rightLittleProximal', RightHandPinky2: 'rightLittleIntermediate', RightHandPinky3: 'rightLittleDistal',
  LeftUpLeg: 'leftUpperLeg', LeftLeg: 'leftLowerLeg', LeftFoot: 'leftFoot', LeftToeBase: 'leftToes',
  RightUpLeg: 'rightUpperLeg', RightLeg: 'rightLowerLeg', RightFoot: 'rightFoot', RightToeBase: 'rightToes',
};

function rigBoneName(name) {
  // accept "mixamorig:Hips", "mixamorigHips", "mixamorig1:Hips", plain "Hips"
  const m = name.match(/^(?:mixamorig\d*[:_]?)?(.+)$/i);
  return m ? m[1] : name;
}

const clipCache = new Map();

async function loadFBXClip(url) {
  if (!vrm) throw new Error('No model loaded');
  const key = url + '|' + vrm.scene.uuid;
  if (clipCache.has(key)) return clipCache.get(key);
  const asset = await new FBXLoader().loadAsync(url);
  const clip = THREE.AnimationClip.findByName(asset.animations, 'mixamo.com') || asset.animations[0];
  if (!clip) throw new Error('No animation in ' + url);
  const tracks = [];
  const restRotationInverse = new THREE.Quaternion();
  const parentRestWorldRotation = new THREE.Quaternion();
  const q = new THREE.Quaternion();
  const v = new THREE.Vector3();
  let hipsNode = null;
  asset.traverse((o) => { if (!hipsNode && rigBoneName(o.name) === 'Hips') hipsNode = o; });
  const motionHipsHeight = hipsNode ? Math.abs(hipsNode.position.y) || 1 : 1;
  const vrmHips = vrm.humanoid.getNormalizedBoneNode('hips');
  const vrmHipsY = vrmHips.getWorldPosition(v).y;
  const vrmRootY = vrm.scene.getWorldPosition(v).y;
  const hipsScale = Math.abs(vrmHipsY - vrmRootY) / motionHipsHeight;
  const isVrm0 = vrm.meta && vrm.meta.metaVersion === '0';
  for (const track of clip.tracks) {
    const [rigName, property] = track.name.split('.');
    const vrmBone = MIXAMO_TO_VRM[rigBoneName(rigName)];
    const vrmNode = vrmBone && vrm.humanoid.getNormalizedBoneNode(vrmBone);
    const rigNode = asset.getObjectByName(rigName);
    if (!vrmNode || !rigNode) continue;
    rigNode.getWorldQuaternion(restRotationInverse).invert();
    rigNode.parent.getWorldQuaternion(parentRestWorldRotation);
    if (track instanceof THREE.QuaternionKeyframeTrack) {
      const values = track.values.slice();
      for (let i = 0; i < values.length; i += 4) {
        q.fromArray(values, i);
        q.premultiply(parentRestWorldRotation).multiply(restRotationInverse);
        q.toArray(values, i);
      }
      tracks.push(new THREE.QuaternionKeyframeTrack(`${vrmNode.name}.${property}`, track.times,
        values.map((x, i) => (isVrm0 && i % 2 === 0 ? -x : x))));
    } else if (track instanceof THREE.VectorKeyframeTrack && vrmBone === 'hips' && property === 'position') {
      tracks.push(new THREE.VectorKeyframeTrack(`${vrmNode.name}.${property}`, track.times,
        track.values.map((x, i) => (isVrm0 && i % 3 !== 1 ? -x : x) * hipsScale)));
    }
  }
  const out = new THREE.AnimationClip(url.split('/').pop(), clip.duration, tracks);
  clipCache.set(key, out);
  return out;
}

async function playAnimation(url, opts = {}) {
  if (!vrm || !mixer) return { ok: false, error: 'No model loaded' };
  try {
    const clip = await loadFBXClip(url);
    const action = mixer.clipAction(clip);
    action.reset();
    action.setLoop(opts.loop === false ? THREE.LoopOnce : THREE.LoopRepeat, Infinity);
    action.clampWhenFinished = opts.loop === false;
    const fade = opts.fade ?? 0.35;
    if (currentAction && currentAction !== action) currentAction.crossFadeTo(action, fade, false);
    action.play();
    if (opts.loop !== false) {
      idleClip = url;
    } else {
      // emote: return to the idle afterwards
      clearTimeout(emoteTimer);
      const back = idleClip;
      emoteTimer = setTimeout(() => {
        if (back) playAnimation(back, { loop: true, fade: 0.5 });
        else stopAnimation();
      }, Math.max(0.2, clip.duration - fade) * 1000);
    }
    currentAction = action;
    return { ok: true, duration: clip.duration };
  } catch (e) {
    return { ok: false, error: String(e.message || e) };
  }
}

function stopAnimation() {
  if (mixer) mixer.stopAllAction();
  currentAction = null;
  idleClip = null;
  if (vrm) { vrm.humanoid.resetNormalizedPose(); relaxArms(); }
}

// ---------------------------------------------------------------------------
// lighting, sky and weather effects
// ---------------------------------------------------------------------------
const TIME_PRESETS = {
  //          sun colour, sun intensity, sun elevation, ambient sky, ambient ground, ambient intensity, sky top, sky bottom
  dawn:      [0xffb27a, 1.4, 0.25, 0xffd1b0, 0x403040, 0.7, 0x5a6fa8, 0xffb88a],
  morning:   [0xfff0d8, 2.2, 0.55, 0xdde8ff, 0x605848, 0.9, 0x6ea8ff, 0xd8ecff],
  day:       [0xffffff, 2.8, 0.95, 0xe8f2ff, 0x6a6458, 1.0, 0x4a90e8, 0xbfe0ff],
  evening:   [0xff9a5a, 1.6, 0.18, 0xffc8a0, 0x403040, 0.7, 0x3a3f80, 0xff9a6a],
  night:     [0x9fb4ff, 0.6, 0.7, 0x5060a0, 0x101020, 0.45, 0x050816, 0x1a2244],
};
const WEATHER_MODS = {
  // sun intensity multiplier, ambient multiplier, tint (lerp to), tint amount, sky desaturation, precipitation
  'Scorching hot':      [1.25, 1.05, 0xffe2b0, 0.25, 0.0, null],
  'Warm':               [1.1, 1.0, 0xfff0d0, 0.12, 0.0, null],
  'Mild':               [1.0, 1.0, 0xffffff, 0.0, 0.0, null],
  'Cool':               [0.85, 1.0, 0xd8e6ff, 0.2, 0.15, null],
  'Cold':               [0.7, 1.0, 0xc8dcff, 0.3, 0.3, null],
  'Freezing / snowy':   [0.55, 1.15, 0xe0ecff, 0.45, 0.55, 'snow'],
  'Rainy':              [0.35, 0.85, 0x9aa8b8, 0.5, 0.7, 'rain'],
  'Windy':              [0.9, 1.0, 0xe8eef4, 0.15, 0.25, null],
};
let sky = { top: new THREE.Color(0x4a90e8), bottom: new THREE.Color(0xbfe0ff) };
let background = { mode: 'sky' };

function timeFromHour(h) {
  if (h < 5 || h >= 21) return 'night';
  if (h < 7) return 'dawn';
  if (h < 11) return 'morning';
  if (h < 17) return 'day';
  return 'evening';
}

function setLighting(opts = {}) {
  const time = opts.time && opts.time !== 'auto' ? opts.time : timeFromHour(new Date().getHours());
  const p = TIME_PRESETS[time] || TIME_PRESETS.day;
  const w = WEATHER_MODS[opts.weather] || WEATHER_MODS.Mild;
  const tint = new THREE.Color(w[2]);
  const sunColor = new THREE.Color(p[0]).lerp(tint, w[3]);
  sun.color.copy(sunColor);
  sun.intensity = p[1] * w[0];
  const elev = p[2];
  sun.position.set(1.8 * Math.cos(elev) , 0.4 + 4 * elev, 2.2 * Math.cos(elev));
  hemi.color.set(p[3]).lerp(tint, w[3]);
  hemi.groundColor.set(p[4]);
  hemi.intensity = p[5] * w[1];
  fill.intensity = 0.35 * w[1];
  const grey = (c) => { const l = c.r * 0.3 + c.g * 0.59 + c.b * 0.11; return new THREE.Color(l, l, l); };
  const top = new THREE.Color(p[6]); const bottom = new THREE.Color(p[7]);
  sky.top = top.lerp(grey(top), w[4]);
  sky.bottom = bottom.lerp(grey(bottom), w[4]);
  setPrecipitation(w[5]);
  if (background.mode === 'sky') applyBackground();
  return { time };
}

function gradientTexture(top, bottom) {
  const c = document.createElement('canvas');
  c.width = 4; c.height = 256;
  const g = c.getContext('2d');
  const grad = g.createLinearGradient(0, 0, 0, 256);
  grad.addColorStop(0, '#' + top.getHexString());
  grad.addColorStop(1, '#' + bottom.getHexString());
  g.fillStyle = grad; g.fillRect(0, 0, 4, 256);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function applyBackground() {
  if (background.mode === 'color') {
    scene.background = new THREE.Color(background.color || '#404040');
  } else if (background.mode === 'image' && background.url) {
    new THREE.TextureLoader().load(background.url, (tex) => {
      tex.colorSpace = THREE.SRGBColorSpace;
      scene.background = tex;
    });
  } else {
    scene.background = gradientTexture(sky.top, sky.bottom);
  }
}

function setBackground(opts) {
  background = Object.assign({ mode: 'sky' }, opts || {});
  applyBackground();
}

function setPrecipitation(kind) {
  if (precipitation && precipitation.kind === kind) return;
  if (precipitation) { scene.remove(precipitation.points); precipitation.points.geometry.dispose(); }
  precipitation = null;
  if (!kind) return;
  const rain = kind === 'rain';
  const n = rain ? 2500 : 1500;
  const per = rain ? 2 : 1;  // rain drops are short line streaks, snowflakes are points
  const pos = new Float32Array(n * 3 * per);
  for (let i = 0; i < n; i++) {
    const x = (Math.random() - 0.5) * 8, y = Math.random() * 5, z = (Math.random() - 0.5) * 8;
    for (let k = 0; k < per; k++) {
      const j = (i * per + k) * 3;
      pos[j] = x + k * 0.01; pos[j + 1] = y + k * 0.12; pos[j + 2] = z;
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const points = rain
    ? new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: 0xb0c0d8, transparent: true, opacity: 0.55, depthWrite: false }))
    : new THREE.Points(geo, new THREE.PointsMaterial({ color: 0xffffff, size: 0.04, transparent: true, opacity: 0.9, depthWrite: false }));
  scene.add(points);
  precipitation = { kind, points, per };
}

function updatePrecipitation(dt) {
  const arr = precipitation.points.geometry.attributes.position.array;
  const rain = precipitation.kind === 'rain';
  const speed = rain ? 6 : 0.6;
  const stride = 3 * precipitation.per;
  const t = performance.now() / 1000;
  for (let i = 0; i < arr.length; i += stride) {
    let dy = -speed * dt;
    if (arr[i + 1] + dy < 0) dy += 5;
    for (let k = 0; k < precipitation.per; k++) {
      arr[i + k * 3 + 1] += dy;
      if (!rain) arr[i + k * 3] += Math.sin(t + i) * 0.002;
    }
  }
  precipitation.points.geometry.attributes.position.needsUpdate = true;
}

// ---------------------------------------------------------------------------
// public API (called from Python)
// ---------------------------------------------------------------------------
window.UO = {
  ready: true,
  loadVRM,
  clearModel,
  frame: frameModel,
  setExpression(weights) { expressionWeights = weights || {}; return true; },
  react(weights, seconds) { reactionWeights = weights || null; reactionUntil = performance.now() / 1000 + (seconds || 2.5); return true; },
  setAutoBlink(on) { autoBlink = !!on; return true; },
  setLookAtCamera(on) { lookAtCamera = !!on; return true; },
  setLighting,
  setBackground,
  playAnimation,
  stopAnimation,
  listExpressions,
  screenshot() { renderer.render(scene, camera); return renderer.domElement.toDataURL('image/png'); },
  info() { return { model: !!vrm, idle: idleClip, expression: expressionWeights }; },
};
setLighting({ weather: 'Mild', time: 'auto' });
window.addEventListener('keydown', (e) => { if (e.key === 'f' || e.key === 'F') frameModel(); });
