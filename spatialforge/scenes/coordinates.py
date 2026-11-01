"""Explicit coordinate transforms into the SpatialForge web convention."""

from __future__ import annotations

import numpy as np

from .schema import Matrix4, Vector3


def matrix4(values: Matrix4) -> np.ndarray:
    return np.asarray(values, dtype=np.float64).reshape((4, 4))


def transform_point(point: Vector3, source_to_scene: Matrix4) -> Vector3:
    homogeneous = np.array([*point, 1.0], dtype=np.float64)
    transformed = matrix4(source_to_scene) @ homogeneous
    if transformed[3] == 0:
        raise ValueError("Coordinate transform produced a point at infinity")
    result = transformed[:3] / transformed[3]
    return float(result[0]), float(result[1]), float(result[2])


def transform_camera_to_world(camera_to_source_world: Matrix4, source_to_scene: Matrix4) -> Matrix4:
    transformed = matrix4(source_to_scene) @ matrix4(camera_to_source_world)
    return tuple(float(value) for value in transformed.reshape(16))  # type: ignore[return-value]
