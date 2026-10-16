import pytest

from footscan.config import settings
from footscan.ml.model import weights_available
from footscan.service import analyze_image, compare_images

pytestmark = pytest.mark.integration
requires_model = pytest.mark.skipif(not weights_available(), reason="model weights not present (or only a Git LFS pointer)")


@requires_model
def test_analyze_image_end_to_end(sample_image):
    result = analyze_image(sample_image, ref_cm=1.0, ref_px=38.46, threshold=0.5)

    assert result.status in ("HEALTHY", "ULCER DETECTED")
    assert result.area_cm2 >= 0
    assert 0.0 <= result.ulcer_percent <= 100.0
    assert result.shape in ("Unknown", "Round", "Oval", "Irregular")
    assert result.sinbad_score in (0, 2, 4, 6)
    assert result.original.shape == (settings.image_size, settings.image_size, 3)
    assert result.blended.shape == result.original.shape


@requires_model
def test_compare_images_reports_zero_change_for_identical_inputs(sample_image):
    result = compare_images(sample_image, sample_image, ref_cm=1.0, ref_px=38.46, threshold=0.5)
    assert result["status"] == "STABLE"
    assert result["change_cm2"] == pytest.approx(0.0, abs=1e-6)
