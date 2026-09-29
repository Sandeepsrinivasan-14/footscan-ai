import numpy as np

from footscan.analysis.color import analyze_color
from footscan.analysis.shape import analyze_shape, auto_crop_wound, extract_edges


def test_shape_unknown_for_empty_mask():
    empty = np.zeros((256, 256), dtype=np.uint8)
    assert analyze_shape(empty) == "Unknown"


def test_shape_round_for_circle(circular_mask):
    assert analyze_shape(circular_mask) == "Round"


def test_shape_irregular_for_thin_strip(elongated_mask):
    assert analyze_shape(elongated_mask) == "Irregular"


def test_color_none_for_empty_mask(sample_image):
    empty = np.zeros((256, 256), dtype=np.uint8)
    assert analyze_color(sample_image, empty) == "None"


def test_color_high_necrosis_for_dark_region():
    img = np.full((256, 256, 3), 20, dtype=np.uint8)  # very dark
    mask = np.ones((256, 256), dtype=np.uint8)
    assert "Necrosis" in analyze_color(img, mask)


def test_color_granulation_for_saturated_red():
    img = np.zeros((256, 256, 3), dtype=np.uint8)
    img[:, :, 0] = 200  # strong red channel -> high saturation in HSV
    mask = np.ones((256, 256), dtype=np.uint8)
    assert "Granulation" in analyze_color(img, mask)


def test_auto_crop_returns_original_when_no_contours(sample_image):
    empty = np.zeros((256, 256), dtype=np.uint8)
    cropped = auto_crop_wound(sample_image, empty)
    assert cropped.shape == sample_image.shape


def test_auto_crop_shrinks_to_roi(sample_image, circular_mask):
    cropped = auto_crop_wound(sample_image, circular_mask)
    assert cropped.shape[0] < sample_image.shape[0]
    assert cropped.shape[1] < sample_image.shape[1]


def test_extract_edges_marks_boundary_red(sample_image, circular_mask):
    overlay = extract_edges(circular_mask, sample_image)
    red_pixels = np.sum((overlay[:, :, 0] == 255) & (overlay[:, :, 1] == 0) & (overlay[:, :, 2] == 0))
    assert red_pixels > 0
