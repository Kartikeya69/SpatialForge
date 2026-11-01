"""Explicit similarity calibration from reconstruction coordinates to viewer world."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


class CalibrationError(ValueError):
    pass


@dataclass(frozen=True)
class SimilarityCalibration:
    matrix_row_major: tuple[float, ...]
    scale: float
    root_mean_square_error: float
    maximum_error: float
    correspondence_count: int

    def transform(self, point: Iterable[float]) -> tuple[float, float, float]:
        vector = np.asarray(tuple(point), dtype=np.float64)
        if vector.shape != (3,):
            raise CalibrationError("Points must contain exactly three coordinates")
        matrix = np.asarray(self.matrix_row_major, dtype=np.float64).reshape(4, 4)
        output = matrix @ np.append(vector, 1.0)
        return tuple(float(value) for value in output[:3])


def estimate_similarity_transform(
    source_points: Iterable[Iterable[float]],
    target_points: Iterable[Iterable[float]],
    *,
    estimate_scale: bool = True,
) -> SimilarityCalibration:
    source = np.asarray(tuple(tuple(point) for point in source_points), dtype=np.float64)
    target = np.asarray(tuple(tuple(point) for point in target_points), dtype=np.float64)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1:] != (3,):
        raise CalibrationError("Source and target correspondence arrays must both have shape (N, 3)")
    if len(source) < 3:
        raise CalibrationError("At least three point correspondences are required")
    if not np.isfinite(source).all() or not np.isfinite(target).all():
        raise CalibrationError("Calibration coordinates must be finite")

    source_center = source.mean(axis=0)
    target_center = target.mean(axis=0)
    source_centered = source - source_center
    target_centered = target - target_center
    variance = float(np.sum(source_centered**2) / len(source))
    if variance <= 1e-12 or np.linalg.matrix_rank(source_centered) < 2:
        raise CalibrationError("Calibration points are degenerate or collinear")

    covariance = target_centered.T @ source_centered / len(source)
    left, singular_values, right_transpose = np.linalg.svd(covariance)
    correction = np.eye(3)
    if np.linalg.det(left) * np.linalg.det(right_transpose) < 0:
        correction[-1, -1] = -1
    rotation = left @ correction @ right_transpose
    scale = float(np.sum(singular_values * np.diag(correction)) / variance) if estimate_scale else 1.0
    if not np.isfinite(scale) or scale <= 0:
        raise CalibrationError("Estimated scale is invalid")
    translation = target_center - scale * rotation @ source_center
    matrix = np.eye(4)
    matrix[:3, :3] = scale * rotation
    matrix[:3, 3] = translation

    predicted = (scale * (rotation @ source.T)).T + translation
    errors = np.linalg.norm(predicted - target, axis=1)
    return SimilarityCalibration(
        matrix_row_major=tuple(float(value) for value in matrix.reshape(-1)),
        scale=scale,
        root_mean_square_error=float(np.sqrt(np.mean(errors**2))),
        maximum_error=float(np.max(errors)),
        correspondence_count=len(source),
    )
