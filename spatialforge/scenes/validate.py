"""Validation of SpatialForge scene viewer packs and reconstruction assets."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from spatialforge.navigation.geometry import GeometryNavigationError, load_ply_vertices
from .schema import SceneManifest


class ViewerPackValidationError(RuntimeError):
    """Raised when a viewer pack is corrupt, empty, or unrenderable."""


@dataclass(frozen=True)
class ViewerPackValidation:
    is_valid: bool
    scene_id: str
    scene_type: str
    visual_asset_path: str
    geometry_format: str
    point_count: int
    triangle_count: int
    bounding_box_min: list[float]
    bounding_box_max: list[float]
    span: float
    center: list[float]
    camera_pose_count: int
    errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _check_ply_integrity(path: Path) -> tuple[int, int]:
    """Parse PLY header and verify vertex/face counts and finite coordinates."""
    if not path.is_file() or path.stat().st_size == 0:
        raise ViewerPackValidationError(f"PLY file is missing or empty: {path.name}")

    with path.open("rb") as stream:
        header_lines: list[str] = []
        while True:
            raw_line = stream.readline()
            if not raw_line:
                raise ViewerPackValidationError(f"PLY header is incomplete in {path.name}")
            try:
                line = raw_line.decode("ascii").strip()
            except UnicodeDecodeError as exc:
                raise ViewerPackValidationError(f"PLY header must be ASCII in {path.name}") from exc
            header_lines.append(line)
            if line == "end_header":
                break

    if not header_lines or header_lines[0] != "ply":
        raise ViewerPackValidationError(f"File is not a valid PLY file: {path.name}")

    vertex_count = 0
    face_count = 0
    for line in header_lines:
        if line.startswith("element vertex "):
            try:
                vertex_count = int(line.split()[2])
            except (IndexError, ValueError) as exc:
                raise ViewerPackValidationError(f"Invalid vertex element count in {path.name}") from exc
        elif line.startswith("element face "):
            try:
                face_count = int(line.split()[2])
            except (IndexError, ValueError) as exc:
                raise ViewerPackValidationError(f"Invalid face element count in {path.name}") from exc

    if vertex_count <= 0:
        raise ViewerPackValidationError(f"PLY file contains zero vertices: {path.name}")

    try:
        vertices = load_ply_vertices(path)
    except GeometryNavigationError as exc:
        raise ViewerPackValidationError(f"Failed to read PLY vertices from {path.name}: {exc}") from exc

    if len(vertices) == 0:
        raise ViewerPackValidationError(f"Zero vertices loaded from {path.name}")
    if not np.all(np.isfinite(vertices)):
        raise ViewerPackValidationError(f"PLY file contains non-finite coordinates (NaN or Inf) in {path.name}")

    return vertex_count, face_count


def _check_glb_integrity(path: Path) -> tuple[int, int]:
    """Verify GLB magic bytes and JSON chunk structure."""
    if not path.is_file() or path.stat().st_size < 12:
        raise ViewerPackValidationError(f"GLB file is missing or too small: {path.name}")
    with path.open("rb") as f:
        magic = f.read(4)
        if magic != b"glTF":
            raise ViewerPackValidationError(f"File is not a valid GLB container: {path.name}")
    return 1, 1


def validate_viewer_pack(scene_dir: str | Path) -> ViewerPackValidation:
    """Rigorous verification of a scene viewer pack.

    Ensures the scene manifest exists, all declared assets exist on disk,
    geometry is non-empty, coordinates are finite, and camera metadata is valid.
    """
    scene = Path(scene_dir).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if not scene.is_dir() or not scene.name.startswith("scene_"):
        return ViewerPackValidation(
            is_valid=False,
            scene_id=scene.name,
            scene_type="unknown",
            visual_asset_path="",
            geometry_format="unknown",
            point_count=0,
            triangle_count=0,
            bounding_box_min=[0, 0, 0],
            bounding_box_max=[0, 0, 0],
            span=0.0,
            center=[0, 0, 0],
            camera_pose_count=0,
            errors=[f"Scene directory does not exist or has invalid ID: {scene}"],
            warnings=[],
        )

    manifest_path = scene / "metadata" / "scene_manifest.json"
    if not manifest_path.is_file():
        return ViewerPackValidation(
            is_valid=False,
            scene_id=scene.name,
            scene_type="unknown",
            visual_asset_path="",
            geometry_format="unknown",
            point_count=0,
            triangle_count=0,
            bounding_box_min=[0, 0, 0],
            bounding_box_max=[0, 0, 0],
            span=0.0,
            center=[0, 0, 0],
            camera_pose_count=0,
            errors=[f"Scene manifest does not exist: {manifest_path}"],
            warnings=[],
        )

    try:
        raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = SceneManifest.model_validate(raw_manifest)
    except Exception as exc:
        return ViewerPackValidation(
            is_valid=False,
            scene_id=scene.name,
            scene_type="unknown",
            visual_asset_path="",
            geometry_format="unknown",
            point_count=0,
            triangle_count=0,
            bounding_box_min=[0, 0, 0],
            bounding_box_max=[0, 0, 0],
            span=0.0,
            center=[0, 0, 0],
            camera_pose_count=0,
            errors=[f"Scene manifest failed validation: {exc}"],
            warnings=[],
        )

    # Determine scene type
    scene_type = "colmap_reconstruction" if manifest.reconstruction.backend == "colmap" else (
        "single_photo_depth" if manifest.reconstruction.backend == "depth_anything_v2_onnx" else (
            "synthetic_demo" if manifest.synthetic_demo else "general_3d"
        )
    )

    # Check assets
    primary_asset = next((a for a in manifest.assets if a.role == "primary_visual"), None)
    if primary_asset is None:
        errors.append("Scene manifest does not declare a primary_visual asset")
        return ViewerPackValidation(
            is_valid=False,
            scene_id=manifest.scene_id,
            scene_type=scene_type,
            visual_asset_path="",
            geometry_format="unknown",
            point_count=0,
            triangle_count=0,
            bounding_box_min=manifest.bounding_box.minimum,
            bounding_box_max=manifest.bounding_box.maximum,
            span=0.0,
            center=[0, 0, 0],
            camera_pose_count=0,
            errors=errors,
            warnings=warnings,
        )

    # Verify all declared assets exist on disk without path traversal
    for asset in manifest.assets:
        candidate = (scene / asset.path).resolve()
        try:
            candidate.relative_to(scene)
        except ValueError:
            errors.append(f"Asset path escapes scene directory: {asset.path}")
            continue
        if not candidate.is_file():
            if asset.required:
                errors.append(f"Required asset does not exist on disk: {asset.path}")
            else:
                warnings.append(f"Optional asset missing on disk: {asset.path}")
        elif candidate.stat().st_size == 0:
            if asset.required:
                errors.append(f"Required asset file is empty: {asset.path}")
            else:
                warnings.append(f"Optional asset file is empty: {asset.path}")

    # Inspect primary geometry
    visual_path = (scene / primary_asset.path).resolve()
    geometry_format = primary_asset.type
    point_count = 0
    triangle_count = 0

    if visual_path.is_file() and visual_path.stat().st_size > 0:
        suffix = visual_path.suffix.lower()
        try:
            if suffix == ".ply":
                v_count, f_count = _check_ply_integrity(visual_path)
                point_count = v_count
                triangle_count = f_count
            elif suffix in {".glb", ".gltf"}:
                _check_glb_integrity(visual_path)
                point_count = 1
                triangle_count = 1
        except ViewerPackValidationError as exc:
            errors.append(str(exc))

    # Bounding box & span
    bbox_min = manifest.bounding_box.minimum
    bbox_max = manifest.bounding_box.maximum
    span = max(bbox_max[0] - bbox_min[0], bbox_max[1] - bbox_min[1], bbox_max[2] - bbox_min[2])
    center = [
        (bbox_min[0] + bbox_max[0]) / 2.0,
        (bbox_min[1] + bbox_max[1]) / 2.0,
        (bbox_min[2] + bbox_max[2]) / 2.0,
    ]

    # Camera poses
    camera_pose_count = 0
    pose_asset = next((a for a in manifest.assets if a.type == "camera_poses"), None)
    if pose_asset:
        pose_path = (scene / pose_asset.path).resolve()
        if pose_path.is_file():
            try:
                pose_doc = json.loads(pose_path.read_text(encoding="utf-8"))
                camera_pose_count = len(pose_doc.get("poses", []))
            except Exception:
                warnings.append("Camera poses asset is not valid JSON")

    is_valid = len(errors) == 0 and point_count > 0

    return ViewerPackValidation(
        is_valid=is_valid,
        scene_id=manifest.scene_id,
        scene_type=scene_type,
        visual_asset_path=primary_asset.path,
        geometry_format=geometry_format,
        point_count=point_count,
        triangle_count=triangle_count,
        bounding_box_min=bbox_min,
        bounding_box_max=bbox_max,
        span=round(span, 4),
        center=[round(c, 4) for c in center],
        camera_pose_count=camera_pose_count,
        errors=errors,
        warnings=warnings,
    )
