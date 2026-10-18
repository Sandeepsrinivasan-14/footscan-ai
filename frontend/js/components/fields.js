/* Shared form controls: labelled fields, a range with live value, a segmented radio group,
   and the patient picker used by the Analyze view. */

import { h, icon, nextId, toast } from "../dom.js";
import { store } from "../store.js";

export function field(label, control, { help = "", id = control.id } = {}) {
  const helpId = help ? nextId("help") : "";
  if (helpId) control.setAttribute("aria-describedby", helpId);
  return h(
    "div",
    { class: "field" },
    h("label", { class: "field__label", for: id, text: label }),
    control,
    help ? h("p", { class: "field__help", id: helpId, text: help }) : null,
  );
}

export function numberInput({ value, min, max, step = "any", name }) {
  return h("input", { class: "input mono", id: nextId(name), name, type: "number", inputmode: "decimal", value: String(value), min, max, step, required: true });
}

export function selectInput({ name, options, value }) {
  const select = h("select", { class: "input", id: nextId(name), name });
  for (const opt of options) {
    const o = h("option", { value: opt.value, text: opt.label });
    if (opt.value === value) o.selected = true;
    select.append(o);
  }
  return select;
}

/** A range input with a live numeric readout. Returns {el, input}. */
export function rangeField({ label, name, min, max, step, value, format = (v) => v }) {
  const id = nextId(name);
  const out = h("output", { class: "mono range-out", for: id, text: format(value) });
  const input = h("input", { class: "range", id, name, type: "range", min, max, step, value: String(value) });
  input.addEventListener("input", () => {
    out.textContent = format(Number(input.value));
  });
  const el = h("div", { class: "field" }, h("div", { class: "field__row" }, h("label", { class: "field__label", for: id, text: label }), out), input);
  return { el, input };
}

/** Segmented control backed by real radio inputs (keyboard + screen-reader friendly). */
export function segmented({ name, label, options, value }) {
  const group = nextId(name);
  const root = h("div", { class: "field" }, h("span", { class: "field__label", id: group, text: label }));
  const seg = h("div", { class: "seg", role: "radiogroup", "aria-labelledby": group });
  for (const opt of options) {
    const id = nextId(name);
    const input = h("input", { class: "seg__input", type: "radio", name: group, id, value: opt.value });
    if (opt.value === value) input.checked = true;
    seg.append(input, h("label", { class: "seg__btn", for: id, text: opt.label }));
  }
  root.append(seg);
  return {
    el: root,
    get value() {
      return seg.querySelector("input:checked")?.value ?? value;
    },
  };
}

/** Patient picker with an inline "add patient" form. */
export function createPatientPicker({ selectName = "patient_id" } = {}) {
  const select = h("select", { class: "input", id: nextId("patient"), name: selectName });
  const nameInput = h("input", { class: "input", id: nextId("newpatient"), type: "text", maxlength: "255", placeholder: "Patient name or code", autocomplete: "off" });
  const addBtn = h("button", { class: "btn btn--primary btn--sm", type: "submit" }, icon("plus", 16), "Add");
  const addForm = h(
    "form",
    { class: "inline-form", hidden: true, novalidate: true },
    h("label", { class: "sr-only", for: nameInput.id, text: "New patient name" }),
    nameInput,
    addBtn,
  );
  const toggle = h("button", { class: "btn btn--ghost btn--sm", type: "button", "aria-expanded": "false" }, icon("plus", 16), "New");
  const hint = h("p", { class: "field__help", text: "Use a pseudonymous code, not a real name. Data is stored unencrypted." });

  function render() {
    const keep = store.selectedPatientId;
    select.replaceChildren(h("option", { value: "", text: "No patient (unlinked scan)" }));
    for (const p of store.patients) select.append(h("option", { value: p.id, text: p.name }));
    select.value = store.patients.some((p) => p.id === keep) ? keep : "";
  }

  toggle.addEventListener("click", () => {
    const open = addForm.hidden;
    addForm.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    if (open) nameInput.focus();
  });
  select.addEventListener("change", () => store.select(select.value));
  addForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = nameInput.value.trim();
    if (!name) {
      nameInput.focus();
      return;
    }
    addBtn.disabled = true;
    try {
      const patient = await store.addPatient(name);
      store.select(patient.id);
      nameInput.value = "";
      addForm.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
      toast("success", "Patient added", patient.name);
    } catch (err) {
      toast("error", "Could not add patient", err.message);
    } finally {
      addBtn.disabled = false;
    }
  });
  store.subscribe(render);
  render();

  const el = h(
    "div",
    { class: "field" },
    h("label", { class: "field__label", for: select.id, text: "Patient" }),
    h("div", { class: "field__row field__row--gap" }, select, toggle),
    addForm,
    hint,
  );
  return { el, select, get value() { return select.value; } };
}
