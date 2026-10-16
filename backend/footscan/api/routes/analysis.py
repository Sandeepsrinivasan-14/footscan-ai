import logging
from pathlib import Path

import cv2
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from footscan.analysis.result import AnalysisResult
from footscan.api.deps import enforce_rate_limit, require_api_key
from footscan.api.imaging import decode_upload, encode_image_b64
from footscan.api.schemas import AnalysisImages, AnalysisResponse, CompareResponse, PrepMethod, ViewType
from footscan.config import settings
from footscan.db.models import Patient, ScanRecord
from footscan.db.session import get_db
from footscan.ml.model import ModelLoadError
from footscan.reports.pdf import generate_pdf_report
from footscan.service import analyze_image, compare_images, persist_scan

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["analysis"], dependencies=[Depends(require_api_key)])

_UPLOAD_ERRORS = {
    400: {"description": "Not a decodable image"},
    413: {"description": "Upload too large (bytes or pixels)"},
    415: {"description": "Unsupported image format"},
    429: {"description": "Rate limit exceeded"},
    503: {"description": "Segmentation model unavailable"},
}


def _resolve_stored_file(rel_path: str) -> Path:
    """Resolve a DB-stored relative path, refusing anything that escapes the data directory."""
    data_dir = settings.data_dir.resolve()
    full_path = (data_dir / rel_path).resolve()
    if not full_path.is_relative_to(data_dir):
        logger.error("Stored path escapes data dir; refusing to serve it")
        raise HTTPException(status_code=404, detail="Stored image file is missing")
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="Stored image file is missing")
    return full_path


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    responses=_UPLOAD_ERRORS,
    dependencies=[Depends(enforce_rate_limit)],
)
async def analyze(
    image: UploadFile = File(..., description="JPEG/PNG/WEBP/BMP, up to FOOTSCAN_MAX_UPLOAD_BYTES"),
    ref_cm: float = Form(1.0, gt=0, le=1000, description="Real-world length of the reference marker (cm)"),
    ref_px: float = Form(38.46, gt=0, le=100_000, description="Length of the reference marker in pixels"),
    threshold: float = Form(0.5, ge=0.0, le=1.0),
    prep_method: PrepMethod = Form("None"),
    view_type: ViewType = Form("Plantar (Bottom)"),
    patient_id: str | None = Form(None, max_length=36),
    save: bool = Form(True),
    db: Session = Depends(get_db),
) -> AnalysisResponse:
    img = await decode_upload(image)

    if patient_id is not None and db.get(Patient, patient_id) is None:
        raise HTTPException(status_code=404, detail="patient_id does not reference an existing patient")

    try:
        result = await run_in_threadpool(
            analyze_image,
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
        record = await run_in_threadpool(persist_scan, db, result, patient_id=patient_id)
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


@router.post(
    "/compare",
    response_model=CompareResponse,
    responses=_UPLOAD_ERRORS,
    dependencies=[Depends(enforce_rate_limit)],
)
async def compare(
    old_image: UploadFile = File(...),
    new_image: UploadFile = File(...),
    ref_cm: float = Form(1.0, gt=0, le=1000),
    ref_px: float = Form(38.46, gt=0, le=100_000),
    threshold: float = Form(0.5, ge=0.0, le=1.0),
) -> CompareResponse:
    old_img = await decode_upload(old_image)
    new_img = await decode_upload(new_image)

    try:
        result = await run_in_threadpool(
            compare_images, old_img, new_img, ref_cm=ref_cm, ref_px=ref_px, threshold=threshold
        )
    except ModelLoadError as exc:
        logger.error("Model unavailable during /compare: %s", exc)
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

    return FileResponse(_resolve_stored_file(rel_path), media_type="image/jpeg")


def _read_rgb(path: Path):
    bgr = cv2.imread(str(path))
    if bgr is None:
        raise HTTPException(status_code=404, detail="Stored image file is missing or unreadable")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


@router.get("/scans/{scan_id}/report")
def download_report(
    scan_id: str,
    patient_name: str | None = Query(None, max_length=255),
    db: Session = Depends(get_db),
) -> FileResponse:
    scan = db.get(ScanRecord, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    if not scan.original_image_path or not scan.overlay_image_path:
        raise HTTPException(status_code=422, detail="Scan has no stored images to render a report from")

    original = _read_rgb(_resolve_stored_file(scan.original_image_path))
    blended = _read_rgb(_resolve_stored_file(scan.overlay_image_path))

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
    # The PDF contains patient data: serve it once, then delete the rendered copy from disk.
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"footscan_report_{scan_id}.pdf",
        background=BackgroundTask(pdf_path.unlink, missing_ok=True),
    )
