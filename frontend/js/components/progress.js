/* Animated multi-step analysis progress.

   The server runs the whole pipeline inside one request, so only the *upload* phase reports real
   progress. The later stages advance on a timer and are indicative; the final step completes when
   the response actually arrives. This is stated in the component's accessible description. */

import { h, icon, nextId, reduceMotion } from "../dom.js";

const STEPS = [
  { key: "upload", label: "Uploading image", icon: "upload" },
  { key: "prep", label: "Validating & pre-processing", icon: "image" },
  { key: "segment", label: "Segmenting wound (ResNet34-UNet)", icon: "scan" },
  { key: "measure", label: "Measuring area, shape & tissue", icon: "ruler" },
  { key: "score", label: "Scoring & preparing visuals", icon: "pulse" },
];

// Rough cumulative delays (ms) before stages 2..5 are shown as active while we wait on the server.
const STAGE_DELAYS = [350, 1100, 2400, 3600];

export function createProgress() {
  const bar = h("span", { class: "progress__fill" });
  const track = h("div", { class: "progress__track", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": "0", "aria-label": "Analysis progress" }, bar);
  const items = STEPS.map((s) =>
    h("li", { class: "progress__step", dataset: { state: "idle" } }, h("span", { class: "progress__bullet" }, icon(s.icon, 16)), h("span", { text: s.label })),
  );
  const status = h("p", { class: "sr-only", role: "status" });
  const noteId = nextId("progress-note");
  const el = h(
    "div",
    { class: "progress", hidden: true, "aria-describedby": noteId },
    h("div", { class: "progress__head" }, h("strong", { text: "Analyzing" }), h("span", { class: "mono progress__pct", text: "0%" })),
    track,
    h("ol", { class: "progress__steps" }, items),
    h("p", { class: "progress__note muted", id: noteId, text: "Only the upload reports real progress; later stages are indicative while the server works." }),
    status,
  );
  const pct = el.querySelector(".progress__pct");

  let timers = [];
  let current = -1;

  function setPct(value) {
    const v = Math.max(0, Math.min(100, Math.round(value)));
    bar.style.width = `${v}%`;
    track.setAttribute("aria-valuenow", String(v));
    pct.textContent = `${v}%`;
  }

  function activate(index) {
    current = index;
    items.forEach((li, i) => {
      li.dataset.state = i < index ? "done" : i === index ? "active" : "idle";
    });
    status.textContent = STEPS[index] ? STEPS[index].label : "";
    // Stages 1..4 fill the bar up to 92%; the last 8% is reserved for the real response.
    setPct(Math.min(92, (index / STEPS.length) * 100 + 8));
  }

  function clearTimers() {
    timers.forEach(clearTimeout);
    timers = [];
  }

  return {
    el,
    start() {
      clearTimers();
      el.hidden = false;
      setPct(2);
      activate(0);
      const factor = reduceMotion() ? 0.5 : 1;
      STAGE_DELAYS.forEach((ms, i) => timers.push(setTimeout(() => current < i + 1 && activate(i + 1), ms * factor)));
    },
    /** Real upload progress, 0..1. Moves to the next stage once the bytes are sent. */
    setUpload(fraction) {
      if (current === 0) setPct(2 + fraction * 14);
      if (fraction >= 1 && current === 0) activate(1);
    },
    finish() {
      clearTimers();
      items.forEach((li) => (li.dataset.state = "done"));
      setPct(100);
      status.textContent = "Analysis complete";
    },
    fail() {
      clearTimers();
      el.hidden = true;
    },
    reset() {
      clearTimers();
      el.hidden = true;
      setPct(0);
    },
  };
}
