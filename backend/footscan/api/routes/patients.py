from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from footscan.api.deps import require_api_key
from footscan.api.schemas import PatientCreate, PatientResponse, ScanSummary
from footscan.db.models import Patient
from footscan.db.session import get_db

router = APIRouter(prefix="/api/patients", tags=["patients"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
def create_patient(payload: PatientCreate, db: Session = Depends(get_db)) -> Patient:
    patient = Patient(name=payload.name)
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


@router.get("", response_model=list[PatientResponse])
def list_patients(db: Session = Depends(get_db)) -> list[Patient]:
    return db.query(Patient).order_by(Patient.created_at.desc()).all()


@router.get("/{patient_id}", response_model=PatientResponse)
def get_patient(patient_id: str, db: Session = Depends(get_db)) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.get("/{patient_id}/scans", response_model=list[ScanSummary])
def get_patient_scans(patient_id: str, db: Session = Depends(get_db)) -> list[ScanSummary]:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return [
        ScanSummary(
            id=s.id,
            created_at=s.created_at.isoformat(),
            area_cm2=s.area_cm2,
            severity=s.severity,
            status="ULCER DETECTED" if s.ulcer_percent > 0 else "HEALTHY",
        )
        for s in sorted(patient.scans, key=lambda s: s.created_at)
    ]
