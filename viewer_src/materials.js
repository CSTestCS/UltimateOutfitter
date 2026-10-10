// Material effects for the VRM preview: metallic reflections, silk sheen, wet gloss and
// semi-transparent thin clothing when wet. The model's textures are never modified - only how
// the preview renders them.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';

const NEVER_SEE_THROUGH = /skin|body|face|eye|hair|mouth|brow|lash|teeth|tongue|iris|highlight/i;
const METAL_WORDS = /metallic|metal|chrome|silver|gold|steel|iron|armor|armour/i;
const SILK_WORDS = /silk|satin/i;

let renderer = null;
let scene = null;
let envTexture = null;
let entries = [];          // one per (mesh, material slot)
let overlays = [];         // wet / silk gloss layers, one per mesh
let rules = { overrides: {}, matcapAsMetal: true };
let wet = { on: false, strength: 1, thin: [], thinOpacity: 0.7 };
let envIntensity = 1;

export function init(r, s) {
  renderer = r;
  scene = s;
  const pmrem = new THREE.PMREMGenerator(renderer);
  envTexture = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environment = envTexture;  // only affects standard / physical materials (MToon ignores it)
}

function texName(tex) {
  if (!tex) return '';
  return `${tex.name || ''} ${(tex.image && (tex.image.src || tex.image.currentSrc)) || ''}`;
}

// json material info from the glTF (metallicFactor survives in the file even for MToon)
function jsonInfo(gltfJson, name) {
  const mats = (gltfJson && gltfJson.materials) || [];
  const m = mats.find((x) => x.name === name);
  return {
    metallicFactor: m && m.pbrMetallicRoughness ? (m.pbrMetallicRoughness.metallicFactor ?? 0) : 0,
    roughnessFactor: m && m.pbrMetallicRoughness ? (m.pbrMetallicRoughness.roughnessFactor ?? 1) : 1,
  };
}

function overrideFor(name) {
  const low = name.toLowerCase();
  let best = null;
  for (const [key, effect] of Object.entries(rules.overrides || {})) {
    if (key && low.includes(key.toLowerCase()) && (!best || key.length > best[0].length)) best = [key, effect];
  }
  return best ? best[1] : null;
}

function classify(e) {
  const name = e.name;
  const ov = overrideFor(name);
  if (ov === 'none' || ov === 'thin' || ov === 'thick') e.forced = ov;
  if (ov === 'metallic' || ov === 'silk') return { effect: ov, why: 'materials.txt' };
  if (ov === 'none') return { effect: null, why: 'materials.txt' };
  const tname = texName(e.original.map);
  if (METAL_WORDS.test(name) || METAL_WORDS.test(tname)) return { effect: 'metallic', why: 'name' };
  if (SILK_WORDS.test(name) || SILK_WORDS.test(tname)) return { effect: 'silk', why: 'name' };
  if (e.json.metallicFactor >= 0.5) return { effect: 'metallic', why: 'metallic factor' };
  if (rules.matcapAsMetal && e.original.matcapTexture && !NEVER_SEE_THROUGH.test(name)) {
    return { effect: 'metallic', why: 'matcap (reflection) texture' };
  }
  return { effect: null, why: '' };
}

function makeMetal(src, json) {
  const color = src.color ? src.color.clone() : new THREE.Color(1, 1, 1);
  const m = new THREE.MeshStandardMaterial({
    name: src.name + ' (metal preview)',
    map: src.map || null,
    color,
    metalness: 1.0,
    roughness: Math.min(0.45, Math.max(0.12, json.roughnessFactor < 1 ? json.roughnessFactor : 0.25)),
    normalMap: src.normalMap || null,
    transparent: src.transparent,
    opacity: src.opacity ?? 1,
    alphaTest: src.alphaTest || 0,
    side: src.side,
    envMapIntensity: envIntensity * 1.2,
  });
  return m;
}

function glossMaterial(src) {
  // black base + additive blending: only the specular / clearcoat highlights are added on top
  const m = new THREE.MeshPhysicalMaterial({
    color: 0x000000,
    map: src && src.map ? src.map : null,
    alphaTest: src && src.map ? Math.max(src.alphaTest || 0, 0.3) : 0,
    roughness: 0.2,
    metalness: 0,
    clearcoat: 1,
    clearcoatRoughness: 0.08,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    polygonOffset: true,
    polygonOffsetFactor: -1,
    polygonOffsetUnits: -1,
    side: src ? src.side : THREE.FrontSide,
  });
  m.userData.isGloss = true;
  return m;
}

export function attach(vrm, gltfJson) {
  detach();
  vrm.scene.traverse((obj) => {
    if (!obj.isMesh || obj.userData.isGlossOverlay) return;
    const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
    const glossMats = [];
    mats.forEach((mat, index) => {
      const isOutline = !!mat.isOutline;
      if (!isOutline) {
        const e = {
          mesh: obj, index, name: mat.name || obj.name || '', original: mat, current: mat,
          json: jsonInfo(gltfJson, mat.name), effect: null, why: '', forced: null,
          base: { transparent: mat.transparent, opacity: mat.opacity ?? 1, depthWrite: mat.depthWrite },
        };
        entries.push(e);
        const g = glossMaterial(mat);
        g.userData.entry = e;
        e.gloss = g;
        glossMats.push(g);
      } else {
        const hidden = new THREE.MeshBasicMaterial({ visible: false });
        glossMats.push(hidden);
      }
    });
    const overlay = obj.isSkinnedMesh
      ? new THREE.SkinnedMesh(obj.geometry, Array.isArray(obj.material) ? glossMats : glossMats[0])
      : new THREE.Mesh(obj.geometry, Array.isArray(obj.material) ? glossMats : glossMats[0]);
    if (obj.isSkinnedMesh) overlay.bind(obj.skeleton, obj.bindMatrix);
    overlay.morphTargetInfluences = obj.morphTargetInfluences;   // shared: follows expressions
    overlay.morphTargetDictionary = obj.morphTargetDictionary;
    overlay.userData.isGlossOverlay = true;
    overlay.frustumCulled = false;
    overlay.castShadow = false;
    overlay.receiveShadow = false;
    overlay.renderOrder = (obj.renderOrder || 0) + 1;
    overlay.visible = false;
    obj.add(overlay);
    overlays.push(overlay);
  });
  reclassify();
}

export function detach() {
  for (const o of overlays) if (o.parent) o.parent.remove(o);
  overlays = [];
  entries = [];
}

function setSlot(e, mat) {
  const mats = e.mesh.material;
  if (Array.isArray(mats)) mats[e.index] = mat; else e.mesh.material = mat;
  e.current = mat;
}

function reclassify() {
  for (const e of entries) {
    e.forced = null;
    const c = classify(e);
    e.effect = c.effect;
    e.why = c.why;
    if (e.effect === 'metallic') {
      if (!e.metal) e.metal = makeMetal(e.original, e.json);
      setSlot(e, e.metal);
    } else {
      setSlot(e, e.original);
    }
  }
  apply();
}

function isThin(e) {
  if (e.forced === 'thin') return true;
  if (e.forced === 'thick' || NEVER_SEE_THROUGH.test(e.name)) return false;
  const low = e.name.toLowerCase();
  return (wet.thin || []).some((k) => k && low.includes(k.toLowerCase()));
}

function apply() {
  for (const e of entries) {
    const mat = e.current;
    // wet thin clothing becomes see-through
    const seeThrough = wet.on && isThin(e);
    const opacity = seeThrough ? Math.min(e.base.opacity, wet.thinOpacity) : e.base.opacity;
    const transparent = seeThrough ? true : (mat === e.original ? e.base.transparent : mat.transparent);
    if (mat.transparent !== transparent) { mat.transparent = transparent; mat.needsUpdate = true; }
    mat.opacity = opacity;
    if (mat === e.original) mat.depthWrite = seeThrough ? false : e.base.depthWrite;
    e.seeThrough = seeThrough;
    if (e.metal) e.metal.envMapIntensity = envIntensity * 1.2;
    // gloss layer: wet = whole body, silk = sheen on silk parts only
    const g = e.gloss;
    if (wet.on) {
      g.visible = true;
      g.roughness = 0.14;
      g.clearcoat = 1.0 * wet.strength;
      g.clearcoatRoughness = 0.06;
      g.opacity = 0.85 * wet.strength;
      g.envMapIntensity = envIntensity * 1.4;
    } else if (e.effect === 'silk') {
      g.visible = true;
      g.roughness = 0.38;
      g.clearcoat = 0.35;
      g.clearcoatRoughness = 0.3;
      g.opacity = 0.7;
      g.envMapIntensity = envIntensity * 0.8;
    } else {
      g.visible = false;
    }
  }
  for (const o of overlays) {
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    o.visible = mats.some((m) => m.userData.isGloss && m.visible);
  }
}

export function setRules(r) {
  rules = Object.assign({ overrides: {}, matcapAsMetal: true }, r || {});
  if (entries.length) reclassify();
}

export function setWet(w) {
  wet = Object.assign({ on: false, strength: 1, thin: [], thinOpacity: 0.7 }, w || {});
  apply();
}

export function setEnvIntensity(v) {
  envIntensity = v;
  apply();
}

export function list() {
  return entries.map((e) => ({
    name: e.name, effect: e.effect, why: e.why, thin: isThin(e), seeThrough: !!e.seeThrough,
    texture: texName(e.original.map).trim(), metallicFactor: e.json.metallicFactor,
    matcap: !!e.original.matcapTexture,
  }));
}
