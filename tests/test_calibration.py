import math

import pytest

from spatialforge.scenes.calibration import CalibrationError, estimate_similarity_transform


def test_similarity_calibration_recovers_rotation_scale_and_translation() -> None:
    source = [(0, 0, 0), (1, 0, 0), (0, 0, 1), (1, 1, 1)]
    # Rotate +90 degrees around Y, scale by 2, then translate.
    target = [(3 + 2 * z, 1 + 2 * y, -4 - 2 * x) for x, y, z in source]
    result = estimate_similarity_transform(source, target)
    assert result.scale == pytest.approx(2)
    assert result.root_mean_square_error < 1e-10
    assert result.transform((0.25, 0.5, 0.75)) == pytest.approx((4.5, 2.0, -4.5))


def test_calibration_rejects_collinear_points() -> None:
    with pytest.raises(CalibrationError, match="degenerate|collinear"):
        estimate_similarity_transform([(0, 0, 0), (1, 0, 0), (2, 0, 0)], [(0, 0, 0), (2, 0, 0), (4, 0, 0)])


def test_calibration_can_preserve_scale() -> None:
    source = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    target = [(5, 2, 1), (6, 2, 1), (5, 3, 1)]
    result = estimate_similarity_transform(source, target, estimate_scale=False)
    assert math.isclose(result.scale, 1)
