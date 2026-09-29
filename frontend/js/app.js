"use strict";

/* =========================================================================
   FootScan AI — frontend application logic
   Vanilla JS, no build step. Talks to the FastAPI REST API under /api and
   /health. Renders results from footscan.api.schemas.AnalysisResponse /
   CompareResponse, which carry base64 JPEG data URIs for every pipeline
   visualization.
   ========================================================================= */

const API_BASE = "";
const API_KEY = document.querySelector('meta[name="footscan-api-key"]')?.content?.trim() || "";
const REDUCE_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const state = {
  view: "analyze",
  analyzeFile: null,
  compareOldFile: null,
  compareNewFile: null,
  trackFile: null,
  lastScanId: null,
  patients: [],
  selectedPatientId: null,
  healingChart: null,
};

// -------------------------------------------------------------------------
// Small DOM helpers
// -------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);
const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function setHidden(el, hidden) {
  if (hidden) el.setAttribute("hidden", "");
  else el.removeAttribute("hidden");
}

function fmtNum(n, digits = 2) {
  const v = Number(n);
  return Number.isFinite(v) ? v.toFixed(digits) : "—";
}

function severityBadgeClass(severity) {
  switch (severity) {
    case "Mild": return "badge--mild";
    case "Moderate": return "badge--moderate";
    case "Severe": return "badge--severe";
    default: return "";
  }
}

// -------------------------------------------------------------------------
// API client
// -------------------------------------------------------------------------
async function apiRequest(path, options = {}) {
  if (API_KEY && path.startsWith("/api/")) {
    options.headers = { ...(options.headers || {}), "X-API-Key": API_KEY };
  }
  const resp = await fetch(API_BASE + path, options);
  const contentType = resp.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  const body = isJson ? await resp.json().catch(() => null) : null;

  if (!resp.ok) {
    const detail = body && body.detail ? body.detail : `Request failed (${resp.status})`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body ?? resp;
}

const api = {
  health: () => apiRequest("/health"),

  analyze: (formData) =>
    apiRequest("/api/analyze", { method: "POST", body: formData }),

  compare: (formData) =>
    apiRequest("/api/compare", { method: "POST", body: formData }),

  listPatients: () => apiRequest("/api/patients"),

  createPatient: (name) =>
    apiRequest("/api/patients", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),

  getPatientScans: (patientId) => apiRequest(`/api/patients/${patientId}/scans`),

  scanImageUrl: (scanId, kind) => `/api/scans/${scanId}/image/${kind}`,

  reportUrl: (scanId, patientName) => {
    const q = patientName ? `?patient_name=${encodeURIComponent(patientName)}` : "";
    return `/api/scans/${scanId}/report${q}`;
  },
};

// -------------------------------------------------------------------------
// Toasts
// -------------------------------------------------------------------------
const ICONS = { success: "icon-check", error: "icon-alert", info: "icon-activity" };

function showToast(type, title, message, timeout = 4400) {
  const stack = $("toastStack");
  const el = document.createElement("div");
  el.className = `toast toast--${type}`;
  el.innerHTML = `
    <span class="toast__icon"><svg width="13" height="13"><use href="#${ICONS[type] || ICONS.info}"/></svg></span>
    <div class="toast__body">
      <div class="toast__title">${escapeHtml(title)}</div>
      ${message ? `<div class="toast__msg">${escapeHtml(message)}</div>` : ""}
    </div>`;
  stack.appendChild(el);
  const remove = () => {
    el.classList.add("is-leaving");
    setTimeout(() => el.remove(), 220);
  };
  setTimeout(remove, timeout);
  el.addEventListener("click", remove);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = String(str);
  return div.innerHTML;
}

// -------------------------------------------------------------------------
// Loading overlay
// -------------------------------------------------------------------------
function setLoading(isLoading, text = "Running inference…") {
  $("loadingText").textContent = text;
  setHidden($("loadingOverlay"), !isLoading);
}

// -------------------------------------------------------------------------
// 3D tilt for glass cards
// -------------------------------------------------------------------------
function attachTilt(el) {
  if (REDUCE_MOTION || el.dataset.tiltBound) return;
  el.dataset.tiltBound = "1";
  const maxDeg = 7;
  el.addEventListener("pointermove", (e) => {
    if (e.pointerType === "touch") return;
    const rect = el.getBoundingClientRect();
    const px = (e.clientX - rect.left) / rect.width;
    const py = (e.clientY - rect.top) / rect.height;
    const rx = (0.5 - py) * maxDeg * 2;
    const ry = (px - 0.5) * maxDeg * 2;
    el.style.transform = `rotateX(${rx.toFixed(2)}deg) rotateY(${ry.toFixed(2)}deg) translateZ(4px)`;
  });
  el.addEventListener("pointerleave", () => {
    el.style.transform = "";
  });
}

function initTilt(root = document) {
  qsa("[data-tilt]", root).forEach(attachTilt);
}

// -------------------------------------------------------------------------
// Tabs / views
// -------------------------------------------------------------------------
function switchView(view) {
  state.view = view;
  qsa(".tabs__btn").forEach((btn) => {
    const active = btn.dataset.view === view;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-selected", String(active));
  });
  qsa(".view").forEach((section) => {
    section.classList.toggle("is-active", section.dataset.view === view);
  });
}

qsa(".tabs__btn").forEach((btn) =>
  btn.addEventListener("click", () => {
    switchView(btn.dataset.view);
    history.replaceState(null, "", `#${btn.dataset.view}`);
  })
);

const validViews = qsa(".tabs__btn").map((btn) => btn.dataset.view);
const initialView = validViews.includes(location.hash.slice(1)) ? location.hash.slice(1) : "analyze";
switchView(initialView);

// -------------------------------------------------------------------------
// Health check polling
// -------------------------------------------------------------------------
async function pollHealth() {
  const dot = $("statusDot");
  const label = $("statusLabel");
  try {
    const health = await api.health();
    const ok = health.status === "ok" && health.model_loaded;
    dot.className = `status-dot ${ok ? "is-ok" : "is-bad"}`;
    label.textContent = ok ? `Model online · ${health.device}` : "Model unavailable";
  } catch {
    dot.className = "status-dot is-bad";
    label.textContent = "Backend unreachable";
  }
}

// -------------------------------------------------------------------------
// Generic dropzone wiring
// -------------------------------------------------------------------------
function setupDropzone({ zone, input, empty, preview, img, clearBtn, onChange }) {
  const openPicker = () => input.click();

  zone.addEventListener("click", (e) => {
    if (e.target.closest(".chip-btn")) return;
    openPicker();
  });
  zone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openPicker();
    }
  });

  ["dragenter", "dragover"].forEach((evt) =>
    zone.addEventListener(evt, (e) => {
      e.preventDefault();
      zone.classList.add("is-dragover");
    })
  );
  ["dragleave", "dragend", "drop"].forEach((evt) =>
    zone.addEventListener(evt, (e) => {
      e.preventDefault();
      zone.classList.remove("is-dragover");
    })
  );
  zone.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (file) setFile(file);
  });

  input.addEventListener("change", () => {
    const file = input.files && input.files[0];
    if (file) setFile(file);
  });

  clearBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    input.value = "";
    setHidden(empty, false);
    setHidden(preview, true);
    revokeCurrent();
    img.src = "";
    onChange(null);
  });

  function revokeCurrent() {
    if (img.dataset.objectUrl) {
      URL.revokeObjectURL(img.dataset.objectUrl);
      delete img.dataset.objectUrl;
    }
  }

  function setFile(file) {
    if (!file.type.startsWith("image/")) {
      showToast("error", "Unsupported file", "Please choose a JPG, PNG, WEBP or BMP image.");
      return;
    }
    revokeCurrent();
    const url = URL.createObjectURL(file);
    img.dataset.objectUrl = url;
    img.src = url;
    setHidden(empty, true);
    setHidden(preview, false);
    onChange(file);
  }
}

// -------------------------------------------------------------------------
// Analyze view
// -------------------------------------------------------------------------
setupDropzone({
  zone: $("dropzone"),
  input: $("fileInput"),
  empty: $("dropzoneEmpty"),
  preview: $("dropzonePreview"),
  img: $("previewImg"),
  clearBtn: $("clearImage"),
  onChange: (file) => (state.analyzeFile = file),
});

let viewType = "Plantar (Bottom)";
qsa("#viewTypeSeg .segmented__btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    qsa("#viewTypeSeg .segmented__btn").forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    viewType = btn.dataset.value;
  });
});

$("threshold").addEventListener("input", (e) => {
  $("thresholdOut").textContent = Number(e.target.value).toFixed(2);
});

const VIZ_FIELDS = [
  { key: "original", label: "Original" },
  { key: "mask", label: "Binary Mask" },
  { key: "heatmap", label: "Heatmap" },
  { key: "blended", label: "Blended Overlay" },
  { key: "edges", label: "Edge Detection" },
  { key: "cropped", label: "Auto-Zoom ROI" },
];

function renderVizGrid(images) {
  const grid = $("vizGrid");
  grid.innerHTML = "";
  VIZ_FIELDS.forEach(({ key, label }) => {
    const fig = document.createElement("figure");
    fig.className = "viz-card glass";
    fig.setAttribute("data-tilt", "");
    fig.innerHTML = `
      <div class="viz-card__frame"><img src="${images[key]}" alt="${label}" loading="lazy" /></div>
      <figcaption>${label}</figcaption>`;
    fig.addEventListener("click", () => openLightbox(images[key], label));
    grid.appendChild(fig);
    attachTilt(fig);
  });
}

async function runAnalysis() {
  if (!state.analyzeFile) {
    showToast("error", "No image selected", "Upload a foot scan image first.");
    return;
  }

  const fd = new FormData();
  fd.append("image", state.analyzeFile);
  fd.append("ref_cm", $("refCm").value || "1.0");
  fd.append("ref_px", $("refPx").value || "38.46");
  fd.append("threshold", $("threshold").value);
  fd.append("prep_method", $("prepMethod").value);
  fd.append("view_type", viewType);
  fd.append("save", "true");

  const btn = $("analyzeBtn");
  btn.classList.add("is-loading");
  btn.disabled = true;
  setLoading(true, "Segmenting wound boundaries…");

  try {
    const result = await api.analyze(fd);
    state.lastScanId = result.scan_id;
    renderAnalysisResult(result);
    $("exportBtn").disabled = !result.scan_id;
    showToast("success", "Analysis complete", `Status: ${result.status}`);
  } catch (err) {
    showToast("error", "Analysis failed", err.message);
  } finally {
    btn.classList.remove("is-loading");
    btn.disabled = false;
    setLoading(false);
  }
}

function renderAnalysisResult(result) {
  setHidden($("analyzeEmpty"), true);
  setHidden($("analyzeContent"), false);

  const isDanger = result.status === "ULCER DETECTED";
  const banner = $("statusBanner");
  banner.classList.toggle("is-danger", isDanger);
  $("statusValue").textContent = result.status;
  $("statusIcon").innerHTML = `<svg width="26" height="26"><use href="#${isDanger ? "icon-alert" : "icon-check"}"/></svg>`;

  const sevBadge = $("severityBadge");
  sevBadge.textContent = result.severity;
  sevBadge.className = `badge ${severityBadgeClass(result.severity)}`;
  $("sinbadBadge").textContent = `SINBAD ${result.sinbad_score}/6`;

  $("metricArea").textContent = fmtNum(result.area_cm2, 3);
  $("metricShape").textContent = result.shape;
  $("metricColor").textContent = result.color_profile;
  $("metricHealing").textContent = result.est_healing_days;

  $("treatmentText").textContent = result.treatment;

  renderVizGrid(result.images);
}

$("analyzeBtn").addEventListener("click", runAnalysis);

$("exportBtn").addEventListener("click", () => {
  if (!state.lastScanId) return;
  const patientName = $("patientName").value.trim();
  window.open(api.reportUrl(state.lastScanId, patientName || undefined), "_blank");
});

// -------------------------------------------------------------------------
// Compare view
// -------------------------------------------------------------------------
setupDropzone({
  zone: $("dropzoneOld"),
  input: $("fileOld"),
  empty: $("dropzoneOldEmpty"),
  preview: $("dropzoneOldPreview"),
  img: $("previewOldImg"),
  clearBtn: $("clearOld"),
  onChange: (file) => (state.compareOldFile = file),
});

setupDropzone({
  zone: $("dropzoneNew"),
  input: $("fileNew"),
  empty: $("dropzoneNewEmpty"),
  preview: $("dropzoneNewPreview"),
  img: $("previewNewImg"),
  clearBtn: $("clearNew"),
  onChange: (file) => (state.compareNewFile = file),
});

async function runCompare() {
  if (!state.compareOldFile || !state.compareNewFile) {
    showToast("error", "Missing images", "Upload both an earlier and a later scan.");
    return;
  }

  const fd = new FormData();
  fd.append("old_image", state.compareOldFile);
  fd.append("new_image", state.compareNewFile);
  fd.append("ref_cm", $("refCm").value || "1.0");
  fd.append("ref_px", $("refPx").value || "38.46");
  fd.append("threshold", $("threshold").value);

  const btn = $("compareBtn");
  btn.classList.add("is-loading");
  btn.disabled = true;
  setLoading(true, "Computing healing delta…");

  try {
    const result = await api.compare(fd);
    renderCompareResult(result);
    showToast("success", "Comparison complete", `Trend: ${result.status}`);
  } catch (err) {
    showToast("error", "Comparison failed", err.message);
  } finally {
    btn.classList.remove("is-loading");
    btn.disabled = false;
    setLoading(false);
  }
}

function renderCompareResult(result) {
  setHidden($("compareEmpty"), true);
  setHidden($("compareResults"), false);

  const isWorse = result.status === "WORSENED";
  const isBetter = result.status === "IMPROVED";
  $("compareBanner").classList.toggle("is-danger", isWorse);
  $("compareStatus").textContent = result.status;
  const iconName = isWorse ? "icon-arrow-up" : isBetter ? "icon-arrow-down" : "icon-minus";
  $("compareIcon").innerHTML = `<svg width="26" height="26"><use href="#${iconName}"/></svg>`;

  $("compareOldArea").textContent = fmtNum(result.old_area_cm2, 3);
  $("compareNewArea").textContent = fmtNum(result.new_area_cm2, 3);
  const change = result.change_cm2;
  $("compareChange").textContent = `${change >= 0 ? "+" : ""}${fmtNum(change, 3)} cm²`;

  $("diffImg").src = result.diff_image;
}

$("compareBtn").addEventListener("click", runCompare);

// -------------------------------------------------------------------------
// Patients view
// -------------------------------------------------------------------------
function initials(name) {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("") || "?";
}

async function loadPatients() {
  try {
    state.patients = await api.listPatients();
    renderPatientList();
  } catch (err) {
    showToast("error", "Could not load patients", err.message);
  }
}

function renderPatientList() {
  const list = $("patientList");
  const filter = $("patientSearch").value.trim().toLowerCase();
  const filtered = state.patients.filter((p) => p.name.toLowerCase().includes(filter));

  list.innerHTML = "";
  setHidden($("patientListEmpty"), filtered.length !== 0);

  filtered.forEach((p) => {
    const li = document.createElement("li");
    li.className = `patient-list__item ${p.id === state.selectedPatientId ? "is-active" : ""}`;
    li.innerHTML = `
      <span class="patient-list__avatar">${escapeHtml(initials(p.name))}</span>
      <span>
        <div class="patient-list__name">${escapeHtml(p.name)}</div>
        <div class="patient-list__meta">Tap to view history</div>
      </span>`;
    li.addEventListener("click", () => selectPatient(p.id));
    list.appendChild(li);
  });
}

$("patientSearch").addEventListener("input", renderPatientList);

$("newPatientBtn").addEventListener("click", () => {
  const form = $("newPatientForm");
  const wasHidden = form.hidden;
  setHidden(form, !wasHidden);
  if (wasHidden) $("newPatientName").focus();
});
$("cancelNewPatient").addEventListener("click", () => {
  setHidden($("newPatientForm"), true);
  $("newPatientName").value = "";
});

$("newPatientForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = $("newPatientName").value.trim();
  if (!name) return;
  try {
    const patient = await api.createPatient(name);
    $("newPatientName").value = "";
    setHidden($("newPatientForm"), true);
    await loadPatients();
    selectPatient(patient.id);
    showToast("success", "Patient added", name);
  } catch (err) {
    showToast("error", "Could not add patient", err.message);
  }
});

async function selectPatient(patientId) {
  state.selectedPatientId = patientId;
  renderPatientList();

  const patient = state.patients.find((p) => p.id === patientId);
  if (!patient) return;

  setHidden($("patientDetailEmpty"), true);
  setHidden($("patientDetailContent"), false);
  $("patientDetailName").textContent = patient.name;
  $("patientDetailMeta").textContent = "Loading scan history…";
  $("clearTrack").click();

  await refreshPatientHistory();
}

async function refreshPatientHistory() {
  if (!state.selectedPatientId) return;
  let scans = [];
  try {
    scans = await api.getPatientScans(state.selectedPatientId);
  } catch (err) {
    showToast("error", "Could not load history", err.message);
    return;
  }

  $("patientDetailMeta").textContent = `${scans.length} scan${scans.length === 1 ? "" : "s"} recorded`;
  renderHealingChart(scans);
  renderHistoryGrid(scans);
}

function renderHealingChart(scans) {
  const canvas = $("healingChart");
  setHidden($("chartEmptyHint"), scans.length !== 0);
  canvas.style.display = scans.length === 0 ? "none" : "block";
  if (scans.length === 0) {
    if (state.healingChart) {
      state.healingChart.destroy();
      state.healingChart = null;
    }
    return;
  }

  const sorted = [...scans].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
  const labels = sorted.map((s) => new Date(s.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }));
  const data = sorted.map((s) => s.area_cm2);

  if (state.healingChart) state.healingChart.destroy();

  const ctx = canvas.getContext("2d");
  const gradient = ctx.createLinearGradient(0, 0, 0, 200);
  gradient.addColorStop(0, "rgba(109,139,255,0.35)");
  gradient.addColorStop(1, "rgba(109,139,255,0)");

  state.healingChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Area (cm²)",
          data,
          borderColor: "#6d8bff",
          backgroundColor: gradient,
          pointBackgroundColor: "#38d9c9",
          pointBorderColor: "rgba(255,255,255,0.85)",
          pointBorderWidth: 1.5,
          pointRadius: 4,
          pointHoverRadius: 6,
          borderWidth: 2.5,
          tension: 0.35,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: "rgba(255,255,255,0.06)" }, ticks: { color: "#9aa2bd", font: { size: 11 } } },
        y: { grid: { color: "rgba(255,255,255,0.06)" }, ticks: { color: "#9aa2bd", font: { size: 11 } }, beginAtZero: true },
      },
    },
  });
}

function renderHistoryGrid(scans) {
  const grid = $("historyGrid");
  grid.innerHTML = "";
  const sorted = [...scans].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

  sorted.forEach((s) => {
    const card = document.createElement("div");
    card.className = "history-card";
    const dateStr = new Date(s.created_at).toLocaleString(undefined, {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
    card.innerHTML = `
      <div class="history-card__img"><img src="${api.scanImageUrl(s.id, "overlay")}" alt="Scan overlay" loading="lazy" /></div>
      <div class="history-card__body">
        <div class="history-card__date">${dateStr}</div>
        <div class="history-card__area">${fmtNum(s.area_cm2, 2)} cm²</div>
      </div>`;
    card.addEventListener("click", () => openLightbox(api.scanImageUrl(s.id, "overlay"), `${dateStr} · ${s.severity}`));
    grid.appendChild(card);
  });
}

setupDropzone({
  zone: $("dropzoneTrack"),
  input: $("fileTrack"),
  empty: $("dropzoneTrackEmpty"),
  preview: $("dropzoneTrackPreview"),
  img: $("previewTrackImg"),
  clearBtn: $("clearTrack"),
  onChange: (file) => (state.trackFile = file),
});

$("addVisitBtn").addEventListener("click", async () => {
  if (!state.selectedPatientId) return;
  if (!state.trackFile) {
    showToast("error", "No image selected", "Upload a scan for this visit first.");
    return;
  }

  const fd = new FormData();
  fd.append("image", state.trackFile);
  fd.append("ref_cm", $("refCm").value || "1.0");
  fd.append("ref_px", $("refPx").value || "38.46");
  fd.append("threshold", $("threshold").value);
  fd.append("prep_method", "None");
  fd.append("view_type", viewType);
  fd.append("patient_id", state.selectedPatientId);
  fd.append("save", "true");

  const btn = $("addVisitBtn");
  btn.classList.add("is-loading");
  btn.disabled = true;
  setLoading(true, "Recording visit…");

  try {
    await api.analyze(fd);
    $("clearTrack").click();
    await refreshPatientHistory();
    showToast("success", "Visit recorded", "Healing trajectory updated.");
  } catch (err) {
    showToast("error", "Could not record visit", err.message);
  } finally {
    btn.classList.remove("is-loading");
    btn.disabled = false;
    setLoading(false);
  }
});

// -------------------------------------------------------------------------
// Lightbox
// -------------------------------------------------------------------------
function openLightbox(src, caption) {
  $("lightboxImg").src = src;
  $("lightboxImg").alt = caption || "";
  $("lightboxCaption").textContent = caption || "";
  setHidden($("lightbox"), false);
}
function closeLightbox() {
  setHidden($("lightbox"), true);
  $("lightboxImg").src = "";
}
$("lightboxClose").addEventListener("click", closeLightbox);
$("lightbox").addEventListener("click", (e) => {
  if (e.target === $("lightbox")) closeLightbox();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeLightbox();
});

// -------------------------------------------------------------------------
// Init
// -------------------------------------------------------------------------
initTilt();
pollHealth();
setInterval(pollHealth, 20000);
loadPatients();
