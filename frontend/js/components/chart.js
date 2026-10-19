/* Dependency-free SVG area-trend chart for a patient's scan history. */

import { fmtDate, fmtNum, h, nextId, svgEl } from "../dom.js";

const W = 640;
const H = 220;
const PAD = { l: 46, r: 18, t: 16, b: 34 };

/** @param {{created_at: string, area_cm2: number, severity: string}[]} scans oldest -> newest */
export function createTrendChart(scans) {
  const gradId = nextId("grad");
  const times = scans.map((s) => new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s.created_at) ? s.created_at : `${s.created_at}Z`).getTime());
  const areas = scans.map((s) => s.area_cm2);
  const maxA = Math.max(...areas, 0.5) * 1.15;
  const t0 = Math.min(...times);
  const t1 = Math.max(...times);
  const x = (i) => (scans.length === 1 || t1 === t0 ? (PAD.l + (W - PAD.r)) / 2 : PAD.l + ((times[i] - t0) / (t1 - t0)) * (W - PAD.l - PAD.r));
  const y = (a) => PAD.t + (1 - a / maxA) * (H - PAD.t - PAD.b);

  const svg = svgEl("svg", { class: "chart__svg", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-labelledby": "" });
  const titleId = nextId("chart-title");
  svg.setAttribute("aria-labelledby", titleId);
  svg.append(
    svgEl("title", { id: titleId }, `Wound area over time: ${scans.length} scans, from ${fmtNum(areas[0])} to ${fmtNum(areas[areas.length - 1])} square centimetres`),
    svgEl(
      "defs",
      {},
      svgEl("linearGradient", { id: gradId, x1: 0, y1: 0, x2: 0, y2: 1 }, svgEl("stop", { offset: "0%", "stop-color": "var(--accent)", "stop-opacity": 0.45 }), svgEl("stop", { offset: "100%", "stop-color": "var(--accent)", "stop-opacity": 0 })),
    ),
  );

  // Horizontal grid + y labels
  for (let i = 0; i <= 3; i++) {
    const val = (maxA / 3) * i;
    const yy = y(val);
    svg.append(
      svgEl("line", { class: "chart__grid", x1: PAD.l, x2: W - PAD.r, y1: yy, y2: yy }),
      svgEl("text", { class: "chart__label", x: PAD.l - 8, y: yy + 4, "text-anchor": "end" }, fmtNum(val, 1)),
    );
  }
  svg.append(svgEl("text", { class: "chart__label chart__label--axis", x: 10, y: 12 }, "cm²"));

  const pts = scans.map((_, i) => [x(i), y(areas[i])]);
  if (pts.length > 1) {
    const line = pts.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)} ${py.toFixed(1)}`).join(" ");
    const area = `${line} L${pts[pts.length - 1][0].toFixed(1)} ${y(0)} L${pts[0][0].toFixed(1)} ${y(0)} Z`;
    svg.append(svgEl("path", { class: "chart__area", d: area, fill: `url(#${gradId})` }), svgEl("path", { class: "chart__line", d: line, pathLength: 1 }));
  }
  const tone = { Mild: "ok", Moderate: "warn", Severe: "danger" };
  const tip = h("div", { class: "chart__tip", hidden: true, role: "status" });
  pts.forEach(([px, py], i) => {
    const dot = svgEl("circle", { class: `chart__dot chart__dot--${tone[scans[i].severity] || "info"}`, cx: px, cy: py, r: 5.5, tabindex: 0, "aria-label": `${fmtDate(scans[i].created_at)}: ${fmtNum(areas[i])} square centimetres, ${scans[i].severity} severity` });
    const show = () => {
      tip.hidden = false;
      tip.textContent = `${fmtDate(scans[i].created_at)} · ${fmtNum(areas[i])} cm² · ${scans[i].severity}`;
      tip.dataset.side = px > W * 0.6 ? "left" : "right";
      tip.style.left = `${(px / W) * 100}%`;
      tip.style.top = `${(py / H) * 100}%`;
    };
    dot.addEventListener("pointerenter", show);
    dot.addEventListener("focus", show);
    dot.addEventListener("pointerleave", () => (tip.hidden = true));
    dot.addEventListener("blur", () => (tip.hidden = true));
    svg.append(dot);
  });

  // x labels: first and last date
  const dateOpts = { month: "short", day: "numeric" };
  svg.append(svgEl("text", { class: "chart__label", x: PAD.l, y: H - 10 }, fmtDate(scans[0].created_at, dateOpts)));
  if (scans.length > 1) svg.append(svgEl("text", { class: "chart__label", x: W - PAD.r, y: H - 10, "text-anchor": "end" }, fmtDate(scans[scans.length - 1].created_at, dateOpts)));

  return h("div", { class: "chart" }, svg, tip);
}
