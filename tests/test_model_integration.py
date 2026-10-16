import pytest

from footscan.config import settings
from footscan.ml.model import get_model, run_inference, weights_available

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not weights_available(), reason="model weights not present (or only a Git LFS pointer)")
def test_model_loads_and_has_expected_output_shape(sample_image):
    model, device = get_model()
    assert model is not None
    assert str(device) in ("cpu", "cuda")

    confidence, processed = run_inference(sample_image, "None")
    assert confidence.shape == (settings.image_size, settings.image_size)
    assert confidence.min() >= 0.0
    assert confidence.max() <= 1.0
    assert processed.shape == sample_image.shape


@pytest.mark.skipif(not weights_available(), reason="model weights not present (or only a Git LFS pointer)")
def test_model_singleton_returns_same_instance():
    model_a, _ = get_model()
    model_b, _ = get_model()
    assert model_a is model_b
