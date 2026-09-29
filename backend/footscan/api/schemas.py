from pydantic import BaseModel, ConfigDict, Field


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


class CompareResponse(BaseModel):
    status: str
    old_area_cm2: float
    new_area_cm2: float
    change_cm2: float


class PatientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


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
