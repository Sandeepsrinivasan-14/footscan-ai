"""Regression tests for the legacy training helper ``DataGen.change_color_space``.

The original code used ``color_space.lower() is 'hsi' or 'hsv'``, which is always truthy,
so every colour space (including ``lab`` and ``rgb``) was converted to HSV.
"""

import sys
import types

import cv2
import numpy as np
import pytest

# The legacy module imports matplotlib at the top, but only for plotting helpers. CI does not install
# it, so stub it when missing; the colour-space code under test never touches it.
try:
    import matplotlib.pyplot  # noqa: F401
except ImportError:
    _mpl = types.ModuleType("matplotlib")
    _mpl.pyplot = types.ModuleType("matplotlib.pyplot")
    sys.modules.setdefault("matplotlib", _mpl)
    sys.modules.setdefault("matplotlib.pyplot", _mpl.pyplot)

from FootScan_AI_Core.utils.io.data import DataGen  # noqa: E402


@pytest.fixture
def pair():
    rng = np.random.default_rng(0)
    img = rng.integers(0, 256, (8, 8, 3), dtype=np.uint8)
    return img, img.copy()


@pytest.mark.parametrize("name", ["hsv", "HSV", "hsi"])
def test_hsv_and_hsi_convert_to_hsv(pair, name):
    image, label = pair
    out_img, out_lbl = DataGen.change_color_space(image.copy(), label.copy(), name)
    expected = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    assert np.array_equal(out_img, expected)
    assert np.array_equal(out_lbl, expected)


def test_lab_converts_to_lab_not_hsv(pair):
    image, label = pair
    out_img, _ = DataGen.change_color_space(image.copy(), label.copy(), "LAB")
    assert np.array_equal(out_img, cv2.cvtColor(image, cv2.COLOR_BGR2LAB))
    assert not np.array_equal(out_img, cv2.cvtColor(image, cv2.COLOR_BGR2HSV))


def test_other_color_spaces_are_unchanged(pair):
    image, label = pair
    out_img, out_lbl = DataGen.change_color_space(image.copy(), label.copy(), "rgb")
    assert np.array_equal(out_img, image)
    assert np.array_equal(out_lbl, label)
