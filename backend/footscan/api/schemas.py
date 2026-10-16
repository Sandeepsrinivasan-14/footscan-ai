from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DISCLAIMER = (
    "Research use only. FootScan AI is not a medical device and has not been clinically validated "
    "or cleared by any regulatory body. Outputs must not be used for diagnosis or treatment decisions."
)

PrepMethod = Literal["None", "CLAHE", "Histogram Equalization"]
ViewType = Literal["Plantar (Bottom)", "Dorsal (Top)"]


class AnalysisImages(BaseModel):
    original: str
    mask: str
    heatmap: str
    blended: str
    edges: str
    cropped: str


class AnalysisResponse(BaseModel):
    status: str
    view_type: str
    area_cm2: float
    ulcer_percent: float
    max_confidence: float
    shape: str
    color_profile: str
    sinbad_score: int
    severity: str
    est_healing_days: int
    treatment: str
    threshold: float
    preprocessing: str
    scan_id: str | None = None
    patient_id: str | None = None
    images: AnalysisImages
    disclaimer: str = DISCLAIMER


class CompareResponse(BaseModel):
    status: str
    old_area_cm2: float
    new_area_cm2: float
    change_cm2: float
    diff_image: str
    disclaimer: str = DISCLAIMER


class PatientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def _strip_and_require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        if any(ord(ch) < 32 for ch in value):
            raise ValueError("name must not contain control characters")
        return value


class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str


class ScanSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: str
    area_cm2: float
    severity: str
    status: str


class HealthResponse(BaseModel):
    status: str
    device: str
    model_loaded: bool


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str]
