/* Patients view: patient list + per-patient healing timeline built from /api/patients/{id}/scans. */

import { api, downloadReport, scanImageUrl } from "../api.js";
import { createTrendChart } from "../components/chart.js";
import { clear, countUp, fmtDate, fmtNum, h, icon, severityBadge, statusBadge, toast } from "../dom.js";
import { store } from "../store.js";

function initials(name) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join("");
}

function delta(prev, cur) {
  if (prev === undefined) return null;
  const d = cur - prev;
  const dir = d < -0.05 ? "down" : d > 0.05 ? "up" : "flat";
  const label = dir === "flat" ? "no change" : `${d > 0 ? "+" : "−"}${fmtNum(Math.abs(d))} cm²`;
  return h("span", { class: `delta delta--${dir}`, title: "Change in area since the previous scan" }, icon(dir, 14), label);
}

export function createPatientsView({ navigate }) {
  let selectedId = "";
  let query = "";
  let loadToken = 0;

  const search = h("input", { class: "input", type: "search", placeholder: "Search patients", "aria-label": "Search patients", autocomplete: "off" });
  const nameInput = h("input", { class: "input", type: "text", maxlength: "255", placeholder: "New patient name or code", "aria-label": "New patient name or code", autocomplete: "off" });
  const addBtn = h("button", { class: "btn btn--primary", type: "submit" }, icon("plus", 16), "Add");
  const addForm = h("form", { class: "inline-form", novalidate: true }, nameInput, addBtn);
  const list = h("ul", { class: "plist", "aria-label": "Patients" });
  const detail = h("div", { class: "detail", "aria-live": "polite" });

  const listPanel = h(
    "section",
    { class: "panel glass plist-panel", "aria-labelledby": "patients-list-title" },
    h("header", { class: "panel__head" }, h("h2", { id: "patients-list-title", text: "Patients" })),
    h("div", { class: "search" }, icon("search", 16), search),
    addForm,
    list,
    h("p", { class: "field__help", text: "Use pseudonymous codes. Records are stored unencrypted on the server." }),
  );
  const detailPanel = h("section", { class: "panel glass detail-panel", "aria-label": "Patient history" }, detail);

  function renderList() {
    clear(list);
    const q = query.trim().toLowerCase();
    const rows = store.patients.filter((p) => !q || p.name.toLowerCase().includes(q));
    if (!store.loaded) {
      for (let i = 0; i < 4; i++) list.append(h("li", { class: "skeleton skeleton--row" }));
      return;
    }
    if (!rows.length) {
      list.append(h("li", { class: "plist__empty muted", text: store.patients.length ? "No patients match your search." : "No patients yet. Add one above." }));
      return;
    }
    for (const p of rows) {
      const current = p.id === selectedId;
      list.append(
        h(
          "li",
          {},
          h(
            "button",
            { class: "pitem", type: "button", "aria-current": current ? "true" : null, onclick: () => select(p.id) },
            h("span", { class: "avatar", "aria-hidden": "true", text: initials(p.name) || "?" }),
            h("span", { class: "pitem__name", text: p.name }),
            icon("down", 14, "pitem__chev"),
          ),
        ),
      );
    }
  }

  function renderPlaceholder() {
    clear(detail).append(
      h("div", { class: "empty" }, h("span", { class: "empty__icon" }, icon("users", 30)), h("h3", { text: "Select a patient" }), h("p", { class: "muted", text: "Their saved scans appear here as a healing timeline with an area trend." })),
    );
  }

  async function select(id) {
    selectedId = id;
    store.select(id);
    renderList();
    const patient = store.patients.find((p) => p.id === id);
    if (!patient) return renderPlaceholder();
    const token = ++loadToken;

    clear(detail).append(h("div", { class: "skeleton skeleton--block" }), h("div", { class: "skeleton skeleton--block" }));
    let scans;
    try {
      scans = await api.patientScans(id);
    } catch (err) {
      if (token === loadToken) {
        clear(detail).append(h("div", { class: "empty" }, h("span", { class: "empty__icon" }, icon("alert", 30)), h("h3", { text: "Could not load history" }), h("p", { class: "muted", text: err.message })));
      }
      return;
    }
    if (token !== loadToken) return; // a newer selection superseded this one
    renderDetail(patient, scans);
  }

  function renderDetail(patient, scans) {
    const head = h(
      "header",
      { class: "detail__head" },
      h("span", { class: "avatar avatar--lg", "aria-hidden": "true", text: initials(patient.name) || "?" }),
      h("div", {}, h("h2", { text: patient.name }), h("p", { class: "muted", text: `${scans.length} saved scan${scans.length === 1 ? "" : "s"}` })),
      h(
        "button",
        {
          class: "btn btn--primary btn--sm detail__cta",
          type: "button",
          onclick: () => {
            store.select(patient.id);
            navigate("analyze");
          },
        },
        icon("scan", 16),
        "New scan",
      ),
    );

    if (!scans.length) {
      clear(detail).append(head, h("div", { class: "empty" }, h("span", { class: "empty__icon" }, icon("image", 30)), h("h3", { text: "No scans yet" }), h("p", { class: "muted", text: "Run an analysis with this patient selected and “Save scan to history” on." })));
      return;
    }

    const first = scans[0];
    const last = scans[scans.length - 1];
    const total = last.area_cm2 - first.area_cm2;
    const dir = scans.length < 2 ? "flat" : total < -0.05 ? "down" : total > 0.05 ? "up" : "flat";

    const latestEl = h("span", { class: "metric__value mono" });
    countUp(latestEl, last.area_cm2, { digits: 2 });
    const totalEl = h("span", { class: "metric__value mono" });
    countUp(totalEl, Math.abs(total), { digits: 2 });

    const stats = h(
      "div",
      { class: "metrics metrics--3" },
      h("div", { class: "metric glass" }, h("div", { class: "metric__head" }, icon("ruler", 16), h("span", { text: "Latest area" })), h("div", { class: "metric__body" }, latestEl, h("span", { class: "metric__unit", text: "cm²" }))),
      h("div", { class: "metric glass" }, h("div", { class: "metric__head" }, icon("pulse", 16), h("span", { text: "Latest severity" })), h("div", { class: "metric__body metric__body--badge" }, severityBadge(last.severity))),
      h(
        "div",
        { class: `metric glass metric--delta metric--${dir}` },
        h("div", { class: "metric__head" }, icon(dir, 16), h("span", { text: "Since first scan" })),
        h("div", { class: "metric__body" }, h("span", { class: "metric__sign mono", text: dir === "up" ? "+" : dir === "down" ? "−" : "" }), totalEl, h("span", { class: "metric__unit", text: "cm²" })),
      ),
    );

    const timeline = h("ol", { class: "timeline", "aria-label": "Scan timeline, newest first" });
    [...scans].reverse().forEach((scan, idx, arr) => {
      const prev = arr[idx + 1];
      const thumb = h("img", { class: "tl__thumb", alt: "", hidden: true });
      const tone = { Mild: "ok", Moderate: "warn", Severe: "danger" }[scan.severity] || "info";
      scanImageUrl(scan.id, "overlay")
        .then((url) => {
          thumb.src = url;
          thumb.hidden = false;
          thumb.alt = `Segmentation overlay from ${fmtDate(scan.created_at)}`;
        })
        .catch(() => {});
      timeline.append(
        h(
          "li",
          { class: "tl__item" },
          h("span", { class: `tl__dot tl__dot--${tone}`, "aria-hidden": "true" }),
          h(
            "article",
            { class: "tl__card glass" },
            thumb,
            h(
              "div",
              { class: "tl__main" },
              h("div", { class: "tl__top" }, h("time", { class: "tl__date", datetime: scan.created_at, text: fmtDate(scan.created_at) }), idx === 0 ? h("span", { class: "tag tag--accent", text: "Latest" }) : null),
              h("div", { class: "badges" }, statusBadge(scan.status), scan.status === "ULCER DETECTED" ? severityBadge(scan.severity) : null),
              h("div", { class: "tl__stats" }, h("span", { class: "mono tl__area" }, fmtNum(scan.area_cm2), h("small", { text: " cm²" })), delta(prev?.area_cm2, scan.area_cm2)),
            ),
            h(
              "button",
              {
                class: "btn btn--ghost btn--sm",
                type: "button",
                "aria-label": `Download PDF report for ${fmtDate(scan.created_at)}`,
                onclick: async (e) => {
                  const btn = e.currentTarget;
                  btn.disabled = true;
                  try {
                    await downloadReport(scan.id, patient.name);
                  } catch (err) {
                    toast("error", "Could not download the report", err.message);
                  } finally {
                    btn.disabled = false;
                  }
                },
              },
              icon("file", 16),
              "PDF",
            ),
          ),
        ),
      );
    });

    clear(detail).append(
      head,
      stats,
      scans.length > 1
        ? h("div", { class: "chart-card" }, h("h3", { class: "subhead", text: "Wound area over time" }), createTrendChart(scans))
        : h("p", { class: "muted chart-note", text: "Add a second scan to see the area trend." }),
      h("h3", { class: "subhead", text: "Timeline" }),
      timeline,
    );
  }

  search.addEventListener("input", () => {
    query = search.value;
    renderList();
  });
  addForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = nameInput.value.trim();
    if (!name) return nameInput.focus();
    addBtn.disabled = true;
    try {
      const patient = await store.addPatient(name);
      nameInput.value = "";
      toast("success", "Patient added", patient.name);
      await select(patient.id);
    } catch (err) {
      toast("error", "Could not add patient", err.message);
    } finally {
      addBtn.disabled = false;
    }
  });
  store.subscribe(() => renderList());

  renderList();
  renderPlaceholder();

  const el = h(
    "div",
    {},
    h("header", { class: "page-head" }, h("h1", {}, "Patient ", h("span", { class: "grad", text: "history" })), h("p", { class: "muted", text: "Follow healing across visits: area trend, severity and per-visit reports." })),
    h("div", { class: "split" }, listPanel, detailPanel),
  );

  return {
    el,
    title: "Patients",
    async onShow() {
      try {
        await store.refreshPatients();
      } catch (err) {
        toast("error", "Could not load patients", err.message);
        return;
      }
      const wanted = store.selectedPatientId;
      if (wanted && wanted !== selectedId && store.patients.some((p) => p.id === wanted)) await select(wanted);
      else if (selectedId && store.patients.some((p) => p.id === selectedId)) await select(selectedId); // refresh history
      renderList();
    },
  };
}
