// Spring-bone physics for the VRM preview: hair, skirts, ribbons and other parts that the model
// marks as spring bones swing with movement, sag a little more when wet and blow in the wind.
// three-vrm simulates the bones in vrm.update(); this module tunes their settings every frame and
// adds a gentle idle sway so the physics is visible even when no animation is playing.
import * as THREE from 'three';

let vrm = null;
let base = new Map();     // joint -> its original settings
let opts = { enabled: true, stiffness: 1, wind: 0.5, gusty: false, wet: 0 };
let time = 0;
let swayBones = [];
const tmp = new THREE.Vector3();
const windVec = new THREE.Vector3();
// parts that wind should barely move (soft-body physics on the chest)
const LITTLE_WIND = /bust|breast|oppai/i;

// wind is a living thing: gusts rise and fall (with lulls), and the direction wanders. In windy
// weather the direction can also swing round at any moment. It never settles into a steady push.
const gust = { now: 0, target: 0.5, until: 0 };
const heading = { now: 0.6, target: 0.6, until: 0, speed: 0.6 };

function updateWind(dt) {
  if (time >= gust.until) {
    // a new gust (or lull) every 0.4 - 2.5 s; about one in four is a near-calm lull
    const lull = Math.random() < 0.25;
    gust.target = lull ? Math.random() * 0.15 : 0.35 + Math.random() * (opts.gusty ? 1.0 : 0.75);
    gust.until = time + 0.4 + Math.random() * (opts.gusty ? 1.6 : 2.1);
  }
  gust.now += (gust.target - gust.now) * Math.min(1, dt * (gust.target > gust.now ? 3.0 : 1.4));
  if (time >= heading.until) {
    if (opts.gusty && Math.random() < 0.45) {
      // windy: the wind can come from anywhere, quickly
      heading.target = Math.random() * Math.PI * 2;
      heading.speed = 1.5 + Math.random() * 2.5;
    } else {
      // otherwise it drifts around its general direction
      heading.target = heading.now + (Math.random() - 0.5) * (opts.gusty ? 1.6 : 0.9);
      heading.speed = 0.3 + Math.random() * 0.5;
    }
    heading.until = time + 1 + Math.random() * (opts.gusty ? 2.5 : 5);
  }
  let d = heading.target - heading.now;
  d = Math.atan2(Math.sin(d), Math.cos(d));
  heading.now += d * Math.min(1, dt * heading.speed);
  // a little flutter on top so even a steady gust keeps moving
  const flutter = 1 + 0.25 * Math.sin(time * 6.3) * Math.sin(time * 2.9 + 1.3) + 0.12 * Math.sin(time * 13.7);
  const a = heading.now + 0.25 * Math.sin(time * 1.7) * Math.sin(time * 0.43);
  const strength = opts.wind * gust.now * flutter;
  windVec.set(Math.sin(a), 0.08 * Math.sin(time * 2.3), -Math.cos(a)).multiplyScalar(strength);
}

export function attach(v) {
  vrm = v;
  base = new Map();
  const sbm = v && v.springBoneManager;
  if (!sbm) return 0;
  for (const j of sbm.joints) {
    const name = (j.bone && j.bone.name) || '';
    base.set(j, {
      windScale: LITTLE_WIND.test(name) ? 0.12 : 1,
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
  updateWind(dt);
  for (const [j, b] of base) {
    const s = j.settings;
    if (!opts.enabled) continue;
    s.stiffness = b.stiffness * opts.stiffness;
    // wet hair / fabric is heavier: more gravity, more drag
    s.dragForce = Math.min(1, b.dragForce * (1 + 0.6 * opts.wet));
    tmp.copy(b.gravityDir).multiplyScalar(b.gravityPower * (1 + 0.8 * opts.wet));
    if (opts.wind > 0) tmp.addScaledVector(windVec, 0.3 * b.windScale);
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
