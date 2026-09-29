from footscan.analysis.scoring import (
    calculate_sinbad_score,
    generate_treatment_recommendation,
    predict_healing_days,
)


def test_sinbad_no_ulcer():
    assert calculate_sinbad_score(0) == (0, "No Ulcer")


def test_sinbad_mild():
    score, severity = calculate_sinbad_score(0.5)
    assert score == 2
    assert severity == "Mild"


def test_sinbad_moderate_boundary():
    # area == 1.0 should NOT count as mild (< 1.0 is the mild cutoff)
    score, severity = calculate_sinbad_score(1.0)
    assert severity == "Moderate"
    assert score == 4


def test_sinbad_severe():
    score, severity = calculate_sinbad_score(10.0)
    assert score == 6
    assert severity == "Severe"


def test_treatment_zero_area():
    assert "No ulcer" in generate_treatment_recommendation(0, "None", "No Ulcer")


def test_treatment_necrosis_flags_debridement():
    rec = generate_treatment_recommendation(2.0, "High Necrosis (Dark/Black Tissue)", "Moderate")
    assert "Debridement" in rec


def test_treatment_severe_flags_urgent():
    rec = generate_treatment_recommendation(5.0, "Mixed/Slough (Yellow/Fibrinous)", "Severe")
    assert "Urgent" in rec


def test_healing_days_scales_with_area():
    small = predict_healing_days(0.25)
    large = predict_healing_days(2.0)
    assert small < large
    assert predict_healing_days(0) == 0
    assert predict_healing_days(0.001) >= 1  # never rounds down to 0 for a real wound
