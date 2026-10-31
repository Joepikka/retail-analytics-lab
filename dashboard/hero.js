// Hero: the 61 days of real revenue drawn as rising particle columns.
// Height is linear in revenue, so the 17 Nov catch-up spike dwarfs normal days, as it did in the data.
import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.min.js";

const canvas = document.getElementById("hero-canvas");
const D = window.DASHBOARD_DATA;
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

function supportsWebGL() {
  try { return !!document.createElement("canvas").getContext("webgl2"); } catch { return false; }
}

if (canvas && D && supportsWebGL()) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);

  const days = D.daily;
  const maxRev = Math.max(...days.map(d => d.revenue));
  const MAX_H = 7.5, SPACING = 0.27, PER_UNIT = 34;  // ~2,500 particles: inside the mobile budget
  const width = (days.length - 1) * SPACING;

  const positions = [], targets = [], colors = [], delays = [];
  const cNormalLow = new THREE.Color("#5b3fd6"), cNormalHigh = new THREE.Color("#9f86ff");
  const cGap = new THREE.Color("#ef6b6b"), cSpike = new THREE.Color("#f0a93a");
  days.forEach((d, i) => {
    const h = Math.max(0.05, (d.revenue / maxRev) * MAX_H);
    const n = Math.max(3, Math.round(h * PER_UNIT));
    const isSpike = d.revenue === maxRev;
    const x = i * SPACING - width / 2;
    for (let k = 0; k < n; k++) {
      const y = (k / n) * h;
      const a = Math.random() * Math.PI * 2, r = Math.random() * 0.075;
      targets.push(x + Math.cos(a) * r, y, Math.sin(a) * r);
      positions.push(x + Math.cos(a) * r, 0, Math.sin(a) * r);
      const c = d.tracking_gap ? (isSpike ? cSpike : cGap) : cNormalLow.clone().lerp(cNormalHigh, y / 1.6);
      colors.push(c.r, c.g, c.b);
      delays.push(i / days.length * 0.9 + (k / n) * 0.25);
    }
  });

  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(reduceMotion ? targets : positions);
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));

  // Soft round sprite so points read as glowing dots, not squares.
  const sprite = (() => {
    const c = document.createElement("canvas"); c.width = c.height = 64;
    const g = c.getContext("2d");
    const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grad.addColorStop(0, "rgba(255,255,255,1)"); grad.addColorStop(0.35, "rgba(255,255,255,.65)"); grad.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = grad; g.fillRect(0, 0, 64, 64);
    return new THREE.CanvasTexture(c);
  })();
  const mat = new THREE.PointsMaterial({ size: 0.15, map: sprite, vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
  const columns = new THREE.Points(geo, mat);
  scene.add(columns);

  // Floor grid and drifting dust for depth.
  const grid = new THREE.GridHelper(26, 52, 0x3a2f7a, 0x1c1740);
  grid.material.transparent = true; grid.material.opacity = 0.55;
  scene.add(grid);
  const DUST = 500, dustPos = new Float32Array(DUST * 3);
  for (let i = 0; i < DUST; i++) {
    dustPos[i * 3] = (Math.random() - 0.5) * 30;
    dustPos[i * 3 + 1] = Math.random() * 12;
    dustPos[i * 3 + 2] = (Math.random() - 0.5) * 20 - 4;
  }
  const dustGeo = new THREE.BufferGeometry();
  dustGeo.setAttribute("position", new THREE.BufferAttribute(dustPos, 3));
  const dust = new THREE.Points(dustGeo, new THREE.PointsMaterial({ size: 0.05, map: sprite, color: 0x8f7cff, transparent: true, opacity: 0.5, depthWrite: false, blending: THREE.AdditiveBlending }));
  scene.add(dust);

  const group = new THREE.Group();
  group.add(columns, grid);
  scene.add(group);

  let wide = false, baseRotY = 0;
  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    const halfFov = THREE.MathUtils.degToRad(camera.fov / 2);
    wide = w >= 1000;
    if (wide) {
      // Wide screens: the row recedes into depth on the right, leaving the left for the headline.
      camera.position.set(0, 4.6, 17);
      camera.lookAt(0, 3.2, 0);
      group.position.set(7.2, 0, -5);
    } else {
      // Narrow screens: face-on, pulled back until all 61 columns fit the width.
      const dist = Math.max(11, (width + 2.5) / 2 / (Math.tan(halfFov) * camera.aspect));
      camera.position.set(0, dist * 0.32, dist);
      camera.lookAt(0, MAX_H * 0.42, 0);
      group.position.set(0, 0, 0);
    }
    camera.updateProjectionMatrix();
    baseRotY = wide ? 1.0 : 0;
    group.rotation.y = baseRotY;
  }
  resize();
  addEventListener("resize", resize);

  let pointerX = 0, pointerY = 0;
  addEventListener("pointermove", e => {
    pointerX = e.clientX / innerWidth - 0.5;
    pointerY = e.clientY / innerHeight - 0.5;
  }, { passive: true });

  const ease = t => 1 - Math.pow(1 - Math.min(Math.max(t, 0), 1), 3);
  const INTRO = 2.6;  // seconds for columns to rise
  const clock = new THREE.Clock();
  let visible = true, raf = 0;

  function frame() {
    const t = clock.getElapsedTime();
    if (t < INTRO + 1.2) {
      for (let i = 0, p = 0; p < pos.length; i++, p += 3) {
        pos[p + 1] = targets[p + 1] * ease((t / INTRO - delays[i] * 0.55) * 1.8);
      }
      geo.attributes.position.needsUpdate = true;
    }
    group.rotation.y += ((baseRotY + pointerX * 0.3 + Math.sin(t * 0.15) * 0.1) - group.rotation.y) * 0.04;
    group.rotation.x += ((pointerY * 0.08) - group.rotation.x) * 0.04;
    dust.rotation.y = t * 0.01;
    renderer.render(scene, camera);
    raf = visible && !document.hidden ? requestAnimationFrame(frame) : 0;
  }

  if (reduceMotion) {
    renderer.render(scene, camera);  // one static frame, final state
    addEventListener("resize", () => renderer.render(scene, camera));
  } else {
    // Pause the loop when the hero is off screen or the tab is hidden.
    new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible && !raf) raf = requestAnimationFrame(frame);
    }).observe(canvas);
    document.addEventListener("visibilitychange", () => { if (!document.hidden && visible && !raf) raf = requestAnimationFrame(frame); });
    raf = requestAnimationFrame(frame);
  }
}
