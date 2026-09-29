"""Gradio dashboard for FootScan AI.

Runs in-process against the same service layer as the REST API and is
mounted onto the FastAPI app (see footscan.api.main). Per-request state
(the last analysis result) is held in gr.State rather than module-level
globals -- the original prototype used shared globals, which leaked one
user's analysis into every other concurrent user's PDF export.
"""

import logging

import gradio as gr
import matplotlib.pyplot as plt
import pandas as pd

from footscan.analysis.result import AnalysisResult
from footscan.config import settings
from footscan.db.session import SessionLocal
from footscan.ml.model import ModelLoadError
from footscan.reports.pdf import generate_pdf_report
from footscan.service import analyze_image, compare_images, get_or_create_patient, persist_scan

logger = logging.getLogger(__name__)


def process_single(image, ref_cm, ref_px, threshold, prep_method, view_type, patient_name):
    if image is None:
        return [None] * 13 + [None]

    try:
        result = analyze_image(
            image,
            ref_cm=ref_cm,
            ref_px=ref_px,
            threshold=threshold,
            prep_method=prep_method,
            view_type=view_type,
        )
    except ModelLoadError as exc:
        gr.Warning(f"Model unavailable: {exc}")
        return [None] * 13 + [None]

    if patient_name and patient_name.strip():
        db = SessionLocal()
        try:
            patient = get_or_create_patient(db, patient_name)
            persist_scan(db, result, patient_id=patient.id)
        except Exception:
            logger.exception("Failed to persist scan from Gradio UI")
        finally:
            db.close()

    return (
        result.original,
        result.mask,
        result.heatmap,
        result.blended,
        result.edges,
        result.cropped,
        result.status,
        f"{result.area_cm2:.4f}",
        result.shape,
        result.color_profile,
        f"{result.sinbad_score}/6 ({result.severity})",
        f"~{result.est_healing_days} Days",
        result.treatment,
        result,  # -> gr.State
    )


def export_report(patient_name: str, result: AnalysisResult | None):
    if result is None:
        gr.Warning("Run an analysis first.")
        return None
    path = generate_pdf_report(result, patient_name)
    return str(path)


def compare_scans(old_img, new_img, ref_cm, ref_px, threshold):
    if old_img is None or new_img is None:
        return None, "Please upload both images."
    try:
        result = compare_images(old_img, new_img, ref_cm=ref_cm, ref_px=ref_px, threshold=threshold)
    except ModelLoadError as exc:
        gr.Warning(f"Model unavailable: {exc}")
        return None, "Model unavailable."

    text = (
        f"Status: {result['status']}\n"
        f"Old Area: {result['old_area_cm2']:.2f} cm²\n"
        f"New Area: {result['new_area_cm2']:.2f} cm²\n"
        f"Change: {result['change_cm2']:+.2f} cm²"
    )
    return result["diff_map"], text


def add_to_history(img, patient_name, threshold, ref_cm, ref_px, view_type):
    if img is None or not patient_name or not patient_name.strip():
        gr.Warning("Provide both an image and a patient name.")
        return [], None

    try:
        result = analyze_image(
            img, ref_cm=ref_cm, ref_px=ref_px, threshold=threshold, prep_method="None", view_type=view_type
        )
    except ModelLoadError as exc:
        gr.Warning(f"Model unavailable: {exc}")
        return [], None

    db = SessionLocal()
    try:
        patient = get_or_create_patient(db, patient_name)
        persist_scan(db, result, patient_id=patient.id)
        rows = [
            {"Date": s.created_at.strftime("%Y-%m-%d %H:%M"), "Area_cm2": round(s.area_cm2, 4)}
            for s in sorted(patient.scans, key=lambda s: s.created_at)
        ]
    finally:
        db.close()

    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(df["Date"], df["Area_cm2"], "bo-", linewidth=2)
    ax.set_ylabel("Area (cm²)")
    ax.set_title(f"Healing Trajectory - {patient_name}")
    ax.tick_params(axis="x", rotation=30)
    ax.grid(True)
    fig.tight_layout()
    return df.values.tolist(), fig


CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --fs-bg-0: #0a0e1a;
    --fs-bg-1: #10162b;
    --fs-bg-2: #151d36;
    --fs-glass: rgba(255, 255, 255, 0.045);
    --fs-glass-border: rgba(255, 255, 255, 0.09);
    --fs-glass-strong: rgba(255, 255, 255, 0.07);
    --fs-text: #e7eaf3;
    --fs-text-dim: #8b93ab;
    --fs-text-faint: #5b6380;
    --fs-accent: #6d8bff;
    --fs-accent-2: #38d9c9;
    --fs-accent-grad: linear-gradient(135deg, #6d8bff 0%, #8f6dff 55%, #38d9c9 120%);
    --fs-danger: #ff6b7a;
    --fs-ok: #38d9c9;
    --fs-radius: 18px;
    --fs-radius-sm: 12px;
    --fs-shadow-deep: 0 24px 60px -20px rgba(0, 0, 0, 0.65), 0 2px 8px rgba(0, 0, 0, 0.35);
    --fs-shadow-soft: 0 10px 30px -12px rgba(0, 0, 0, 0.5);
}

* { box-sizing: border-box; }

html { background-color: var(--fs-bg-0) !important; }
body, .gradio-container {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    color: var(--fs-text) !important;
    background-color: var(--fs-bg-0) !important;
    background-image: radial-gradient(1100px 600px at 12% -10%, rgba(109, 139, 255, 0.16), transparent 60%), radial-gradient(900px 500px at 105% 10%, rgba(56, 217, 201, 0.12), transparent 55%), radial-gradient(800px 500px at 50% 120%, rgba(143, 109, 255, 0.10), transparent 55%), linear-gradient(180deg, var(--fs-bg-0) 0%, var(--fs-bg-1) 45%, var(--fs-bg-2) 100%) !important;
    background-attachment: fixed !important;
    background-repeat: no-repeat !important;
    min-height: 100vh;
}

::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.14);
    border-radius: 10px;
    border: 2px solid transparent;
    background-clip: padding-box;
}
::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.22); background-clip: padding-box; }

/* ---------- Header ---------- */
.fs-hero {
    text-align: center;
    padding: 40px 24px 28px;
    margin-bottom: 8px;
}
.fs-hero h1 {
    font-size: 2.35em;
    font-weight: 800;
    letter-spacing: -0.02em;
    margin: 0 0 6px;
    background: var(--fs-accent-grad);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    filter: drop-shadow(0 4px 24px rgba(109, 139, 255, 0.25));
}
.fs-hero .fs-subtitle {
    color: var(--fs-text-dim);
    font-weight: 600;
    font-size: 0.78em;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    margin: 0;
}
.fs-hero .fs-disclaimer {
    color: var(--fs-text-faint);
    font-size: 0.82em;
    max-width: 640px;
    line-height: 1.55;
    margin: 14px auto 0;
    padding: 10px 18px;
    border: 1px solid var(--fs-glass-border);
    border-radius: 999px;
    background: var(--fs-glass);
    backdrop-filter: blur(12px);
}

/* ---------- Glass surfaces (panels, blocks, groups) ---------- */
.gradio-container .block,
.gradio-container .form,
.gradio-container fieldset,
.gradio-container .panel,
.gradio-container .column.panel,
.tabitem {
    background: var(--fs-glass) !important;
    border: 1px solid var(--fs-glass-border) !important;
    border-radius: var(--fs-radius) !important;
    backdrop-filter: blur(18px) saturate(140%);
    -webkit-backdrop-filter: blur(18px) saturate(140%);
    box-shadow: var(--fs-shadow-soft);
    transition: border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease;
}

.gradio-container label span,
.gradio-container label {
    color: var(--fs-text-dim) !important;
    font-weight: 600 !important;
    font-size: 0.86em !important;
    letter-spacing: 0.01em;
}

/* ---------- Tabs ---------- */
.tab-nav, [role="tablist"] {
    background: var(--fs-glass) !important;
    border: 1px solid var(--fs-glass-border) !important;
    border-radius: 999px !important;
    padding: 6px !important;
    backdrop-filter: blur(16px);
    gap: 4px;
    box-shadow: var(--fs-shadow-soft);
}
.tab-nav button, [role="tab"] {
    border: none !important;
    border-radius: 999px !important;
    color: var(--fs-text-dim) !important;
    font-weight: 600 !important;
    background: transparent !important;
    transition: all 200ms ease !important;
}
.tab-nav button.selected, [role="tab"][aria-selected="true"] {
    background: var(--fs-accent-grad) !important;
    color: #0a0e1a !important;
    box-shadow: 0 6px 20px -6px rgba(109, 139, 255, 0.55);
}

/* ---------- Buttons ---------- */
button.primary, .gradio-container button.primary {
    background: var(--fs-accent-grad) !important;
    border: none !important;
    color: #0a0e1a !important;
    font-weight: 700 !important;
    letter-spacing: 0.01em;
    border-radius: var(--fs-radius-sm) !important;
    box-shadow: 0 10px 30px -10px rgba(109, 139, 255, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.35);
    transition: transform 160ms ease, box-shadow 160ms ease !important;
}
button.primary:hover {
    transform: translateY(-2px);
    box-shadow: 0 16px 36px -8px rgba(109, 139, 255, 0.65), inset 0 1px 0 rgba(255, 255, 255, 0.4);
}
button.primary:active { transform: translateY(0) scale(0.98); }

button.secondary, .gradio-container button:not(.primary) {
    background: var(--fs-glass-strong) !important;
    border: 1px solid var(--fs-glass-border) !important;
    color: var(--fs-text) !important;
    border-radius: var(--fs-radius-sm) !important;
    font-weight: 600 !important;
    transition: transform 160ms ease, border-color 160ms ease !important;
}
button.secondary:hover, .gradio-container button:not(.primary):hover {
    border-color: rgba(109, 139, 255, 0.45) !important;
    transform: translateY(-1px);
}

/* ---------- Inputs ---------- */
input[type="text"], input[type="number"], textarea, select,
.gradio-container input, .gradio-container textarea {
    background: rgba(255, 255, 255, 0.035) !important;
    border: 1px solid var(--fs-glass-border) !important;
    border-radius: var(--fs-radius-sm) !important;
    color: var(--fs-text) !important;
    transition: border-color 160ms ease, box-shadow 160ms ease !important;
}
input:focus, textarea:focus, select:focus {
    border-color: var(--fs-accent) !important;
    box-shadow: 0 0 0 3px rgba(109, 139, 255, 0.18) !important;
    outline: none !important;
}
input:disabled, textarea:disabled {
    opacity: 0.55 !important;
    -webkit-text-fill-color: var(--fs-text-dim) !important;
    color: var(--fs-text-dim) !important;
}

/* ---------- Slider ---------- */
input[type="range"] { accent-color: var(--fs-accent) !important; }

/* ---------- Section headings inside panels ---------- */
.gradio-container h3 {
    color: var(--fs-text) !important;
    font-weight: 700 !important;
    font-size: 0.95em !important;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    opacity: 0.85;
    border-bottom: none !important;
    margin: 4px 0 10px !important;
}

/* ---------- Upload / image widget inner wrappers (override gradio's opaque white) ---------- */
[data-testid="image"], .upload-container, .image-frame {
    background: transparent !important;
}
[data-testid="image"] *, .upload-container * {
    background-color: transparent !important;
}
[data-testid="image"] button, .upload-container button {
    background: var(--fs-glass-strong) !important;
}

/* ---------- Image / plot panels: subtle 3D hover lift ---------- */
.gradio-container .image-container,
.gradio-container [data-testid="image"] {
    border-radius: var(--fs-radius-sm) !important;
    overflow: hidden;
    border: 1px solid var(--fs-glass-border) !important;
    transition: transform 220ms cubic-bezier(.2,.8,.2,1), box-shadow 220ms ease, border-color 220ms ease;
    transform-style: preserve-3d;
}
.gradio-container .image-container:hover,
.gradio-container [data-testid="image"]:hover {
    transform: translateY(-4px) scale(1.012);
    box-shadow: var(--fs-shadow-deep);
    border-color: rgba(109, 139, 255, 0.35) !important;
}

/* ---------- Accordion ---------- */
.gradio-container .accordion, .gradio-container details {
    background: var(--fs-glass) !important;
    border: 1px solid var(--fs-glass-border) !important;
    border-radius: var(--fs-radius-sm) !important;
}

/* ---------- Dataframe / table ---------- */
.gradio-container table {
    border-radius: var(--fs-radius-sm) !important;
    overflow: hidden;
}
.gradio-container thead th {
    background: rgba(109, 139, 255, 0.12) !important;
    color: var(--fs-text) !important;
    font-weight: 700 !important;
}

/* ---------- Footer ---------- */
footer { opacity: 0.35 !important; }
"""


def build_demo() -> gr.Blocks:
    with gr.Blocks(title=settings.app_name) as demo:
        gr.HTML(
            f"""
            <div class="fs-hero">
              <h1>{settings.app_name}</h1>
              <p class="fs-subtitle">Advanced Analytics for Diabetic Foot Ulcers</p>
              <p class="fs-disclaimer">
                Research and demonstration tool only. Severity scoring and treatment text are
                heuristic and have not been clinically validated or FDA cleared. Do not use for
                real diagnosis.
              </p>
            </div>
            """
        )

        result_state = gr.State(value=None)

        with gr.Tabs():
            with gr.TabItem("Advanced Analysis"):
                with gr.Row():
                    with gr.Column(scale=1, variant="panel"):
                        input_image = gr.Image(label="Upload Foot Scan", type="numpy")
                        patient_name = gr.Textbox(label="Patient Name", placeholder="e.g. John Doe")

                        with gr.Accordion("Settings & Calibration", open=False):
                            view_type = gr.Radio(
                                ["Plantar (Bottom)", "Dorsal (Top)"], value="Plantar (Bottom)", label="View Type"
                            )
                            prep_method = gr.Dropdown(
                                ["None", "CLAHE", "Histogram Equalization"], value="None", label="Image Preprocessing"
                            )
                            conf_threshold = gr.Slider(0.1, 0.9, value=0.5, step=0.05, label="Detection Sensitivity")
                            ref_cm = gr.Number(label="Reference Marker (cm)", value=1.0)
                            ref_px = gr.Number(label="Reference Marker (pixels)", value=38.46)

                        analyze_btn = gr.Button("Run Full Analysis", variant="primary")
                        gr.Markdown("---")
                        gr.Markdown("### Clinical Report")
                        export_btn = gr.Button("Download PDF Report")
                        export_file = gr.File(label="Generated PDF")

                    with gr.Column(scale=3):
                        with gr.Row():
                            result_status = gr.Textbox(label="Overall Status")
                            area_out = gr.Textbox(label="Area (cm²)")
                            sinbad_out = gr.Textbox(label="SINBAD Score")
                        with gr.Row():
                            shape_out = gr.Textbox(label="Wound Shape")
                            color_out = gr.Textbox(label="Tissue Color Profile")
                            heal_out = gr.Textbox(label="Est. Healing Time")

                        treatment_out = gr.Textbox(label="Treatment Recommendation", lines=2)

                        gr.Markdown("### Detection Visualizations")
                        with gr.Row():
                            out_orig = gr.Image(label="Original", height=250)
                            out_mask = gr.Image(label="Binary Mask", height=250)
                            out_heat = gr.Image(label="Heatmap", height=250)
                        with gr.Row():
                            out_blend = gr.Image(label="Blended Overlay", height=250)
                            out_edge = gr.Image(label="Edge Detection", height=250)
                            out_crop = gr.Image(label="Auto-Zoom ROI", height=250)

                analyze_btn.click(
                    process_single,
                    [input_image, ref_cm, ref_px, conf_threshold, prep_method, view_type, patient_name],
                    [
                        out_orig, out_mask, out_heat, out_blend, out_edge, out_crop,
                        result_status, area_out, shape_out, color_out,
                        sinbad_out, heal_out, treatment_out, result_state,
                    ],
                )
                export_btn.click(export_report, [patient_name, result_state], [export_file])

            with gr.TabItem("Before & After"):
                gr.Markdown(
                    "Compare two scans to track healing progress. "
                    "**Blue** = Healed Tissue, **Red** = New/Worsened Ulcer"
                )
                with gr.Row():
                    old_img = gr.Image(label="Old Scan (T1)", type="numpy")
                    new_img = gr.Image(label="New Scan (T2)", type="numpy")
                compare_btn = gr.Button("Compare Scans", variant="primary")
                with gr.Row():
                    diff_img = gr.Image(label="Difference Map", height=300)
                    diff_text = gr.Textbox(label="Comparison Metrics", lines=4)
                compare_btn.click(compare_scans, [old_img, new_img, ref_cm, ref_px, conf_threshold], [diff_img, diff_text])

            with gr.TabItem("Healing Tracker"):
                gr.Markdown("History is persisted per patient name in the database (survives restarts).")
                with gr.Row():
                    track_img = gr.Image(label="New Visit Scan", type="numpy")
                    track_name = gr.Textbox(label="Patient Name")
                    add_btn = gr.Button("Add to History")

                history_table = gr.Dataframe(label="Patient History", headers=["Date", "Area (cm²)"])
                history_plot = gr.Plot(label="Healing Curve")

                add_btn.click(
                    add_to_history,
                    [track_img, track_name, conf_threshold, ref_cm, ref_px, view_type],
                    [history_table, history_plot],
                )

    return demo
