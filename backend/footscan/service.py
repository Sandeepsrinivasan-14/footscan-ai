import logging
import uuid

import cv2
import numpy as np
from sqlalchemy.orm import Session

from footscan.analysis.color import analyze_color
from footscan.analysis.result import AnalysisResult
from footscan.analysis.scoring import (
    calculate_sinbad_score,
    generate_treatment_recommendation,
    predict_healing_days,
)
from footscan.analysis.shape import analyze_shape, auto_crop_wound, extract_edges
from footscan.config import settings
from footscan.db.models import Patient, ScanRecord
from footscan.ml.model import run_inference
from footscan.ml.preprocessing import to_rgb

logger = logging.getLogger(__name__)

DEFAULT_PX_PER_CM = 38.46  # fallback calibration if no reference marker is supplied


def _pixel_to_cm(ref_cm: float, ref_px: float) -> float:
    if ref_px and ref_px > 0:
        return ref_cm / ref_px
    return 1.0 / DEFAULT_PX_PER_CM


def analyze_image(
    image: np.ndarray,
    *,
    ref_cm: float = 1.0,
    ref_px: float = DEFAULT_PX_PER_CM,
    threshold: float = 0.5,
    prep_method: str = "None",
    view_type: str = "Plantar (Bottom)",
) -> AnalysisResult:
    """Run the full segmentation + measurement + scoring pipeline on one image."""
    image = to_rgb(image)
    size = settings.image_size
    original = cv2.resize(image, (size, size))

    confidence, _ = run_inference(original, prep_method)
    binary_mask = (confidence >= threshold).astype(np.uint8)

    ulcer_pixels = int(np.sum(binary_mask))
    ulcer_percent = (ulcer_pixels / (size * size)) * 100
    pixel_to_cm = _pixel_to_cm(ref_cm, ref_px)
    area_cm2 = ulcer_pixels * (pixel_to_cm**2)

    shape = analyze_shape(binary_mask)
    color = analyze_color(original, binary_mask)
    sinbad_score, severity = calculate_sinbad_score(area_cm2)
    treatment = generate_treatment_recommendation(area_cm2, color, severity)
    healing_days = predict_healing_days(area_cm2)

    mask_viz = binary_mask * 255
    heatmap = cv2.applyColorMap((confidence * 255).astype(np.uint8), cv2.COLORMAP_JET)
    overlay = original.copy()
    overlay[binary_mask == 1] = [0, 255, 0]
    blended = cv2.addWeighted(original, 0.6, overlay, 0.4, 0)
    edges = extract_edges(binary_mask, original)
    cropped = auto_crop_wound(original, binary_mask)

    status = "ULCER DETECTED" if ulcer_percent > 0 else "HEALTHY"

    return AnalysisResult(
        status=status,
        view_type=view_type,
        area_cm2=area_cm2,
        ulcer_percent=ulcer_percent,
        max_confidence=float(confidence.max()),
        shape=shape,
        color_profile=color,
        sinbad_score=sinbad_score,
        severity=severity,
        est_healing_days=healing_days,
        treatment=treatment,
        threshold=threshold,
        preprocessing=prep_method,
        original=original,
        mask=mask_viz,
        heatmap=heatmap,
        blended=blended,
        edges=edges,
        cropped=cropped,
    )


def compare_images(
    old_image: np.ndarray,
    new_image: np.ndarray,
    *,
    ref_cm: float = 1.0,
    ref_px: float = DEFAULT_PX_PER_CM,
    threshold: float = 0.5,
) -> dict:
    size = settings.image_size
    pixel_to_cm = _pixel_to_cm(ref_cm, ref_px)

    def _measure(img: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
        img = cv2.resize(to_rgb(img), (size, size))
        conf, _ = run_inference(img, "None")
        mask = (conf >= threshold).astype(np.uint8)
        cm2 = float(np.sum(mask)) * (pixel_to_cm**2)
        return mask, cm2, img

    old_mask, old_area, _ = _measure(old_image)
    new_mask, new_area, new_res = _measure(new_image)
    diff_area = new_area - old_area

    if diff_area > 0.1:
        status = "WORSENED"
    elif diff_area < -0.1:
        status = "IMPROVED"
    else:
        status = "STABLE"

    diff_map = new_res.copy()
    diff_map[(old_mask == 1) & (new_mask == 0)] = [0, 0, 255]  # healed
    diff_map[(old_mask == 0) & (new_mask == 1)] = [255, 0, 0]  # new/worsened

    return {
        "status": status,
        "old_area_cm2": round(old_area, 4),
        "new_area_cm2": round(new_area, 4),
        "change_cm2": round(diff_area, 4),
        "diff_map": diff_map,
    }


def get_or_create_patient(db: Session, name: str) -> Patient:
    """Look up a patient by exact name, creating one if none exists.

    Name-based matching is a convenience for the single-clinician UI flow,
    not a safe identity key for a multi-tenant deployment.
    """
    name = name.strip()
    patient = db.query(Patient).filter(Patient.name == name).one_or_none()
    if patient is None:
        patient = Patient(name=name)
        db.add(patient)
        db.commit()
        db.refresh(patient)
    return patient


def persist_scan(db: Session, result: AnalysisResult, *, patient_id: str | None = None) -> ScanRecord:
    """Save the analysis result and its key images to disk + DB."""
    scan_id = str(uuid.uuid4())
    orig_path = settings.scans_dir / f"{scan_id}_original.jpg"
    overlay_path = settings.scans_dir / f"{scan_id}_overlay.jpg"
    cv2.imwrite(str(orig_path), cv2.cvtColor(result.original, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(overlay_path), cv2.cvtColor(result.blended, cv2.COLOR_RGB2BGR))

    record = ScanRecord(
        id=scan_id,
        patient_id=patient_id,
        view_type=result.view_type,
        threshold=result.threshold,
        preprocessing=result.preprocessing,
        area_cm2=result.area_cm2,
        ulcer_percent=result.ulcer_percent,
        max_confidence=result.max_confidence,
        shape=result.shape,
        color_profile=result.color_profile,
        sinbad_score=result.sinbad_score,
        severity=result.severity,
        est_healing_days=result.est_healing_days,
        treatment=result.treatment,
        original_image_path=str(orig_path.relative_to(settings.data_dir)),
        overlay_image_path=str(overlay_path.relative_to(settings.data_dir)),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info("Persisted scan %s (patient=%s, area=%.3fcm2)", scan_id, patient_id, result.area_cm2)
    return record
