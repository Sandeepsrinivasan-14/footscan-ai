/* Analyze view: capture an image, run /api/analyze, show segmentation + metrics. */

import { api, downloadReport } from "../api.js";
import { createDropzone } from "../components/dropzone.js";
import { createPatientPicker, field, numberInput, rangeField, segmented, selectInput } from "../components/fields.js";
import { createProgress } from "../components/progress.js";
import { createViewer } from "../components/viewer.js";
import { clear, countUp, fmtNum, h, icon, severityBadge, statusBadge, svgEl, toast } from "../dom.js";
import { store } from "../store.js";

const MAX_SINBAD = 6;

function gauge(score, severity) {
  const r = 30;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, score / MAX_SINBAD));
  const tone = { Mild: "ok", Moderate: "warn", Severe: "danger" }[severity] || "info";
  const arc = svgEl("circle", { class: `gauge__arc gauge__arc--${tone}`, cx: 40, cy: 40, r, "stroke-dasharray": `${(c * pct).toFixed(1)} ${c.toFixed(1)}`, transform: "rotate(-90 40 40)" });
  return h(
    "div",
    { class: "gauge", role: "img", "aria-label": `SINBAD-style score ${score} out of ${MAX_SINBAD}, ${severity} severity` },
    svgEl("svg", { viewBox: "0 0 80 80", width: 88, height: 88, "aria-hidden": "true" }, svgEl("circle", { class: "gauge__track", cx: 40, cy: 40, r }), arc),
    h("div", { class: "gauge__label" }, h("strong", { class: "mono", text: String(score) }), h("span", { text: `/ ${MAX_SINBAD}` })),
  );
}

function metricCard({ iconName, label, value, unit = "", digits, numeric = true, note = "", wide = false }) {
  const valueEl = h("span", { class: numeric ? "metric__value mono" : "metric__value metric__value--text" });
  if (numeric) countUp(valueEl, value, { digits, suffix: "" });
  else valueEl.textContent = String(value);
  return h(
    "div",
    { class: `metric glass${wide ? " metric--wide" : ""}` },
    h("div", { class: "metric__head" }, icon(iconName, 16), h("span", { text: label })),
    h("div", { class: "metric__body" }, valueEl, unit ? h("span", { class: "metric__unit", text: unit }) : null),
    note ? h("span", { class: "tag", text: note }) : null,
  );
}

export function createAnalyzeView({ setSceneMode }) {
  const dropzone = createDropzone({ label: "Wound photograph", onChange: () => refreshButton() });
  const picker = createPatientPicker();
  const viewType = segmented({
    name: "view_type",
    label: "View",
    value: "Plantar (Bottom)",
    options: [
      { value: "Plantar (Bottom)", label: "Plantar" },
      { value: "Dorsal (Top)", label: "Dorsal" },
    ],
  });
  const prep = selectInput({
    name: "prep_method",
    value: "None",
    options: [
      { value: "None", label: "None" },
      { value: "CLAHE", label: "CLAHE (local contrast)" },
      { value: "Histogram Equalization", label: "Histogram equalization" },
    ],
  });
  const threshold = rangeField({ label: "Segmentation threshold", name: "threshold", min: 0.05, max: 0.95, step: 0.05, value: 0.5, format: (v) => Number(v).toFixed(2) });
  const refCm = numberInput({ name: "ref_cm", value: 1, min: 0.01, max: 1000 });
  const refPx = numberInput({ name: "ref_px", value: 38.46, min: 1, max: 100000 });
  const save = h("input", { class: "switch__input", type: "checkbox", id: "save-scan", checked: true });
  const saveRow = h("label", { class: "switch", for: "save-scan" }, save, h("span", { class: "switch__track", "aria-hidden": "true" }), h("span", { text: "Save scan to history" }));

  const submit = h("button", { class: "btn btn--primary btn--lg", type: "submit", disabled: true }, icon("scan", 18), "Run analysis");
  const progress = createProgress();

  const form = h(
    "form",
    { class: "stack", novalidate: true },
    dropzone.el,
    picker.el,
    h("div", { class: "grid-2" }, viewType.el, field("Pre-processing", prep)),
    threshold.el,
    h(
      "fieldset",
      { class: "fieldset" },
      h("legend", { text: "Scale calibration" }),
      h("div", { class: "grid-2" }, field("Reference length (cm)", refCm), field("Same length (pixels)", refPx)),
      h("p", { class: "field__help", text: "Measure a ruler or marker visible in the photo. Without it, the default scale of 38.46 px per cm is only a placeholder and areas are not meaningful." }),
    ),
    saveRow,
    submit,
  );

  const capture = h("section", { class: "panel glass", "aria-labelledby": "capture-title" }, h("header", { class: "panel__head" }, h("span", { class: "step-no", text: "1" }), h("h2", { id: "capture-title", text: "Capture" })), form);

  const empty = h(
    "div",
    { class: "empty" },
    h("span", { class: "empty__icon" }, icon("scan", 30)),
    h("h3", { text: "Results appear here" }),
    h("p", { class: "muted", text: "Add a photo and run the analysis. You will get a segmentation overlay, area and shape, a tissue estimate, a heuristic severity score and a downloadable PDF." }),
  );
  const out = h("div", { class: "results__out", "aria-live": "polite" });
  const resultsPanel = h(
    "section",
    { class: "panel glass results", "aria-labelledby": "results-title", "aria-busy": "false" },
    h("header", { class: "panel__head" }, h("span", { class: "step-no", text: "2" }), h("h2", { id: "results-title", text: "Results" })),
    progress.el,
    out,
  );
  out.append(empty);

  let busy = false;
  function refreshButton() {
    submit.disabled = busy || !dropzone.file;
  }

  function setBusy(next) {
    busy = next;
    resultsPanel.setAttribute("aria-busy", String(next));
    submit.classList.toggle("is-loading", next);
    submit.querySelector("svg").style.opacity = next ? "0" : "";
    refreshButton();
    setSceneMode(next ? "busy" : "idle");
  }

  function renderResults(res) {
    const detected = res.status === "ULCER DETECTED";
    const patientName = store.patientName(res.patient_id);

    const actions = h(
      "div",
      { class: "result-actions" },
      res.scan_id
        ? h(
            "button",
            {
              class: "btn btn--ghost btn--sm",
              type: "button",
              onclick: async (e) => {
                const btn = e.currentTarget;
                btn.disabled = true;
                try {
                  await downloadReport(res.scan_id, patientName);
                } catch (err) {
                  toast("error", "Could not download the report", err.message);
                } finally {
                  btn.disabled = false;
                }
              },
            },
            icon("download", 16),
            "PDF report",
          )
        : h("span", { class: "tag", text: "Not saved" }),
    );

    const header = h(
      "div",
      { class: "result-head" },
      h("div", { class: "result-head__main" }, h("div", { class: "badges" }, statusBadge(res.status), detected ? severityBadge(res.severity) : null), h("p", { class: "muted result-head__ctx", text: `${res.view_type} · threshold ${fmtNum(res.threshold)} · pre-processing: ${res.preprocessing}${patientName ? ` · ${patientName}` : ""}` })),
      detected ? gauge(res.sinbad_score, res.severity) : null,
      actions,
    );

    const viewer = createViewer(res.images);

    const metrics = h(
      "div",
      { class: "metrics" },
      metricCard({ iconName: "ruler", label: "Wound area", value: res.area_cm2, unit: "cm²", digits: 2 }),
      metricCard({ iconName: "target", label: "Image coverage", value: res.ulcer_percent, unit: "%", digits: 2 }),
      metricCard({ iconName: "pulse", label: "Peak confidence", value: res.max_confidence * 100, unit: "%", digits: 1 }),
      metricCard({ iconName: "shape", label: "Shape", value: res.shape, numeric: false }),
      metricCard({ iconName: "drop", label: "Tissue colour", value: res.color_profile, numeric: false, note: "heuristic", wide: true }),
      metricCard({ iconName: "clock", label: "Est. healing", value: res.est_healing_days, unit: "days", digits: 0, note: "heuristic" }),
    );

    const note = h(
      "div",
      { class: "note glass" },
      h("div", { class: "note__head" }, icon("info", 16), h("strong", { text: "Suggested care note" }), h("span", { class: "tag", text: "heuristic, not clinical advice" })),
      h("p", { text: res.treatment }),
    );

    const gallery = h(
      "details",
      { class: "gallery" },
      h("summary", { text: "All pipeline images" }),
      h(
        "div",
        { class: "gallery__grid" },
        ["original", "mask", "heatmap", "blended", "edges", "cropped"].map((k) =>
          h("figure", {}, h("img", { src: res.images[k], alt: `${k} image` }), h("figcaption", { text: k })),
        ),
      ),
    );

    clear(out).append(h("div", { class: "result-body" }, header, h("div", { class: "result-grid" }, viewer.el, h("div", { class: "result-side" }, metrics, note)), gallery, h("p", { class: "disclaimer-line", text: res.disclaimer })));
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (busy) return;
    const file = dropzone.file;
    if (!file) {
      toast("info", "Add a photo first");
      return;
    }
    if (!form.reportValidity?.()) return;

    const fd = new FormData();
    fd.append("image", file);
    fd.append("ref_cm", refCm.value);
    fd.append("ref_px", refPx.value);
    fd.append("threshold", threshold.input.value);
    fd.append("prep_method", prep.value);
    fd.append("view_type", viewType.value);
    fd.append("save", save.checked ? "true" : "false");
    if (picker.value) fd.append("patient_id", picker.value);

    setBusy(true);
    clear(out);
    progress.start();
    try {
      const res = await api.analyze(fd, (f) => progress.setUpload(f));
      progress.finish();
      await new Promise((r) => setTimeout(r, 320));
      progress.reset();
      renderResults(res);
      toast("success", "Analysis complete", res.scan_id ? "Saved to history." : "Not saved to history.");
      out.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      progress.fail();
      out.append(empty);
      toast("error", "Analysis failed", err.message, 8000);
    } finally {
      setBusy(false);
    }
  });

  const hero = h(
    "section",
    { class: "hero", "aria-labelledby": "hero-title" },
    h(
      "div",
      { class: "hero__copy" },
      h("span", { class: "eyebrow" }, icon("scan", 14), "Wound segmentation · research prototype"),
      h("h1", { id: "hero-title" }, "See the wound. ", h("span", { class: "grad", text: "Measure the change." })),
      h("p", { class: "hero__lead", text: "Upload a diabetic foot photograph to segment the wound, measure its area and shape, and track healing across visits. A research tool, not a diagnosis." }),
      h("ul", { class: "chips", "aria-label": "Highlights" }, ["ResNet34-UNet", "Area · shape · tissue", "Healing timeline", "PDF reports"].map((t) => h("li", { class: "chip", text: t }))),
    ),
    h("div", { class: "hero__scene", id: "heroScene", "aria-hidden": "true" }, h("div", { class: "hero__orb" }), h("canvas", { id: "heroCanvas" })),
  );

  const el = h("div", {}, hero, h("div", { class: "workspace" }, capture, resultsPanel));
  return {
    el,
    title: "Analyze",
    onShow() {
      if (!store.loaded) store.refreshPatients().catch(() => {});
    },
  };
}
