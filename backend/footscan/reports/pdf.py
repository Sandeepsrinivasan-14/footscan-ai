import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import cv2
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from footscan.analysis.result import AnalysisResult
from footscan.config import settings


def _clean(text: object) -> str:
    if text is None:
        return ""
    return str(text).encode("latin-1", "replace").decode("latin-1")


def generate_pdf_report(result: AnalysisResult, patient_name: str | None) -> Path:
    """Render a one-page clinical summary PDF for a single analysis and return its path."""
    name = _clean((patient_name or "").strip() or "Unknown_Patient")

    with tempfile.TemporaryDirectory() as tmp:
        orig_path = Path(tmp) / "orig.jpg"
        blend_path = Path(tmp) / "blend.jpg"
        cv2.imwrite(str(orig_path), cv2.cvtColor(result.original, cv2.COLOR_RGB2BGR))
        cv2.imwrite(str(blend_path), cv2.cvtColor(result.blended, cv2.COLOR_RGB2BGR))

        pdf = FPDF()
        pdf.add_page()

        NEXT_LINE = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}
        SAME_LINE = {"new_x": XPos.RIGHT, "new_y": YPos.TOP}

        pdf.set_font("Helvetica", "B", 20)
        pdf.set_text_color(220, 50, 50)
        pdf.cell(0, 10, _clean("FootScan AI - Clinical Analysis Report"), 0, align="C", **NEXT_LINE)
        pdf.ln(5)

        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(100, 8, _clean(f"Patient Name: {name}"), 0, **SAME_LINE)
        pdf.cell(
            0,
            8,
            _clean(f"Date: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}"),
            0,
            align="R",
            **NEXT_LINE,
        )
        pdf.line(10, pdf.get_y() + 2, 200, pdf.get_y() + 2)
        pdf.ln(10)

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(95, 8, _clean("Original Scan"), 0, align="C", **SAME_LINE)
        pdf.cell(95, 8, _clean("AI Segmentation Result"), 0, align="C", **NEXT_LINE)
        y = pdf.get_y()
        pdf.image(str(orig_path), x=20, y=y, w=80)
        pdf.image(str(blend_path), x=110, y=y, w=80)
        pdf.ln(85)

        pdf.set_fill_color(240, 240, 240)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, _clean("Detection Metrics"), 0, align="L", fill=True, **NEXT_LINE)
        pdf.ln(2)

        rows = [
            ("Status", result.status),
            ("Ulcer Area (cm2)", f"{result.area_cm2:.4f}"),
            ("Wound Shape", result.shape),
            ("Tissue Color", result.color_profile),
            ("SINBAD Score", f"{result.sinbad_score}/6 - {result.severity}"),
            ("Max Confidence", f"{result.max_confidence:.3f}"),
            ("Est. Healing Days", str(result.est_healing_days)),
        ]
        for label, val in rows:
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(60, 10, _clean(label), 1, **SAME_LINE)
            pdf.set_font("Helvetica", "", 12)
            pdf.cell(130, 10, _clean(val), 1, **NEXT_LINE)

        pdf.ln(8)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, _clean("Treatment Recommendations"), 0, align="L", fill=True, **NEXT_LINE)
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 12)
        pdf.multi_cell(0, 8, _clean(result.treatment), border=1)

        pdf.ln(10)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(150, 150, 150)
        pdf.multi_cell(
            0,
            5,
            _clean(
                "Generated automatically by FootScan AI. This report is a heuristic decision-support "
                "aid and has not been clinically validated or FDA cleared. It does not replace "
                "professional medical judgment."
            ),
        )

        settings.reports_dir.mkdir(parents=True, exist_ok=True)
        # The patient name is untrusted input: never let it shape a filesystem path
        # (it could contain "../", path separators or reserved characters).
        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:40] or "patient"
        out_path = settings.reports_dir / f"FootScan_Report_{safe_name}_{datetime.now(UTC):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:8]}.pdf"
        pdf.output(str(out_path))
        return out_path
