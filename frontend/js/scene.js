/* Lazy-loaded three.js "scanner" hero element.

   - three.js (r159, vendored under /vendor, MIT) is only fetched when the hero scrolls into view,
     after the page is interactive, and never when WebGL is unavailable or Save-Data is on.
   - The script is loaded through a <script> tag with a Subresource Integrity hash, so a changed or
     tampered file is refused by the browser. tests/test_frontend_assets.py keeps the hash honest.
   - prefers-reduced-motion: renders a single static frame (no animation loop, no pointer parallax).
   - The loop pauses when the canvas is off-screen or the tab is hidden. */

import { reduceMotion } from "./dom.js";

const THREE_SRC = "vendor/three.min.js";
const THREE_INTEGRITY = "sha384-Lwojr+0fOVR25P8bdL6E0T2dv0q0ZT4Yy2Ia1dGOz6b5jLSzWZkdqlw0cKTQYKzT";

let threePromise = null;

function loadThree() {
  if (window.THREE) return Promise.resolve(window.THREE);
  if (threePromise) return threePromise;
  threePromise = new Promise((resolve, reject) => {
    // r159's classic build logs a one-line deprecation notice on load; silence just that line.
    const warn = console.warn;
    console.warn = (...args) => {
      if (typeof args[0] === "string" && args[0].includes("build/three.min.js")) return;
      warn.apply(console, args);
    };
    const restore = () => {
      console.warn = warn;
    };
    const script = document.createElement("script");
    script.src = THREE_SRC;
    script.integrity = THREE_INTEGRITY;
    script.crossOrigin = "anonymous";
    script.async = true;
    script.onload = () => {
      restore();
      window.THREE ? resolve(window.THREE) : reject(new Error("three.js did not initialise"));
    };
    script.onerror = () => {
      restore();
      reject(new Error("three.js failed to load or failed its integrity check"));
    };
    document.head.append(script);
  });
  return threePromise;
}

function webglAvailable() {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
  } catch {
    return false;
  }
}

const PALETTES = {
  dark: { primary: 0x5eead4, secondary: 0x818cf8, tertiary: 0x60a5fa, blending: "additive" },
  light: { primary: 0x0d9488, secondary: 0x4f46e5, tertiary: 0x2563eb, blending: "normal" },
};

/**
 * Mounts the scene into `container` (which must already contain a <canvas>).
 * Resolves to a controller, or null when 3D is unavailable (callers keep their CSS fallback).
 */
export async function mountScene(container, canvas) {
  const saveData = navigator.connection && navigator.connection.saveData;
  if (!webglAvailable() || saveData) return null;

  let THREE;
  try {
    THREE = await loadThree();
  } catch (err) {
    console.info("3D hero disabled:", err.message);
    return null;
  }

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "low-power" });
  renderer.setClearColor(0x000000, 0);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 50);
  camera.position.set(0, 0.15, 6.2);

  const rig = new THREE.Group();
  scene.add(rig);

  const theme = () => (document.documentElement.dataset.theme === "light" ? "light" : "dark");
  const mats = [];
  const track = (m) => (mats.push(m), m);

  // 1. Wireframe lattice: the "mesh" being scanned.
  const lattice = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1.55, 3),
    track(new THREE.MeshBasicMaterial({ wireframe: true, transparent: true, opacity: 0.22 })),
  );
  rig.add(lattice);

  // 2. Point cloud on a slightly larger noisy shell.
  const count = 1400;
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    const u = Math.random() * 2 - 1;
    const phi = Math.random() * Math.PI * 2;
    const r = 1.62 + (Math.random() - 0.5) * 0.18;
    const s = Math.sqrt(1 - u * u);
    positions.set([r * s * Math.cos(phi), r * u, r * s * Math.sin(phi)], i * 3);
  }
  const pointsGeo = new THREE.BufferGeometry();
  pointsGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  const points = new THREE.Points(pointsGeo, track(new THREE.PointsMaterial({ size: 0.035, transparent: true, opacity: 0.9, depthWrite: false })));
  rig.add(points);

  // 3. Orbital rings.
  const ringA = new THREE.Mesh(new THREE.TorusGeometry(2.15, 0.012, 8, 160), track(new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.75 })));
  const ringB = new THREE.Mesh(new THREE.TorusGeometry(2.45, 0.008, 8, 160), track(new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.5 })));
  ringA.rotation.x = Math.PI / 2.4;
  ringB.rotation.set(Math.PI / 3.2, Math.PI / 5, 0);
  rig.add(ringA, ringB);

  // 4. Scan plane that sweeps through the lattice.
  const scanRing = new THREE.Mesh(new THREE.TorusGeometry(1.7, 0.02, 8, 120), track(new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.95 })));
  scanRing.rotation.x = Math.PI / 2;
  rig.add(scanRing);

  // 5. Soft core glow.
  const core = new THREE.Mesh(new THREE.SphereGeometry(0.34, 24, 24), track(new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.85 })));
  rig.add(core);

  function applyTheme() {
    const p = PALETTES[theme()];
    const blending = p.blending === "additive" ? THREE.AdditiveBlending : THREE.NormalBlending;
    lattice.material.color.setHex(p.tertiary);
    points.material.color.setHex(p.primary);
    ringA.material.color.setHex(p.primary);
    ringB.material.color.setHex(p.secondary);
    scanRing.material.color.setHex(p.primary);
    core.material.color.setHex(p.secondary);
    for (const m of [points.material, ringA.material, ringB.material, scanRing.material, core.material]) {
      m.blending = blending;
      m.needsUpdate = true;
    }
  }
  applyTheme();

  const state = { mode: "idle", energy: 0, target: 0, px: 0, py: 0 };
  const clock = new THREE.Clock();
  let running = false;
  let raf = 0;
  let visible = true;
  const still = reduceMotion();

  function resize() {
    const { clientWidth: w, clientHeight: hgt } = container;
    if (!w || !hgt) return;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(w, hgt, false);
    camera.aspect = w / hgt;
    camera.position.z = w / hgt < 0.9 ? 7.6 : 6.2;
    camera.updateProjectionMatrix();
  }

  function frame() {
    const dt = Math.min(clock.getDelta(), 0.05);
    const t = clock.elapsedTime;
    state.energy += (state.target - state.energy) * Math.min(dt * 3, 1);
    const speed = 1 + state.energy * 3.2;

    rig.rotation.y += dt * 0.18 * speed;
    rig.rotation.x += (state.py * 0.35 - rig.rotation.x) * Math.min(dt * 2.5, 1);
    rig.position.x += (state.px * 0.25 - rig.position.x) * Math.min(dt * 2.5, 1);
    lattice.rotation.y -= dt * 0.1 * speed;
    points.rotation.y += dt * 0.05 * speed;
    ringA.rotation.z += dt * 0.35 * speed;
    ringB.rotation.z -= dt * 0.25 * speed;
    ringB.rotation.x += dt * 0.05 * speed;

    const sweep = Math.sin(t * (0.9 + state.energy * 2.2));
    scanRing.position.y = sweep * 1.45;
    const radius = Math.sqrt(Math.max(0.05, 1 - (sweep * 1.45) ** 2 / 1.7 ** 2)) * 1.7;
    scanRing.scale.setScalar(radius / 1.7);

    const pulse = 1 + Math.sin(t * 2.2) * 0.08 + state.energy * 0.35;
    core.scale.setScalar(pulse);
    lattice.material.opacity = 0.2 + state.energy * 0.2;

    renderer.render(scene, camera);
    raf = running ? requestAnimationFrame(frame) : 0;
  }

  function start() {
    if (still || running || !visible || document.hidden) return;
    running = true;
    clock.getDelta();
    raf = requestAnimationFrame(frame);
  }
  function stop() {
    running = false;
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
  }
  function renderOnce() {
    rig.rotation.set(0.35, 0.7, 0);
    scanRing.position.y = 0.4;
    scanRing.scale.setScalar(0.96);
    renderer.render(scene, camera);
  }

  const ro = new ResizeObserver(() => {
    resize();
    if (still || !running) renderOnce();
  });
  ro.observe(container);
  resize();

  const io = new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    visible ? start() : stop();
  });
  io.observe(container);

  const onVisibility = () => (document.hidden ? stop() : start());
  document.addEventListener("visibilitychange", onVisibility);

  const onPointer = (e) => {
    const r = container.getBoundingClientRect();
    state.px = ((e.clientX - r.left) / r.width - 0.5) * 2;
    state.py = ((e.clientY - r.top) / r.height - 0.5) * 2;
  };
  if (!still) container.addEventListener("pointermove", onPointer);

  const themeObserver = new MutationObserver(() => {
    applyTheme();
    if (!running) renderOnce();
  });
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  const onContextLost = (e) => {
    e.preventDefault();
    stop();
    container.classList.remove("is-3d");
  };
  canvas.addEventListener("webglcontextlost", onContextLost);

  if (still) renderOnce();
  else start();
  container.classList.add("is-3d");

  return {
    /** idle | busy: the scene speeds up while an analysis is running. */
    setMode(mode) {
      state.mode = mode;
      state.target = mode === "busy" ? 1 : 0;
    },
    dispose() {
      stop();
      ro.disconnect();
      io.disconnect();
      themeObserver.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      container.removeEventListener("pointermove", onPointer);
      canvas.removeEventListener("webglcontextlost", onContextLost);
      for (const m of mats) m.dispose();
      for (const o of [lattice, points, ringA, ringB, scanRing, core]) o.geometry.dispose();
      renderer.dispose();
    },
  };
}
