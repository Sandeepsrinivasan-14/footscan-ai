/* FootScan AI web app: hash router, theme, server status, API-key dialog, lazy 3D hero.
   Plain ES modules, no build step. Everything is same-origin so a strict CSP applies. */

import { api, getApiKey, setApiKey } from "./api.js";
import { $, $$, toast } from "./dom.js";
import { store } from "./store.js";
import { createAnalyzeView } from "./views/analyze.js";
import { createCompareView } from "./views/compare.js";
import { createPatientsView } from "./views/patients.js";

/* ------------------------------------------------------------------- theme */

const THEME_KEY = "footscan.theme";
const root = document.documentElement;
const themeBtn = $("#themeBtn");

function storedTheme() {
  try {
    return localStorage.getItem(THEME_KEY);
  } catch {
    return null;
  }
}

function applyTheme(theme, persist = false) {
  root.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "light" ? "#eaf0fa" : "#070b16");
  const light = theme === "light";
  themeBtn.setAttribute("aria-pressed", String(light));
  themeBtn.setAttribute("aria-label", light ? "Switch to dark theme" : "Switch to light theme");
  if (persist) {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* ignore: theme just will not persist */
    }
  }
}

const prefersLight = window.matchMedia("(prefers-color-scheme: light)");
applyTheme(storedTheme() || (prefersLight.matches ? "light" : "dark"));
prefersLight.addEventListener?.("change", (e) => {
  if (!storedTheme()) applyTheme(e.matches ? "light" : "dark");
});
themeBtn.addEventListener("click", () => applyTheme(root.dataset.theme === "light" ? "dark" : "light", true));

/* ---------------------------------------------------------------- 3D hero */

let sceneController = null;
const setSceneMode = (mode) => sceneController?.setMode(mode);

async function initScene() {
  const container = $("#heroScene");
  const canvas = $("#heroCanvas");
  if (!container || !canvas || sceneController) return;
  const { mountScene } = await import("./scene.js");
  sceneController = await mountScene(container, canvas);
}

function lazyScene() {
  const container = $("#heroScene");
  if (!container) return;
  const start = () => (window.requestIdleCallback ? requestIdleCallback(initScene, { timeout: 2500 }) : setTimeout(initScene, 600));
  if (!("IntersectionObserver" in window)) return start();
  const io = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) {
      io.disconnect();
      start();
    }
  });
  io.observe(container);
}

/* ------------------------------------------------------------------ router */

const views = {
  analyze: createAnalyzeView({ setSceneMode }),
  compare: createCompareView({ setSceneMode }),
  patients: createPatientsView({ navigate: (name) => (location.hash = `#/${name}`) }),
};
for (const [name, view] of Object.entries(views)) $(`#view-${name}`).append(view.el);

const mounted = new Set();
function route() {
  const name = (location.hash.match(/^#\/(\w+)/) || [])[1];
  const current = name in views ? name : "analyze";
  for (const section of $$(".view")) section.hidden = section.dataset.view !== current;
  for (const link of $$(".nav__link")) {
    if (link.dataset.route === current) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  document.title = `${views[current].title} · FootScan AI (research use only)`;
  views[current].onShow?.();
  if (mounted.size) $("#main").focus({ preventScroll: true }); // keep keyboard/screen-reader context after navigation
  mounted.add(current);
  if (current !== "analyze") setSceneMode("idle");
  window.scrollTo({ top: 0 });
}
window.addEventListener("hashchange", route);
route();
lazyScene();

/* ----------------------------------------------------------------- status */

const pill = $("#statusPill");
const pillText = $("#statusText");

async function checkHealth() {
  let state = "down";
  let text = "Server offline";
  try {
    const health = await api.health();
    if (health.model_loaded) {
      state = "ok";
      text = `Model ready · ${health.device}`;
    } else {
      state = "degraded";
      text = "Model not loaded";
    }
  } catch {
    /* keep the offline defaults */
  }
  pill.dataset.state = state;
  pillText.textContent = text;
  pill.title = text;
}
checkHealth();
setInterval(() => !document.hidden && checkHealth(), 30_000);

/* ---------------------------------------------------------------- API key */

const keyDialog = $("#keyDialog");
const keyInput = $("#keyInput");
const keyBtn = $("#keyBtn");

function syncKeyButton() {
  keyBtn.dataset.active = String(!!getApiKey());
  keyBtn.setAttribute("aria-label", getApiKey() ? "API key set. Change API key" : "Set API key");
}

function openKeyDialog() {
  keyInput.value = "";
  if (typeof keyDialog.showModal === "function") keyDialog.showModal();
  keyInput.focus();
}

keyBtn.addEventListener("click", openKeyDialog);
$("#keyForm").addEventListener("submit", (e) => {
  const action = e.submitter?.value;
  if (action === "save" && keyInput.value.trim()) {
    setApiKey(keyInput.value.trim());
    toast("success", "API key saved for this tab");
    store.refreshPatients().catch(() => {});
  } else if (action === "clear") {
    setApiKey("");
    toast("info", "API key removed");
  }
  syncKeyButton();
});
window.addEventListener("footscan:auth-required", () => {
  if (!keyDialog.open) {
    toast("error", "API key required", "This server needs an API key. Enter it to continue.", 7000);
    openKeyDialog();
  }
});
syncKeyButton();
