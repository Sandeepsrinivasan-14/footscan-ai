/* Accessible drag-and-drop image picker.
   Keyboard: Tab to the zone, Enter/Space opens the file dialog. Click, drop and (when focused) paste all work. */

import { fmtBytes, h, icon, nextId, toast } from "../dom.js";

export const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp", "image/bmp"];
export const MAX_BYTES = 15 * 1024 * 1024; // mirrors the server default (FOOTSCAN_MAX_UPLOAD_BYTES)

/**
 * @param {{label: string, hint?: string, onChange?: (file: File|null) => void}} opts
 */
export function createDropzone({ label, hint = "JPEG, PNG, WEBP or BMP · up to 15 MB", onChange }) {
  const inputId = nextId("file");
  const descId = nextId("dz-desc");
  let file = null;
  let previewUrl = "";

  const input = h("input", { class: "sr-only", id: inputId, type: "file", accept: ACCEPTED_TYPES.join(","), tabindex: "-1", "aria-label": label });
  const preview = h("img", { class: "dropzone__preview", alt: "", hidden: true });
  const emptyState = h(
    "div",
    { class: "dropzone__empty" },
    h("span", { class: "dropzone__icon" }, icon("upload", 26)),
    h("strong", { text: label }),
    h("span", { class: "dropzone__cta" }, "Drag a photo here, or ", h("u", { text: "browse" })),
    h("span", { class: "dropzone__hint", id: descId, text: hint }),
  );
  const meta = h("div", { class: "dropzone__meta", hidden: true });
  const removeBtn = h("button", { class: "dropzone__remove", type: "button", "aria-label": `Remove ${label.toLowerCase()}`, hidden: true }, icon("x", 16));

  // A real <button> covers the zone (keyboard + screen-reader entry point); the remove button is its
  // sibling, never nested inside it.
  const pick = h("button", { class: "dropzone__pick", type: "button", "aria-describedby": descId, "aria-label": `${label}. Choose an image file` });
  const zone = h("div", { class: "dropzone" }, preview, emptyState, meta, pick, removeBtn);
  const root = h("div", { class: "dropzone-wrap" }, zone, input);

  function accept(candidate) {
    if (!candidate) return;
    if (!ACCEPTED_TYPES.includes(candidate.type)) {
      toast("error", "Unsupported file", "Please choose a JPEG, PNG, WEBP or BMP image.");
      return;
    }
    if (candidate.size > MAX_BYTES) {
      toast("error", "File too large", `The limit is ${fmtBytes(MAX_BYTES)}; this file is ${fmtBytes(candidate.size)}.`);
      return;
    }
    setFile(candidate);
  }

  function setFile(next) {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    file = next;
    previewUrl = next ? URL.createObjectURL(next) : "";
    preview.hidden = !next;
    emptyState.hidden = !!next;
    meta.hidden = !next;
    removeBtn.hidden = !next;
    zone.classList.toggle("has-file", !!next);
    if (next) {
      preview.src = previewUrl;
      meta.replaceChildren(h("strong", { text: next.name }), h("span", { class: "mono", text: fmtBytes(next.size) }));
      pick.setAttribute("aria-label", `${label}: ${next.name}. Choose a different image`);
    } else {
      preview.removeAttribute("src");
      input.value = "";
      pick.setAttribute("aria-label", `${label}. Choose an image file`);
    }
    onChange?.(next);
  }

  pick.addEventListener("click", () => input.click());
  pick.addEventListener("paste", (e) => {
    const item = [...(e.clipboardData?.files || [])].find((f) => f.type.startsWith("image/"));
    if (item) accept(item);
  });
  input.addEventListener("change", () => accept(input.files?.[0]));
  removeBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    setFile(null);
    pick.focus();
  });

  let depth = 0;
  zone.addEventListener("dragenter", (e) => {
    e.preventDefault();
    depth++;
    zone.classList.add("is-dragover");
  });
  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
  });
  zone.addEventListener("dragleave", () => {
    depth = Math.max(0, depth - 1);
    if (!depth) zone.classList.remove("is-dragover");
  });
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    depth = 0;
    zone.classList.remove("is-dragover");
    accept(e.dataTransfer?.files?.[0]);
  });

  return {
    el: root,
    get file() {
      return file;
    },
    get previewUrl() {
      return previewUrl;
    },
    clear: () => setFile(null),
  };
}
