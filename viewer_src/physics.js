// Spring-bone physics for the VRM preview: hair, skirts, ribbons and other parts that the model
// marks as spring bones swing with movement, sag a little more when wet and blow in the wind.
// three-vrm simulates the bones in vrm.update(); this module tunes their settings every frame and
// adds a gentle idle sway so the physics is visible even when no animation is playing.
import * as THREE from 'three';

let vrm = null;
let base = new Map();     // joint -> its original settings
let opts = { enabled: true, stiffness: 1, wind: 0, wet: 0 };
let time = 0;
let swayBones = [];
const windDir = new THREE.Vector3(1, 0, -0.35).normalize();
const tmp = new THREE.Vector3();

export function attach(v) {
  vrm = v;
  base = new Map();
  const sbm = v && v.springBoneManager;
  if (!sbm) return 0;
  for (const j of sbm.joints) {
    base.set(j, {
      stiffness: j.settings.stiffness,
      gravityPower: j.settings.gravityPower,
      gravityDir: j.settings.gravityDir.clone(),
      dragForce: j.settings.dragForce,
    });
  }
  const h = v.humanoid;
  swayBones = h ? ['hips', 'spine', 'chest', 'neck'].map((n) => h.getNormalizedBoneNode(n)) : [];
  return base.size;
}

export function detach() {
  vrm = null;
  base = new Map();
  swayBones = [];
}

// call after the pose changes abruptly (model loaded, arms relaxed, animation stopped)
export function settle() {
  const sbm = vrm && vrm.springBoneManager;
  if (!sbm) return;
  sbm.setInitState();
  sbm.reset();
}

export function set(o) {
  opts = Object.assign(opts, o || {});
  if (!opts.enabled && vrm && vrm.springBoneManager) vrm.springBoneManager.reset();   // back to rest
}

export function count() {
  return base.size;
}

// a few joints' current rotations (for checking that the physics runs)
export function sample(n = 3) {
  const out = [];
  for (const j of base.keys()) {
    if (out.length >= n) break;
    const q = j.bone.quaternion;
    out.push([q.x, q.y, q.z, q.w].map((v) => Math.round(v * 1000) / 1000));
  }
  return out;
}

// after vrm.update(): with physics off the bones stay in their rest pose
export function afterUpdate() {
  if (vrm && vrm.springBoneManager && !opts.enabled) vrm.springBoneManager.reset();
}

// before vrm.update(): tune every joint for wind, wetness and stiffness
export function beforeUpdate(dt, animating) {
  time += dt;
  if (!vrm || !base.size) return;
  const gust = opts.wind > 0
    ? opts.wind * (0.55 + 0.3 * Math.sin(time * 1.3) + 0.15 * Math.sin(time * 3.7 + 1.1) + 0.1 * Math.sin(time * 7.9))
    : 0;
  for (const [j, b] of base) {
    const s = j.settings;
    if (!opts.enabled) continue;
    s.stiffness = b.stiffness * opts.stiffness;
    // wet hair / fabric is heavier: more gravity, more drag
    s.dragForce = Math.min(1, b.dragForce * (1 + 0.6 * opts.wet));
    tmp.copy(b.gravityDir).multiplyScalar(b.gravityPower * (1 + 0.8 * opts.wet));
    if (gust) tmp.addScaledVector(windDir, gust * 0.3);
    s.gravityPower = tmp.length();
    if (s.gravityPower > 1e-5) s.gravityDir.copy(tmp).normalize();
  }
  // a gentle breathing / weight-shift sway when no animation is moving the body
  if (!animating && opts.enabled && swayBones.length) {
    const [hips, spine, chest, neck] = swayBones;
    if (hips) { hips.rotation.y = 0.05 * Math.sin(time * 0.6); hips.rotation.z = 0.015 * Math.sin(time * 0.45); }
    if (spine) spine.rotation.x = 0.012 * Math.sin(time * 1.6);
    if (chest) chest.rotation.x = 0.01 * Math.sin(time * 1.6 + 0.4);
    if (neck) neck.rotation.y = 0.04 * Math.sin(time * 0.35 + 1);
  }
}
