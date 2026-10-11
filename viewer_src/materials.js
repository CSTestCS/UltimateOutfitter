// Material effects for the VRM preview: metallic reflections, silk sheen, wet gloss and
// semi-transparent thin clothing when wet. The model's textures are never modified - only how
// the preview renders them.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';

const NEVER_SEE_THROUGH = /skin|body|face|eye|hair|mouth|brow|lash|teeth|tongue|iris|highlight/i;
// parts that never get darker when wet (skin and face); hair, clothing and accessories do
const SKIN = /skin|face|eye|mouth|brow|lash|teeth|tongue|iris|highlight/i;
const METAL_WORDS = /metallic|metal|chrome|silver|gold|steel|iron|armor|armour/i;
const SILK_WORDS = /silk|satin/i;

let renderer = null;
let scene = null;
let envTexture = null;
let entries = [];          // one per (mesh, material slot)
let overlays = [];         // wet / silk gloss layers, one per mesh
let rules = { overrides: {} };
// strengths from preview_settings.txt
let settings = { metallic: 1, silk: 1, wetShine: 1, darken: 0.25, level: 1 };

// effective strengths: preview_settings.txt value x the Interact tab's Shine level
const metalS = () => settings.metallic * settings.level;
const silkS = () => settings.silk * settings.level;
const wetS = () => settings.wetShine * settings.level;

// weak metal is a mostly matte, slightly reflective surface; full strength is polished metal
function tuneMetal(m, masked) {
  const sv = metalS();
  const t = Math.min(1, sv);
  m.metalness = 0.1 + 0.9 * t;
  m.roughness = 0.22 + 0.5 * (1 - t);
  m.envMapIntensity = envIntensity * 1.2 * Math.max(0.15, sv);
  if (masked) m.userData.baseOpacity = Math.min(1, 0.15 + 0.85 * t);
}
let glossEnv = null;       // dark environment with a few bright panels: sharp highlights, no haze
let wet = { on: false, strength: 1, thin: [], thinOpacity: 0.7 };
let envIntensity = 1;
let matches = [];          // wardrobe pieces found among the model's textures (from Python)
let effectOverlays = [];   // masked metallic / silk layers for matched pieces
let outlines = [];         // MToon outline material slots: [{mesh, mat}]
let hiddenEntries = new Set();   // wardrobe entry ids taken off - their model parts are hidden
let hiddenWords = [];            // fallback material-name words for removed pieces with no texture match
const maskLoader = new THREE.TextureLoader();

export function init(r, s) {
  renderer = r;
  scene = s;
  const pmrem = new THREE.PMREMGenerator(renderer);
  envTexture = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environment = envTexture;  // only affects standard / physical materials (MToon ignores it)
  glossEnv = pmrem.fromScene(highlightRoom(), 0.02).texture;
}

// a black room with a few bright soft-boxes: reflecting it gives the crisp highlights of a wet or
// glossy surface without washing the colours out
function highlightRoom() {
  const room = new THREE.Scene();
  room.background = new THREE.Color(0x000000);
  const panel = (w, h, x, y, z, intensity) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(intensity, intensity, intensity), side: THREE.DoubleSide }));
    m.position.set(x, y, z);
    m.lookAt(0, 0, 0);
    room.add(m);
  };
  panel(3, 2, 2.5, 3, 4, 6);      // key light, front right above
  panel(1.2, 4, -4, 1, 1, 3);     // tall strip on the left
  panel(4, 1, 0, 5, -2, 4);       // top / back rim
  panel(2, 1, 0, -3, 3, 0.6);     // faint bounce from below
  return room;
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

function matchFor(e) {
  return matches.find((m) => m.material === e.name) || null;
}

function classify(e) {
  const name = e.name;
  const m = matchFor(e);
  if (m) {
    e.match = m;
    // a matched piece with a mask gets a masked overlay instead of a whole-material swap
    const unmasked = (m.shine || []).find((s) => !s.maskUrl);
    if (unmasked) return { effect: unmasked.kind, why: `wardrobe piece "${m.item_name}"` };
    if ((m.shine || []).length) return { effect: null, why: `wardrobe piece "${m.item_name}" (masked)` };
  } else {
    e.match = null;
  }
  const ov = overrideFor(name);
  if (ov === 'none' || ov === 'thin' || ov === 'thick') e.forced = ov;
  if (ov === 'metallic' || ov === 'silk') return { effect: ov, why: 'materials.txt' };
  if (ov === 'none') return { effect: null, why: 'materials.txt' };
  const tname = texName(e.original.map);
  if (METAL_WORDS.test(name) || METAL_WORDS.test(tname)) return { effect: 'metallic', why: 'name' };
  if (SILK_WORDS.test(name) || SILK_WORDS.test(tname)) return { effect: 'silk', why: 'name' };
  // note: the glTF metallicFactor and VRoid's matcap textures are NOT used - exporters set them on
  // many materials that are not metal, which made the choice look random
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
    envMapIntensity: envIntensity * 1.2 * settings.metallic,
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
  matches = [];
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
        outlines.push({ mesh: obj, mat });
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
  clearEffectOverlays();
  entries = [];
  outlines = [];
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
    if (e.effect === 'metallic' && metalS() > 0) {
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
  if (e.match && e.forced !== 'thick') return !!e.match.thin;
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
    if (e.metal) tuneMetal(e.metal, false);
    applyDarkening(e);
    for (const o of effectOverlays) {
      const ms = Array.isArray(o.material) ? o.material : [o.material];
      for (const m of ms) {
        if (!m.userData.effectKind) continue;
        if (m.userData.effectKind === 'metallic') tuneMetal(m, true);
        if (m.userData.effectKind === 'silk') {
          m.userData.baseOpacity = 0.35 * Math.min(1, silkS());
          m.envMapIntensity = Math.max(0.6, envIntensity) * 0.5 * silkS();
        }
        // see-through thin clothing: the shine layer fades with the fabric
        const ent = m.userData.entry;
        m.opacity = m.userData.baseOpacity * (ent && ent.seeThrough ? wet.thinOpacity : 1);
      }
    }
    // pieces taken off are hidden (with their outline and effect layers)
    e.hidden = e.match ? hiddenEntries.has(e.match.entry_id)
      : (!NEVER_SEE_THROUGH.test(e.name) && hiddenWords.some((w) => w && e.name.toLowerCase().includes(w.toLowerCase())));
    mat.visible = !e.hidden;
    // gloss layer: wet = whole body, silk = sheen on silk parts only
    const g = e.gloss;
    if (wet.on && wetS() > 0) {
      // wet: crisp highlights over the whole character (skin, hair, clothing, accessories)
      g.visible = true;
      g.envMap = glossEnv;
      g.roughness = 0.12;
      g.clearcoat = 1;
      g.clearcoatRoughness = 0.04;
      g.opacity = Math.min(1, 0.85 * wet.strength * wetS());
      g.envMapIntensity = Math.max(0.6, envIntensity) * 1.1 * wetS();
      g.clearcoatRoughness = 0.04 + 0.25 * (1 - Math.min(1, wetS()));
    } else if (e.effect === 'silk' && silkS() > 0) {
      g.visible = true;
      g.envMap = glossEnv;
      g.roughness = 0.4;
      g.clearcoat = 0.3;
      g.clearcoatRoughness = 0.35;
      g.opacity = Math.min(1, 0.45 * silkS());
      g.envMapIntensity = Math.max(0.6, envIntensity) * 0.5 * silkS();
    } else {
      g.visible = false;
    }
  }
  for (const e of entries) if (e.hidden) e.gloss.visible = false;
  for (const o of overlays) {
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    o.visible = mats.some((m) => m.userData.isGloss && m.visible);
  }
  for (const o of effectOverlays) {
    const ms = Array.isArray(o.material) ? o.material : [o.material];
    o.visible = !ms.some((m) => (m.userData.entry && m.userData.entry.hidden)
      || (m.userData.effectKind === 'metallic' && metalS() <= 0)
      || (m.userData.effectKind === 'silk' && silkS() <= 0));
  }
  for (const { mesh, mat } of outlines) {
    mat.visible = !entries.some((e) => e.hidden && e.mesh === mesh && mat.name && e.name && mat.name.startsWith(e.name));
  }
}

export function setHidden(h) {
  hiddenEntries = new Set((h && h.entries) || []);
  hiddenWords = (h && h.words) || [];
  apply();
  return entries.filter((e) => e.hidden).map((e) => e.name);
}

function clearEffectOverlays() {
  for (const o of effectOverlays) if (o.parent) o.parent.remove(o);
  effectOverlays = [];
}

// a copy of the mesh that only draws one material slot, with ``mat``
function slotOverlay(e, mat) {
  const src = e.mesh;
  const mats = Array.isArray(src.material)
    ? src.material.map((_, i) => (i === e.index ? mat : new THREE.MeshBasicMaterial({ visible: false })))
    : mat;
  const o = src.isSkinnedMesh ? new THREE.SkinnedMesh(src.geometry, mats) : new THREE.Mesh(src.geometry, mats);
  if (src.isSkinnedMesh) o.bind(src.skeleton, src.bindMatrix);
  o.morphTargetInfluences = src.morphTargetInfluences;
  o.morphTargetDictionary = src.morphTargetDictionary;
  o.userData.isGlossOverlay = true;
  o.frustumCulled = false;
  o.castShadow = false;
  o.renderOrder = (src.renderOrder || 0) + 1;
  src.add(o);
  effectOverlays.push(o);
  return o;
}

function maskedEffectMaterial(e, kind, mask) {
  const src = e.original;
  if (kind === 'metallic') {
    return new THREE.MeshStandardMaterial({
      map: src.map || null, color: src.color ? src.color.clone() : new THREE.Color(1, 1, 1),
      metalness: 1.0, roughness: 0.22, alphaMap: mask, transparent: true, depthWrite: false,
      polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1, side: src.side,
      envMapIntensity: envIntensity * 1.2 * settings.metallic,
    });
  }
  const g = glossMaterial(src);   // silk: soft additive sheen limited by the mask
  g.alphaMap = mask;
  g.envMap = glossEnv;
  g.roughness = 0.4; g.clearcoat = 0.3; g.clearcoatRoughness = 0.35; g.opacity = 0.35 * Math.min(1, silkS());
  g.envMapIntensity = Math.max(0.6, envIntensity) * 0.5 * silkS();
  return g;
}

function buildEffectOverlays() {
  clearEffectOverlays();
  for (const e of entries) {
    if (!e.match) continue;
    for (const s of e.match.shine || []) {
      if (!s.maskUrl) continue;
      const mask = maskLoader.load(s.maskUrl);
      mask.flipY = false;               // glTF texture convention
      mask.colorSpace = THREE.NoColorSpace;
      const mat = maskedEffectMaterial(e, s.kind, mask);
      mat.userData.effectKind = s.kind;
      mat.userData.entry = e;
      mat.userData.baseOpacity = mat.opacity;
      slotOverlay(e, mat);
    }
  }
}

export function setMatches(list) {
  matches = list || [];
  if (entries.length) { reclassify(); buildEffectOverlays(); apply(); }
}

export function setRules(r) {
  rules = Object.assign({ overrides: {} }, r || {});
  if (entries.length) reclassify();
}

export function setSettings(v) {
  settings = Object.assign({ metallic: 1, silk: 1, wetShine: 1, darken: 0.25, level: 1 }, v || {});
  if (entries.length) { reclassify(); buildEffectOverlays(); apply(); }
}

// ---------------------------------------------------------------------------
// wet darkening: soaked fabric, hair and accessories look darker (not thin, metallic, silk or skin)
// ---------------------------------------------------------------------------
function darkens(e) {
  if (SKIN.test(e.name) && !/hair/i.test(e.name)) return false;
  if (/body/i.test(e.name) && !/cloth|tops|bottoms|onepiece|shoes|accessory/i.test(e.name)) return false;
  if (e.effect === 'metallic' || e.effect === 'silk' || isThin(e)) return false;
  if (e.match && (e.match.shine || []).some((s) => s.kind === 'silk')) return false;
  return true;
}

const COLOR_KEYS = ['color', 'shadeColorFactor'];
function applyDarkening(e) {
  const mat = e.original;
  if (!e.baseColors) {
    e.baseColors = {};
    for (const k of COLOR_KEYS) if (mat[k] && mat[k].isColor) e.baseColors[k] = mat[k].clone();
  }
  const amount = wet.on && darkens(e) ? Math.min(0.9, settings.darken * Math.max(0.5, wet.strength)) : 0;
  e.darkened = amount > 0;
  for (const [k, c] of Object.entries(e.baseColors)) mat[k].copy(c).multiplyScalar(1 - amount);
}

export function setWet(w) {
  wet = Object.assign({ on: false, strength: 1, thin: [], thinOpacity: 0.7 }, w || {});
  if (w && w.settings) settings = Object.assign(settings, w.settings);
  apply();
}

export function setEnvIntensity(v) {
  envIntensity = v;
  apply();
}

export function list() {
  return entries.map((e) => ({
    name: e.name, effect: e.effect, why: e.why, thin: isThin(e), seeThrough: !!e.seeThrough,
    darkened: !!e.darkened, hidden: !!e.hidden,
    match: e.match ? { item: e.match.item_name, file: e.match.file, shine: (e.match.shine || []).map((s) => s.kind),
                       masked: (e.match.shine || []).some((s) => !!s.maskUrl) } : null,
    texture: texName(e.original.map).trim(), metallicFactor: e.json.metallicFactor,
    matcap: !!e.original.matcapTexture,
  }));
}
