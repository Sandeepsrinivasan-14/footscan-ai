import logging

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from footscan.api.deps import require_api_key
from footscan.api.imaging import encode_image_b64
from footscan.api.schemas import AnalysisImages, AnalysisResponse, CompareResponse
from footscan.config import settings
from footscan.db.models import Patient, ScanRecord
from footscan.db.session import get_db
from footscan.ml.model import ModelLoadError
from footscan.reports.pdf import generate_pdf_report
from footscan.service import analyze_image, compare_images, persist_scan

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["analysis"], dependencies=[Depends(require_api_key)])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15MB
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp"}


async def _decode_upload(file: UploadFile) -> np.ndarray:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported content type: {file.content_type}")

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds 15MB limit")

    buffer = np.frombuffer(raw, dtype=np.uint8)
    image_bgr = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise HTTPException(status_code=400, detail="Could not decode image; is it a valid image file?")
    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze(
    image: UploadFile = File(...),
    ref_cm: float = Form(1.0),
    ref_px: float = Form(38.46),
    threshold: float = Form(0.5, ge=0.0, le=1.0),
    prep_method: str = Form("None"),
    view_type: str = Form("Plantar (Bottom)"),
    patient_id: str | None = Form(None),
    save: bool = Form(True),
    db: Session = Depends(get_db),
) -> AnalysisResponse:
    img = await _decode_upload(image)

    if patient_id is not None and db.get(Patient, patient_id) is None:
        raise HTTPException(status_code=404, detail="patient_id does not reference an existing patient")

    try:
        result = analyze_image(
            img,
            ref_cm=ref_cm,
            ref_px=ref_px,
            threshold=threshold,
            prep_method=prep_method,
            view_type=view_type,
        )
    except ModelLoadError as exc:
        logger.error("Model unavailable during /analyze: %s", exc)
        raise HTTPException(status_code=503, detail="Segmentation model is unavailable") from exc

    scan_id = None
    if save:
        record = persist_scan(db, result, patient_id=patient_id)
        scan_id = record.id

    images = AnalysisImages(
        original=encode_image_b64(result.original),
        mask=encode_image_b64(result.mask),
        heatmap=encode_image_b64(result.heatmap),
        blended=encode_image_b64(result.blended),
        edges=encode_image_b64(result.edges),
        cropped=encode_image_b64(result.cropped),
    )

    return AnalysisResponse(**result.to_dict(), scan_id=scan_id, patient_id=patient_id, images=images)


@router.post("/compare", response_model=CompareResponse)
async def compare(
    old_image: UploadFile = File(...),
    new_image: UploadFile = File(...),
    ref_cm: float = Form(1.0),
    ref_px: float = Form(38.46),
    threshold: float = Form(0.5, ge=0.0, le=1.0),
) -> CompareResponse:
    old_img = await _decode_upload(old_image)
    new_img = await _decode_upload(new_image)

    try:
        result = compare_images(old_img, new_img, ref_cm=ref_cm, ref_px=ref_px, threshold=threshold)
    except ModelLoadError as exc:
        raise HTTPException(status_code=503, detail="Segmentation model is unavailable") from exc

    return CompareResponse(
        status=result["status"],
        old_area_cm2=result["old_area_cm2"],
        new_area_cm2=result["new_area_cm2"],
        change_cm2=result["change_cm2"],
        diff_image=encode_image_b64(result["diff_map"]),
    )


@router.get("/scans/{scan_id}/image/{kind}")
def get_scan_image(scan_id: str, kind: str, db: Session = Depends(get_db)) -> FileResponse:
    if kind not in {"original", "overlay"}:
        raise HTTPException(status_code=404, detail="Unknown image kind")

    scan = db.get(ScanRecord, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")

    rel_path = scan.original_image_path if kind == "original" else scan.overlay_image_path
    if not rel_path:
        raise HTTPException(status_code=404, detail="No stored image of this kind for this scan")

    full_path = settings.data_dir / rel_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Stored image file is missing")

    return FileResponse(full_path, media_type="image/jpeg")


@router.get("/scans/{scan_id}/report")
def download_report(scan_id: str, patient_name: str | None = None, db: Session = Depends(get_db)) -> FileResponse:
    scan = db.get(ScanRecord, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    if not scan.original_image_path or not scan.overlay_image_path:
        raise HTTPException(status_code=422, detail="Scan has no stored images to render a report from")

    orig_path = settings.data_dir / scan.original_image_path
    overlay_path = settings.data_dir / scan.overlay_image_path
    original = cv2.cvtColor(cv2.imread(str(orig_path)), cv2.COLOR_BGR2RGB)
    blended = cv2.cvtColor(cv2.imread(str(overlay_path)), cv2.COLOR_BGR2RGB)

    from footscan.analysis.result import AnalysisResult

    result = AnalysisResult(
        status="ULCER DETECTED" if scan.ulcer_percent > 0 else "HEALTHY",
        view_type=scan.view_type,
        area_cm2=scan.area_cm2,
        ulcer_percent=scan.ulcer_percent,
        max_confidence=scan.max_confidence,
        shape=scan.shape,
        color_profile=scan.color_profile,
        sinbad_score=scan.sinbad_score,
        severity=scan.severity,
        est_healing_days=scan.est_healing_days,
        treatment=scan.treatment,
        threshold=scan.threshold,
        preprocessing=scan.preprocessing,
        original=original,
        mask=original,
        heatmap=original,
        blended=blended,
        edges=original,
        cropped=original,
    )

    name = patient_name or (scan.patient.name if scan.patient else "Unknown_Patient")
    pdf_path = generate_pdf_report(result, name)
    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_path.name)
