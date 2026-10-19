/* Segmentation viewer: layered result image with an overlay-opacity slider and a side-by-side mode.

   Layers come from the API response (`images.*`, base64 JPEG data URIs, all 256x256):
     overlay  - the binary mask tinted on top of the original, drawn on a canvas so the opacity
                slider is live and the mask edge gets a soft glow
     heatmap  - model confidence (JET colormap) blended over the original
     edges / mask / cropped - shown as returned
*/

import { h, icon, nextId, reduceMotion } from "../dom.js";

const LAYERS = [
  { key: "overlay", label: "Overlay", opacity: true },
  { key: "heatmap", label: "Confidence", opacity: true },
  { key: "edges", label: "Edges", opacity: false },
  { key: "mask", label: "Mask", opacity: false },
  { key: "cropped", label: "Crop", opacity: false },
  { key: "original", label: "Original", opacity: false },
];

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("image failed to load"));
    img.src = src;
  });
}

/** Build an offscreen canvas that is `color` where the mask is on and transparent elsewhere. */
async function buildTint(maskSrc, rgb) {
  const img = await loadImage(maskSrc);
  const w = img.naturalWidth;
  const hgt = img.naturalHeight;
  const src = document.createElement("canvas");
  src.width = w;
  src.height = hgt;
  const sctx = src.getContext("2d", { willReadFrequently: true });
  sctx.drawImage(img, 0, 0);
  const data = sctx.getImageData(0, 0, w, hgt);
  const px = data.data;
  for (let i = 0; i < px.length; i += 4) {
    const on = px[i] > 127;
    px[i] = rgb[0];
    px[i + 1] = rgb[1];
    px[i + 2] = rgb[2];
    px[i + 3] = on ? 255 : 0;
  }
  sctx.putImageData(data, 0, 0);
  return src;
}

/**
 * @param {{original: string, mask: string, heatmap: string, blended: string, edges: string, cropped: string}} images
 */
export function createViewer(images) {
  const sliderId = nextId("opacity");
  const state = { layer: "overlay", opacity: 0.6, split: false };
  let tint = null;
  let overlayCanvas = null;

  const baseImg = h("img", { class: "viewer__img", src: images.original, alt: "Original wound photograph" });
  const topImg = h("img", { class: "viewer__img viewer__img--top", alt: "", hidden: true });
  const canvas = h("canvas", { class: "viewer__canvas", width: "256", height: "256", "aria-hidden": "true" });
  const stage = h("div", { class: "viewer__stage" }, baseImg, topImg, canvas, h("div", { class: "viewer__scan", "aria-hidden": "true" }));

  const splitImg = h("img", { class: "viewer__img", src: images.original, alt: "Original wound photograph" });
  const splitStage = h("div", { class: "viewer__stage" }, splitImg);
  const splitLabel = h("span", { class: "viewer__tag", text: "Original" });
  const mainLabel = h("span", { class: "viewer__tag viewer__tag--accent", text: "Overlay" });

  const frames = h(
    "div",
    { class: "viewer__frames" },
    h("figure", { class: "viewer__frame viewer__frame--pair", hidden: true }, splitStage, h("figcaption", {}, splitLabel)),
    h("figure", { class: "viewer__frame" }, stage, h("figcaption", {}, mainLabel)),
  );
  const pairFrame = frames.firstElementChild;

  const opacityValue = h("output", { class: "mono", for: sliderId, text: "60%" });
  const slider = h("input", {
    class: "range",
    id: sliderId,
    type: "range",
    min: "0",
    max: "100",
    step: "1",
    value: "60",
    "aria-label": "Overlay opacity",
  });
  const opacityRow = h("div", { class: "viewer__opacity" }, h("label", { for: sliderId, text: "Overlay opacity" }), slider, opacityValue);

  const tabs = LAYERS.map((layer) =>
    h(
      "button",
      { class: "seg__btn", type: "button", role: "tab", "aria-selected": layer.key === state.layer ? "true" : "false", dataset: { layer: layer.key }, tabindex: layer.key === state.layer ? "0" : "-1" },
      layer.label,
    ),
  );
  const tablist = h("div", { class: "seg viewer__tabs", role: "tablist", "aria-label": "Visualization layer" }, tabs);

  const splitToggle = h(
    "button",
    { class: "btn btn--ghost btn--sm", type: "button", "aria-pressed": "false" },
    icon("compare", 16),
    "Side by side",
  );

  const root = h("div", { class: "viewer" }, h("div", { class: "viewer__bar" }, tablist, splitToggle), frames, opacityRow);

  function drawOverlay(target) {
    const ctx = target.getContext("2d");
    ctx.clearRect(0, 0, target.width, target.height);
    if (!overlayCanvas) return;
    ctx.save();
    ctx.globalAlpha = state.opacity;
    ctx.shadowColor = "rgba(94, 234, 212, 0.9)";
    ctx.shadowBlur = 6;
    ctx.drawImage(overlayCanvas, 0, 0, target.width, target.height);
    ctx.restore();
  }

  function render() {
    const layer = LAYERS.find((l) => l.key === state.layer);
    const label = layer.label;
    mainLabel.textContent = label;
    opacityRow.hidden = !layer.opacity;
    slider.disabled = !layer.opacity;

    // Main stage
    canvas.hidden = state.layer !== "overlay";
    if (state.layer === "overlay") {
      baseImg.src = images.original;
      topImg.hidden = true;
      drawOverlay(canvas);
    } else if (state.layer === "heatmap") {
      baseImg.src = images.original;
      topImg.src = images.heatmap;
      topImg.alt = "Model confidence heatmap";
      topImg.hidden = false;
      topImg.style.opacity = String(state.opacity);
    } else {
      baseImg.src = images[state.layer];
      baseImg.alt = `${label} view`;
      topImg.hidden = true;
    }

    // Side-by-side: original on the left, selected layer on the right.
    pairFrame.hidden = !state.split;
    frames.classList.toggle("is-split", state.split);
    tabs.forEach((t) => {
      const on = t.dataset.layer === state.layer;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
    });
    splitToggle.setAttribute("aria-pressed", String(state.split));
    splitToggle.classList.toggle("is-on", state.split);
  }

  tablist.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-layer]");
    if (!btn) return;
    state.layer = btn.dataset.layer;
    render();
  });
  tablist.addEventListener("keydown", (e) => {
    const idx = tabs.findIndex((t) => t.dataset.layer === state.layer);
    let next = idx;
    if (e.key === "ArrowRight") next = (idx + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (idx - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    else return;
    e.preventDefault();
    state.layer = tabs[next].dataset.layer;
    render();
    tabs[next].focus();
  });
  slider.addEventListener("input", () => {
    state.opacity = Number(slider.value) / 100;
    opacityValue.textContent = `${slider.value}%`;
    if (state.layer === "overlay") drawOverlay(canvas);
    else if (state.layer === "heatmap") topImg.style.opacity = String(state.opacity);
  });
  splitToggle.addEventListener("click", () => {
    state.split = !state.split;
    render();
  });

  // Tint the mask in the app accent color; failure just means the overlay layer shows nothing.
  buildTint(images.mask, [94, 234, 212])
    .then((c) => {
      overlayCanvas = c;
      if (state.layer === "overlay") drawOverlay(canvas);
    })
    .catch(() => {
      overlayCanvas = null;
    });

  if (!reduceMotion()) stage.classList.add("is-scanning");
  setTimeout(() => stage.classList.remove("is-scanning"), 1900);

  render();
  return { el: root };
}
