// Material effects for the VRM preview: metallic reflections, silk sheen, wet gloss and
// semi-transparent thin clothing when wet. The model's textures are never modified - only how
// the preview renders them.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';

const NEVER_SEE_THROUGH = /skin|body|face|eye|hair|mouth|brow|lash|teeth|tongue|iris|highlight/i;
// parts that never get darker when wet (skin and face); hair, clothing and accessories do
const SKIN = /skin|face|eye|mouth|brow|lash|teeth|tongue|iris|highlight/i;

let renderer = null;
let scene = null;
let envTexture = null;
let entries = [];          // one per (mesh, material slot)
let overlays = [];         // wet / silk gloss layers, one per mesh
let rules = { overrides: {} };
// strengths from preview_settings.txt
let settings = { metallic: 1, silk: 1, wetShine: 1, darken: 0.25, level: 1 };

// effective strengths from preview_settings.txt (0 = off, 1 = full, above 1 = brighter)
const metalS = () => settings.metallic * settings.level;
const silkS = () => settings.silk * settings.level;
const wetS = () => settings.wetShine * settings.level;
// how much of the full effect is blended in: every level up to full is a visible step
// (faint ~0.22, very low ~0.32, low ~0.49, medium ~0.66, high ~0.84, full 1)
const mix = (v) => (v <= 0 ? 0 : Math.min(1, Math.pow(v, 0.6)));
// levels above full make the effect brighter instead
const boost = (v) => Math.max(1, v);

// metal is always polished metal, blended over the model's own look by the level
function tuneMetal(m) {
  m.metalness = 1.0;
  m.roughness = 0.22;
  m.envMapIntensity = envIntensity * 1.2 * boost(metalS());
  m.userData.baseOpacity = mix(metalS());
}
let glossEnv = null;       // dark environment with a few bright panels: sharp highlights, no haze
let wet = { on: false, strength: 1, thin: [], thinOpacity: 0.7 };
let envIntensity = 1;
let matches = [];          // wardrobe pieces found among the model's textures (from Python)
let effectOverlays = [];   // masked metallic / silk layers for matched pieces
let outlines = [];         // MToon outline material slots: [{mesh, mat}]
let hiddenMaterials = new Set();  // model parts hidden because their pieces were taken off (from Python)
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
  // the body (skin, face, eyes) is never a wardrobe piece, whatever its texture looks like;
  // hair materials can be clothing made with VRoid's hair system, so they may match
  if (SKIN.test(e.name)) return null;
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
  // metallic / silk come only from wardrobe pieces (or materials.txt) - never from model names
  // note: the glTF metallicFactor and VRoid's matcap textures are NOT used - exporters set them on
  // many materials that are not metal, which made the choice look random
  return { effect: null, why: '' };
}

// silk / satin: a soft fabric sheen that glows towards the edges and broad, blurry highlights -
// clearly different from the sharp, mirror-like highlights of the wet look
function silkLook(g) {
  g.envMap = glossEnv;
  g.roughness = 0.5;
  g.clearcoat = 0;
  g.specularIntensity = 0.6;
  g.sheen = 1;
  g.sheenRoughness = 0.35;
  g.sheenColor.setRGB(1, 1, 1);
  g.opacity = Math.min(1, 0.75 * mix(silkS()));
  g.envMapIntensity = Math.max(0.6, envIntensity) * 0.7 * boost(silkS());
}

function glossMaterial(src) {
  // black base + additive blending: only the specular / clearcoat highlights are added on top
  const m = new THREE.MeshPhysicalMaterial({
    color: 0x000000,
    map: src && src.map ? src.map : null,
    // low cut-off: only fully transparent texels (hair cut-outs) are skipped, so weak levels still show
    alphaTest: src && src.map ? 0.02 : 0,
    roughness: 0.2,
    metalness: 0,
    clearcoat: 1,
    clearcoatRoughness: 0.08,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    // drawn on exactly the same surface: equal depth passes, so the layer never pokes through
    // clothing that lies close above it (e.g. underwear on skin)
    depthFunc: THREE.LessEqualDepth,
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
    setSlot(e, e.original);   // metal is drawn as a blended layer on top (see buildEffectOverlays)
  }
  buildEffectOverlays();
  apply();
}

function isThin(e) {
  // see-through when wet only for texture-matched thin wardrobe pieces (or a materials.txt rule)
  if (e.forced === 'thin') return true;
  if (e.forced === 'thick') return false;
  return !!(e.match && e.match.thin);
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
    applyDarkening(e);
    for (const o of effectOverlays) {
      const ms = Array.isArray(o.material) ? o.material : [o.material];
      for (const m of ms) {
        if (!m.userData.effectKind) continue;
        if (m.userData.effectKind === 'metallic') tuneMetal(m);
        if (m.userData.effectKind === 'silk') {
          silkLook(m);
          m.userData.baseOpacity = m.opacity;
        }
        // see-through thin clothing: the shine layer fades with the fabric
        const ent = m.userData.entry;
        m.opacity = m.userData.baseOpacity * (ent && ent.seeThrough ? wet.thinOpacity : 1);
      }
    }
    // pieces taken off are hidden (with their outline and effect layers)
    // only model parts whose texture matched a removed wardrobe piece are hidden
    e.hidden = hiddenMaterials.has(e.name);
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
      g.sheen = 0;
      g.specularIntensity = 1;
      g.opacity = Math.min(1, 0.85 * wet.strength * mix(wetS()));
      g.envMapIntensity = Math.max(0.6, envIntensity) * 1.1 * boost(wetS());
    } else if (e.effect === 'silk' && silkS() > 0) {
      g.visible = true;
      silkLook(g);
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
  hiddenMaterials = new Set((h && h.materials) || []);
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
      depthFunc: THREE.LessEqualDepth, side: src.side,
      envMapIntensity: envIntensity * 1.2 * boost(metalS()),
    });
  }
  const g = glossMaterial(src);   // silk: soft additive sheen limited by the mask
  g.alphaMap = mask;
  silkLook(g);
  return g;
}

function buildEffectOverlays() {
  clearEffectOverlays();
  for (const e of entries) {
    // whole parts that are metal (names, materials.txt, or an unmasked wardrobe match)
    if (e.effect === 'metallic') {
      const mat = maskedEffectMaterial(e, 'metallic', null);
      mat.userData.effectKind = 'metallic';
      mat.userData.entry = e;
      slotOverlay(e, mat);
    }
    if (!e.match) continue;
    for (const s of e.match.shine || []) {
      if (!s.maskUrl) continue;
      const mask = maskLoader.load(s.maskUrl);
      mask.flipY = false;               // glTF texture convention
      mask.colorSpace = THREE.NoColorSpace;
      const mat = maskedEffectMaterial(e, s.kind, mask);
      mat.userData.effectKind = s.kind;
      mat.userData.entry = e;
      if (s.kind !== 'metallic') mat.userData.baseOpacity = mat.opacity;
      slotOverlay(e, mat);
    }
  }
}

export function setMatches(list) {
  matches = list || [];
  if (entries.length) reclassify();
}

export function setRules(r) {
  rules = Object.assign({ overrides: {} }, r || {});
  if (entries.length) reclassify();
}

export function setSettings(v) {
  settings = Object.assign({ metallic: 1, silk: 1, wetShine: 1, darken: 0.25, level: 1 }, v || {});
  if (entries.length) reclassify();
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
    darkened: !!e.darkened, hidden: !!e.hidden, gloss: !!(e.gloss && e.gloss.visible),
    match: e.match ? { item: e.match.item_name, file: e.match.file, shine: (e.match.shine || []).map((s) => s.kind),
                       masked: (e.match.shine || []).some((s) => !!s.maskUrl) } : null,
    texture: texName(e.original.map).trim(), metallicFactor: e.json.metallicFactor,
    matcap: !!e.original.matcapTexture,
  }));
}
