"""Heuristic severity scoring and recommendations.

None of the thresholds below are sourced from a validated clinical
guideline -- they are reasonable-looking placeholders carried over from
the original prototype. Treat this module's output as a rough triage
signal for a demo, not a diagnostic tool. See README "Clinical Disclaimer".
"""


def calculate_sinbad_score(area_cm2: float) -> tuple[int, str]:
    if area_cm2 == 0:
        return 0, "No Ulcer"
    if area_cm2 < 1.0:
        return 2, "Mild"
    if area_cm2 < 4.0:
        return 4, "Moderate"
    return 6, "Severe"


def generate_treatment_recommendation(area_cm2: float, color: str, severity: str) -> str:
    if area_cm2 == 0:
        return "No ulcer detected. Routine foot care recommended."

    recs: list[str] = []
    if "Necrosis" in color:
        recs.append("Immediate Debridement recommended for necrotic tissue.")
    elif "Granulation" in color:
        recs.append("Wound is granulating well. Maintain moist wound environment.")

    if severity == "Severe":
        recs.append("Urgent Clinical Intervention. Consider offloading and infection control.")
    elif severity == "Moderate":
        recs.append("Monitor closely. Ensure pressure relief.")

    if not recs:
        recs.append("Standard wound care dressing required.")
    return " | ".join(recs)


def predict_healing_days(area_cm2: float) -> int:
    if area_cm2 == 0:
        return 0
    weeks = area_cm2 / 0.5
    return max(1, int(weeks * 7))
