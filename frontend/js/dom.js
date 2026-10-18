/* Small DOM + formatting helpers. Elements are always built with textContent/attributes,
   never innerHTML, so API-provided strings (patient names, treatment text) cannot inject markup. */

const SVG_NS = "http://www.w3.org/2000/svg";

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** h("div", {class: "x", onclick: fn, "aria-label": "y"}, "text", childNode, ...) */
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (key === "dataset") Object.assign(el.dataset, value);
    else el.setAttribute(key, value === true ? "" : String(value));
  }
  append(el, children);
  return el;
}

export function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === undefined || child === null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function clear(el) {
  el.replaceChildren();
  return el;
}

export function icon(name, size = 18, cls = "") {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(size));
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  if (cls) svg.setAttribute("class", cls);
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

export function svgEl(tag, attrs = {}, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  for (const c of children) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
}

let uid = 0;
export const nextId = (prefix = "id") => `${prefix}-${++uid}`;

/* ------------------------------------------------------------------ formatting */

export function fmtNum(value, digits = 2) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : "–";
}

export function fmtBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function fmtDate(iso, opts = { dateStyle: "medium", timeStyle: "short" }) {
  // The API returns naive UTC timestamps (no zone suffix); treat them as UTC.
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  return Number.isNaN(d.getTime()) ? iso : new Intl.DateTimeFormat(undefined, opts).format(d);
}

/** Animate a number inside `el` (instant when the user prefers reduced motion). */
export function countUp(el, to, { digits = 2, duration = 900, suffix = "" } = {}) {
  const target = Number(to);
  if (!Number.isFinite(target) || reduceMotion()) {
    el.textContent = `${fmtNum(target, digits)}${suffix}`;
    return;
  }
  const start = performance.now();
  const tick = (now) => {
    const t = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - t, 4);
    el.textContent = `${fmtNum(target * eased, digits)}${suffix}`;
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/* ---------------------------------------------------------------------- badges */

const SEVERITY = {
  Mild: { cls: "badge--ok", icon: "check", label: "Mild" },
  Moderate: { cls: "badge--warn", icon: "alert", label: "Moderate" },
  Severe: { cls: "badge--danger", icon: "warn", label: "Severe" },
};

export function severityBadge(severity) {
  const meta = SEVERITY[severity] || { cls: "badge--info", icon: "info", label: severity || "Unknown" };
  return h("span", { class: `badge ${meta.cls}` }, icon(meta.icon, 14), `${meta.label} severity`);
}

export function statusBadge(status) {
  const map = {
    "ULCER DETECTED": { cls: "badge--danger", icon: "alert", label: "Ulcer detected" },
    HEALTHY: { cls: "badge--ok", icon: "check", label: "No ulcer detected" },
    IMPROVED: { cls: "badge--ok", icon: "down", label: "Improved" },
    STABLE: { cls: "badge--info", icon: "flat", label: "Stable" },
    WORSENED: { cls: "badge--danger", icon: "up", label: "Worsened" },
  };
  const meta = map[status] || { cls: "badge--info", icon: "info", label: status };
  return h("span", { class: `badge ${meta.cls}` }, icon(meta.icon, 14), meta.label);
}

/* ---------------------------------------------------------------------- toasts */

const TOAST_ICON = { success: "check", error: "alert", info: "info" };

export function toast(type, title, message = "", timeout = 5200) {
  const host = document.getElementById("toasts");
  if (!host) return;
  const remove = () => {
    el.classList.add("is-leaving");
    setTimeout(() => el.remove(), 240);
  };
  const el = h(
    "div",
    { class: `toast toast--${type}`, role: type === "error" ? "alert" : "status" },
    h("span", { class: "toast__icon" }, icon(TOAST_ICON[type] || "info", 18)),
    h("div", { class: "toast__body" }, h("strong", { text: title }), message ? h("p", { text: message }) : null),
    h("button", { class: "toast__close", type: "button", "aria-label": "Dismiss", onclick: remove }, icon("x", 14)),
  );
  host.append(el);
  if (timeout) setTimeout(remove, timeout);
}
