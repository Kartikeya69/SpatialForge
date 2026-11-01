"""Assemble verified reconstruction artifacts into a browser-loadable scene manifest."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from spatialforge.navigation.geometry import load_ply_vertices

from .coordinates import transform_point
from .schema import Matrix4, SceneManifest
from .validate import validate_viewer_pack


class SceneAssemblyError(RuntimeError):
    pass


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SceneAssemblyError(f"{label} is missing or invalid: {path}") from exc
    if not isinstance(document, dict):
        raise SceneAssemblyError(f"{label} must be a JSON object")
    return document


def _inside_file(scene: Path, path_value: str, label: str) -> Path:
    candidate = (scene / path_value).resolve()
    try:
        candidate.relative_to(scene)
    except ValueError as exc:
        raise SceneAssemblyError(f"{label} escapes the scene directory") from exc
    if not candidate.is_file():
        raise SceneAssemblyError(f"{label} does not exist: {path_value}")
    return candidate


def _camera_centers(document: dict[str, Any]) -> list[tuple[float, float, float]]:
    poses = document.get("poses") or []
    centers = []
    for pose in poses:
        center = pose.get("camera_center_world") if isinstance(pose, dict) else None
        if isinstance(center, list) and len(center) == 3:
            centers.append(tuple(float(value) for value in center))
    return centers


def assemble_reconstructed_scene(
    scene_dir: str | Path,
    calibration_path: str | Path,
    *,
    scene_name: str | None = None,
    visual_asset: str | None = None,
    overwrite: bool = False,
) -> Path:
    scene = Path(scene_dir).expanduser().resolve()
    if not scene.is_dir() or not scene.name.startswith("scene_"):
        raise SceneAssemblyError("Scene directory is missing or has an invalid identifier")
    output = scene / "metadata" / "scene_manifest.json"
    if output.exists() and not overwrite:
        raise SceneAssemblyError("A scene manifest already exists and will not be overwritten")
    reconstruction = _load_json(scene / "metadata" / "reconstruction_manifest.json", "Reconstruction manifest")
    if reconstruction.get("processing_status") != "completed":
        raise SceneAssemblyError("A completed real reconstruction is required")
    calibration = _load_json(Path(calibration_path).expanduser().resolve(), "Calibration document")
    matrix_values = calibration.get("matrix_row_major")
    if not isinstance(matrix_values, list) or len(matrix_values) != 16:
        raise SceneAssemblyError("Calibration document must contain a 16-value matrix_row_major")
    matrix: Matrix4 = tuple(float(value) for value in matrix_values)  # type: ignore[assignment]
    target_units = calibration.get("target_units", "scene_unit")
    metric_status = calibration.get("metric_scale_status", "arbitrary")
    if target_units not in {"meter", "scene_unit"} or metric_status not in {"known", "estimated", "arbitrary"}:
        raise SceneAssemblyError("Calibration unit metadata is invalid")
    if metric_status == "known" and target_units != "meter":
        raise SceneAssemblyError("Known metric scale requires target_units='meter'")

    artifacts = reconstruction.get("artifacts") or {}
    sparse_relative = artifacts.get("point_cloud_ply")
    poses_relative = artifacts.get("camera_poses")
    if not isinstance(sparse_relative, str) or not isinstance(poses_relative, str):
        raise SceneAssemblyError("Reconstruction manifest does not declare point cloud and camera-pose artifacts")
    sparse_path = _inside_file(scene, sparse_relative, "Sparse point cloud")
    poses_path = _inside_file(scene, poses_relative, "Camera poses")
    selected_relative = visual_asset or sparse_relative
    selected_path = _inside_file(scene, selected_relative, "Visual asset")
    suffix = selected_path.suffix.lower()
    if suffix not in {".ply", ".glb", ".gltf"}:
        raise SceneAssemblyError("Visual asset must be PLY, GLB, or glTF")

    bounds_source = sparse_path if suffix != ".ply" else selected_path
    vertices = load_ply_vertices(bounds_source)
    if len(vertices) == 0:
        raise SceneAssemblyError(f"Reconstructed geometry in {bounds_source.name} contains zero vertices")
    if not np.all(np.isfinite(vertices)):
        raise SceneAssemblyError(f"Reconstructed geometry in {bounds_source.name} contains non-finite coordinates (NaN or Inf)")

    transformed = np.asarray([transform_point(tuple(point), matrix) for point in vertices], dtype=np.float64)
    minimum = transformed.min(axis=0)
    maximum = transformed.max(axis=0)
    if np.any(maximum - minimum < 1e-6):
        padding = np.where(maximum - minimum < 1e-6, 0.05, 0)
        minimum -= padding
        maximum += padding

    center = (minimum + maximum) / 2.0
    span = float(max(maximum[0] - minimum[0], maximum[1] - minimum[1], maximum[2] - minimum[2]))

    camera_document = _load_json(poses_path, "Camera-pose document")
    centers = _camera_centers(camera_document)
    if not centers:
        raise SceneAssemblyError("Camera-pose document contains no registered camera centers")
    spawn = transform_point(centers[0], matrix)

    # Calculate camera yaw to face the center of the reconstructed points
    dx = center[0] - spawn[0]
    dz = center[2] - spawn[2]
    spawn_yaw = round(math.degrees(math.atan2(dx, -dz)), 1) if (dx * dx + dz * dz) > 1e-4 else 0.0

    # Calculate adaptive point size based on scene span so points are clearly visible in Viewer 2.0
    adaptive_point_size = round(max(0.15, min(0.65, span / 180.0)), 4) if suffix == ".ply" else 0.025

    asset_type = suffix.lstrip(".")
    mime = {"ply": "application/octet-stream", "glb": "model/gltf-binary", "gltf": "model/gltf+json"}[asset_type]
    assets = [
        {"id": "reconstructed_visual", "type": asset_type, "path": selected_relative.replace("\\", "/"), "role": "primary_visual", "mime_type": mime},
        {"id": "camera_poses", "type": "camera_poses", "path": poses_relative.replace("\\", "/"), "role": "diagnostic", "mime_type": "application/json", "visible_by_default": False},
    ]
    if selected_path != sparse_path:
        assets.append({"id": "sparse_points", "type": "ply", "path": sparse_relative.replace("\\", "/"), "role": "diagnostic", "mime_type": "application/octet-stream", "visible_by_default": False})
    manifest = SceneManifest.model_validate({
        "schema_version": "1.0.0",
        "scene_id": scene.name,
        "scene_name": scene_name or scene.name.replace("scene_", "").replace("_", " ").title(),
        "description": "Real reconstruction packaged by SpatialForge. Navigation remains disabled until reviewed geometry is supplied.",
        "synthetic_demo": False,
        "processing_status": "completed",
        "coordinate_system": {
            "handedness": "right", "up_axis": "Y", "forward_axis": "-Z",
            "source_convention": "COLMAP reconstruction coordinates",
            "source_to_scene_matrix_row_major": matrix,
        },
        "units": {
            "name": target_units,
            "metric_scale_status": metric_status,
            "meters_per_unit": 1.0 if metric_status == "known" else None,
        },
        "origin": [0, 0, 0],
        "bounding_box": {"minimum": minimum.tolist(), "maximum": maximum.tolist()},
        "reconstruction": {
            "backend": reconstruction.get("backend", "colmap"),
            "backend_version": reconstruction.get("backend_version"),
            "source": "reconstruction", "status": "completed",
            "metric_scale_calibrated": metric_status == "known",
        },
        "assets": assets,
        "camera_metadata": {"pose_asset_id": "camera_poses", "pose_convention": "camera_to_world"},
        "navigation": {
            "enabled": False, "spawn_position": spawn, "spawn_yaw_degrees": spawn_yaw,
            "camera_height": 1.65, "movement_speed": 2.5, "collision_radius": 0.25,
            "collider_asset_id": None, "grid_asset_id": None, "zones": [],
        },
        "poi_metadata": {"asset_id": None, "count": 0},
        "viewer": {
            "background": "#06131d",
            "ambient_light_intensity": 0.85,
            "directional_light_intensity": 2.1,
            "point_size": adaptive_point_size,
        },
    })
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(output)

    # Rigorous validation of the packaged viewer pack before returning
    validation = validate_viewer_pack(scene)
    if not validation.is_valid:
        output.unlink(missing_ok=True)
        errors_str = "; ".join(validation.errors)
        raise SceneAssemblyError(f"Viewer pack validation failed: {errors_str}")

    return output
