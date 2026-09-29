import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    scans: Mapped[list["ScanRecord"]] = relationship(back_populates="patient", cascade="all, delete-orphan")


class ScanRecord(Base):
    __tablename__ = "scans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    patient_id: Mapped[str | None] = mapped_column(ForeignKey("patients.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    view_type: Mapped[str] = mapped_column(String(64), default="Plantar (Bottom)")
    threshold: Mapped[float] = mapped_column(Float, default=0.5)
    preprocessing: Mapped[str] = mapped_column(String(64), default="None")

    area_cm2: Mapped[float] = mapped_column(Float)
    ulcer_percent: Mapped[float] = mapped_column(Float)
    max_confidence: Mapped[float] = mapped_column(Float)
    shape: Mapped[str] = mapped_column(String(64))
    color_profile: Mapped[str] = mapped_column(String(128))
    sinbad_score: Mapped[int] = mapped_column(Integer)
    severity: Mapped[str] = mapped_column(String(64))
    est_healing_days: Mapped[int] = mapped_column(Integer)
    treatment: Mapped[str] = mapped_column(Text)

    original_image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    overlay_image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    patient: Mapped["Patient | None"] = relationship(back_populates="scans")
