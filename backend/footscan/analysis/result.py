from dataclasses import dataclass

import numpy as np


@dataclass
class AnalysisResult:
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

    # Visual artifacts (RGB uint8 arrays), not persisted to DB directly
    original: np.ndarray
    mask: np.ndarray
    heatmap: np.ndarray
    blended: np.ndarray
    edges: np.ndarray
    cropped: np.ndarray

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "view_type": self.view_type,
            "area_cm2": round(self.area_cm2, 4),
            "ulcer_percent": round(self.ulcer_percent, 2),
            "max_confidence": round(self.max_confidence, 3),
            "shape": self.shape,
            "color_profile": self.color_profile,
            "sinbad_score": self.sinbad_score,
            "severity": self.severity,
            "est_healing_days": self.est_healing_days,
            "treatment": self.treatment,
            "threshold": self.threshold,
            "preprocessing": self.preprocessing,
        }
