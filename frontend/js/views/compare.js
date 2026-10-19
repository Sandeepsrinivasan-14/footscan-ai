/* Compare view: baseline vs follow-up via /api/compare, with a swipe slider and side-by-side panels. */

import { api } from "../api.js";
import { createDropzone } from "../components/dropzone.js";
import { field, numberInput, rangeField } from "../components/fields.js";
import { createProgress } from "../components/progress.js";
import { clear, countUp, fmtNum, h, icon, nextId, statusBadge, toast } from "../dom.js";

function swipe(beforeSrc, afterSrc) {
  const id = nextId("swipe");
  const afterImg = h("img", { class: "swipe__img", src: afterSrc, alt: "Follow-up photograph" });
  const beforeImg = h("img", { class: "swipe__img swipe__img--before", src: beforeSrc, alt: "Baseline photograph" });
  const handle = h("span", { class: "swipe__handle", "aria-hidden": "true" }, icon("compare", 16));
  const stage = h("div", { class: "swipe__stage" }, afterImg, beforeImg, handle, h("span", { class: "viewer__tag swipe__tag swipe__tag--l", text: "Baseline" }), h("span", { class: "viewer__tag swipe__tag swipe__tag--r viewer__tag--accent", text: "Follow-up" }));
  const slider = h("input", { class: "range swipe__range", id, type: "range", min: "0", max: "100", value: "50", "aria-label": "Swipe between baseline and follow-up" });
  const set = (v) => {
    stage.style.setProperty("--pos", `${v}%`);
  };
  slider.addEventListener("input", () => set(slider.value));
  set(50);
  return h("div", { class: "swipe" }, stage, slider);
}

export function createCompareView({ setSceneMode }) {
  const oldZone = createDropzone({ label: "Baseline photo", hint: "Earlier visit", onChange: () => refresh() });
  const newZone = createDropzone({ label: "Follow-up photo", hint: "Later visit", onChange: () => refresh() });
  const threshold = rangeField({ label: "Segmentation threshold", name: "cmp_threshold", min: 0.05, max: 0.95, step: 0.05, value: 0.5, format: (v) => Number(v).toFixed(2) });
  const refCm = numberInput({ name: "cmp_ref_cm", value: 1, min: 0.01, max: 1000 });
  const refPx = numberInput({ name: "cmp_ref_px", value: 38.46, min: 1, max: 100000 });
  const submit = h("button", { class: "btn btn--primary btn--lg", type: "submit", disabled: true }, icon("compare", 18), "Compare photos");
  const progress = createProgress();
  const out = h("div", { class: "results__out", "aria-live": "polite" });

  const empty = h(
    "div",
    { class: "empty" },
    h("span", { class: "empty__icon" }, icon("compare", 30)),
    h("h3", { text: "Change summary appears here" }),
    h("p", { class: "muted", text: "Add a baseline and a follow-up photo taken at the same scale. The comparison shows area change and a map of healed and newly affected tissue." }),
  );
  out.append(empty);

  let busy = false;
  function refresh() {
    submit.disabled = busy || !oldZone.file || !newZone.file;
  }

  const form = h(
    "form",
    { class: "stack", novalidate: true },
    h("div", { class: "grid-2 grid-2--zones" }, oldZone.el, newZone.el),
    threshold.el,
    h("fieldset", { class: "fieldset" }, h("legend", { text: "Scale calibration (applies to both photos)" }), h("div", { class: "grid-2" }, field("Reference length (cm)", refCm), field("Same length (pixels)", refPx))),
    submit,
  );

  function renderResults(res, baselineSrc, followSrc) {
    const change = res.change_cm2;
    const dir = change < -0.1 ? "down" : change > 0.1 ? "up" : "flat";
    const changeEl = h("span", { class: "metric__value mono" });
    countUp(changeEl, Math.abs(change), { digits: 2 });
    const oldEl = h("span", { class: "metric__value mono" });
    const newEl = h("span", { class: "metric__value mono" });
    countUp(oldEl, res.old_area_cm2, { digits: 2 });
    countUp(newEl, res.new_area_cm2, { digits: 2 });
    const pct = res.old_area_cm2 > 0 ? (change / res.old_area_cm2) * 100 : null;

    const metrics = h(
      "div",
      { class: "metrics metrics--3" },
      h("div", { class: "metric glass" }, h("div", { class: "metric__head" }, icon("ruler", 16), h("span", { text: "Baseline area" })), h("div", { class: "metric__body" }, oldEl, h("span", { class: "metric__unit", text: "cm²" }))),
      h("div", { class: "metric glass" }, h("div", { class: "metric__head" }, icon("ruler", 16), h("span", { text: "Follow-up area" })), h("div", { class: "metric__body" }, newEl, h("span", { class: "metric__unit", text: "cm²" }))),
      h(
        "div",
        { class: `metric glass metric--delta metric--${dir}` },
        h("div", { class: "metric__head" }, icon(dir === "flat" ? "flat" : dir, 16), h("span", { text: "Change" })),
        h("div", { class: "metric__body" }, h("span", { class: "metric__sign mono", text: change > 0 ? "+" : change < 0 ? "−" : "" }), changeEl, h("span", { class: "metric__unit", text: "cm²" })),
        pct !== null ? h("span", { class: "tag", text: `${pct > 0 ? "+" : ""}${fmtNum(pct, 1)}% vs baseline` }) : null,
      ),
    );

    const panels = h(
      "div",
      { class: "triptych" },
      h("figure", { class: "viewer__frame" }, h("img", { class: "triptych__img", src: baselineSrc, alt: "Baseline photograph" }), h("figcaption", {}, h("span", { class: "viewer__tag", text: "Baseline" }))),
      h("figure", { class: "viewer__frame" }, h("img", { class: "triptych__img", src: followSrc, alt: "Follow-up photograph" }), h("figcaption", {}, h("span", { class: "viewer__tag", text: "Follow-up" }))),
      h(
        "figure",
        { class: "viewer__frame" },
        h("img", { class: "triptych__img", src: res.diff_image, alt: "Change map: blue marks tissue that healed, red marks newly affected tissue" }),
        h("figcaption", {}, h("span", { class: "viewer__tag viewer__tag--accent", text: "Change map" })),
      ),
    );
    const legend = h(
      "ul",
      { class: "legend", "aria-label": "Change map legend" },
      h("li", {}, h("span", { class: "legend__swatch legend__swatch--healed" }), "Healed (in baseline, not in follow-up)"),
      h("li", {}, h("span", { class: "legend__swatch legend__swatch--new" }), "New or enlarged (not in baseline)"),
    );

    clear(out).append(
      h(
        "div",
        { class: "result-body" },
        h("div", { class: "result-head" }, h("div", { class: "result-head__main" }, h("div", { class: "badges" }, statusBadge(res.status)), h("p", { class: "muted result-head__ctx", text: "Both photos are segmented independently; differences below ±0.1 cm² count as stable." }))),
        metrics,
        panels,
        legend,
        h("h3", { class: "subhead", text: "Swipe comparison" }),
        swipe(baselineSrc, followSrc),
        h("p", { class: "disclaimer-line", text: res.disclaimer }),
      ),
    );
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (busy || !oldZone.file || !newZone.file || !form.reportValidity?.()) return;
    const fd = new FormData();
    fd.append("old_image", oldZone.file);
    fd.append("new_image", newZone.file);
    fd.append("ref_cm", refCm.value);
    fd.append("ref_px", refPx.value);
    fd.append("threshold", threshold.input.value);

    // Keep the previews alive for the results even if the user changes the dropzones meanwhile.
    const baselineSrc = URL.createObjectURL(oldZone.file);
    const followSrc = URL.createObjectURL(newZone.file);

    busy = true;
    refresh();
    setSceneMode("busy");
    clear(out);
    progress.start();
    try {
      const res = await api.compare(fd, (f) => progress.setUpload(f));
      progress.finish();
      await new Promise((r) => setTimeout(r, 320));
      progress.reset();
      renderResults(res, baselineSrc, followSrc);
      toast("success", "Comparison complete");
    } catch (err) {
      progress.fail();
      out.append(empty);
      URL.revokeObjectURL(baselineSrc);
      URL.revokeObjectURL(followSrc);
      toast("error", "Comparison failed", err.message, 8000);
    } finally {
      busy = false;
      refresh();
      setSceneMode("idle");
    }
  });

  const el = h(
    "div",
    {},
    h(
      "header",
      { class: "page-head" },
      h("h1", { id: "compare-title" }, "Compare ", h("span", { class: "grad", text: "two visits" })),
      h("p", { class: "muted", text: "Quantify how a wound changed between two photographs taken at the same scale." }),
    ),
    h(
      "div",
      { class: "workspace" },
      h("section", { class: "panel glass", "aria-label": "Compare inputs" }, h("header", { class: "panel__head" }, h("span", { class: "step-no", text: "1" }), h("h2", { text: "Photos" })), form),
      h("section", { class: "panel glass results", "aria-label": "Comparison results" }, h("header", { class: "panel__head" }, h("span", { class: "step-no", text: "2" }), h("h2", { text: "Change" })), progress.el, out),
    ),
  );
  return { el, title: "Compare" };
}
