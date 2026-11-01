"""Parsers for COLMAP text models and pose conversion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .base import ReconstructionError


@dataclass(frozen=True)
class Camera:
    camera_id: int
    model: str
    width: int
    height: int
    parameters: tuple[float, ...]


@dataclass(frozen=True)
class RegisteredImage:
    image_id: int
    quaternion_wxyz: tuple[float, float, float, float]
    translation: tuple[float, float, float]
    camera_id: int
    name: str


@dataclass(frozen=True)
class Point3D:
    point_id: int
    xyz: tuple[float, float, float]
    rgb: tuple[int, int, int]
    reprojection_error: float
    track_length: int = 0


@dataclass(frozen=True)
class ParsedModel:
    cameras: tuple[Camera, ...]
    images: tuple[RegisteredImage, ...]
    points: tuple[Point3D, ...]


def _data_lines(path: Path) -> list[str]:
    if not path.is_file():
        raise ReconstructionError(f"Required COLMAP text model file is missing: {path}")
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]


def parse_cameras(path: str | Path) -> tuple[Camera, ...]:
    cameras: list[Camera] = []
    for line in _data_lines(Path(path)):
        values = line.split()
        if len(values) < 5:
            raise ReconstructionError(f"Invalid cameras.txt record: {line}")
        cameras.append(
            Camera(
                camera_id=int(values[0]),
                model=values[1],
                width=int(values[2]),
                height=int(values[3]),
                parameters=tuple(float(value) for value in values[4:]),
            )
        )
    return tuple(cameras)


def parse_images(path: str | Path) -> tuple[RegisteredImage, ...]:
    model_path = Path(path)
    if not model_path.is_file():
        raise ReconstructionError(f"Required COLMAP text model file is missing: {model_path}")
    raw_lines = [
        line.rstrip("\r\n")
        for line in model_path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    while raw_lines and not raw_lines[0].strip():
        raw_lines.pop(0)
    images: list[RegisteredImage] = []
    index = 0
    while index < len(raw_lines):
        if not raw_lines[index].strip():
            index += 1
            continue
        values = raw_lines[index].split()
        if len(values) < 10:
            raise ReconstructionError(f"Invalid images.txt image record: {raw_lines[index]}")
        images.append(
            RegisteredImage(
                image_id=int(values[0]),
                quaternion_wxyz=tuple(float(value) for value in values[1:5]),  # type: ignore[arg-type]
                translation=tuple(float(value) for value in values[5:8]),  # type: ignore[arg-type]
                camera_id=int(values[8]),
                name=" ".join(values[9:]),
            )
        )
        index += 2  # Every image record is followed by one POINTS2D record, possibly blank.
    return tuple(images)


def parse_points3d(path: str | Path) -> tuple[Point3D, ...]:
    points: list[Point3D] = []
    for line in _data_lines(Path(path)):
        values = line.split()
        if len(values) < 8:
            raise ReconstructionError(f"Invalid points3D.txt record: {line}")
        points.append(
            Point3D(
                point_id=int(values[0]),
                xyz=tuple(float(value) for value in values[1:4]),  # type: ignore[arg-type]
                rgb=tuple(int(value) for value in values[4:7]),  # type: ignore[arg-type]
                reprojection_error=float(values[7]),
                track_length=max(0, (len(values) - 8) // 2),
            )
        )
    return tuple(points)


def parse_text_model(directory: str | Path) -> ParsedModel:
    model_dir = Path(directory)
    return ParsedModel(
        cameras=parse_cameras(model_dir / "cameras.txt"),
        images=parse_images(model_dir / "images.txt"),
        points=parse_points3d(model_dir / "points3D.txt"),
    )


def quaternion_to_rotation_matrix(quaternion_wxyz: tuple[float, float, float, float]) -> np.ndarray:
    quaternion = np.asarray(quaternion_wxyz, dtype=np.float64)
    norm = np.linalg.norm(quaternion)
    if norm == 0:
        raise ReconstructionError("Camera quaternion has zero magnitude")
    w, x, y, z = quaternion / norm
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def image_pose(image: RegisteredImage) -> dict[str, object]:
    rotation_world_to_camera = quaternion_to_rotation_matrix(image.quaternion_wxyz)
    translation = np.asarray(image.translation, dtype=np.float64)
    rotation_camera_to_world = rotation_world_to_camera.T
    camera_center = -rotation_camera_to_world @ translation
    world_to_camera = np.eye(4)
    world_to_camera[:3, :3] = rotation_world_to_camera
    world_to_camera[:3, 3] = translation
    camera_to_world = np.eye(4)
    camera_to_world[:3, :3] = rotation_camera_to_world
    camera_to_world[:3, 3] = camera_center
    return {
        "image_id": image.image_id,
        "image_name": image.name,
        "camera_id": image.camera_id,
        "quaternion_wxyz": list(image.quaternion_wxyz),
        "translation_world_to_camera": list(image.translation),
        "camera_center_world": camera_center.tolist(),
        "world_to_camera_matrix": world_to_camera.tolist(),
        "camera_to_world_matrix": camera_to_world.tolist(),
    }
