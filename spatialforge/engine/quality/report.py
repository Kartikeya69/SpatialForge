"""Unified Quality Report engine for SpatialForge Reconstruction Engine 3.0."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from spatialforge.scenes.validate import validate_viewer_pack


@dataclass(frozen=True)
class UnifiedQualityReport:
    scene_id: str
    pipeline: str  # "single_photo", "photo_set", "video", "synthetic"
    status: str
    confidence_score: float  # 0.0 - 1.0 honest score
    metric_scale_status: str  # "arbitrary" | "metric"
    geometry_summary: dict[str, Any]
    input_quality: dict[str, Any]
    reconstruction_metrics: dict[str, Any]
    limitations: list[str]
    recommendations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def generate_quality_report(scene_dir: str | Path) -> UnifiedQualityReport:
    scene = Path(scene_dir).expanduser().resolve()
    if not scene.is_dir():
        raise FileNotFoundError(f"Scene directory does not exist: {scene}")

    metadata_dir = scene / "metadata"
    scene_manifest_path = metadata_dir / "scene_manifest.json"
    single_image_quality_path = metadata_dir / "single_image_quality.json"
    reconstruction_manifest_path = metadata_dir / "reconstruction_manifest.json"
    capture_manifest_path = metadata_dir / "capture_manifest.json"

    # Validate viewer pack
    vpack = validate_viewer_pack(scene)

    # Determine pipeline type
    pipeline = "unknown"
    if single_image_quality_path.is_file() or (metadata_dir / "single_image_manifest.json").is_file():
        pipeline = "single_photo"
    elif capture_manifest_path.is_file():
        try:
            cman = json.loads(capture_manifest_path.read_text(encoding="utf-8"))
            pipeline = cman.get("capture_mode", "video")
        except Exception:
            pipeline = "video"
    elif vpack.scene_type == "synthetic_demo":
        pipeline = "synthetic"

    # Default containers
    input_quality: dict[str, Any] = {}
    reconstruction_metrics: dict[str, Any] = {}
    limitations: list[str] = []
    recommendations: list[str] = []
    metric_scale_status = "arbitrary"
    status = "completed" if vpack.is_valid else "failed"
    confidence = 0.5

    if pipeline == "single_photo":
        metric_scale_status = "arbitrary"
        limitations.extend([
            "AI-estimated 2.5D monocular depth has arbitrary non-metric scale.",
            "Hidden and occluded surfaces are not reconstructed.",
            "Visual depth ordering is predicted from a single viewpoint without stereoscopic baseline.",
        ])
        recommendations.extend([
            "Use multi-view photo set or video capture with COLMAP if absolute metric measurement is required.",
            "Ensure subject lighting is even and avoids heavy specular glare.",
        ])

        if single_image_quality_path.is_file():
            try:
                sq = json.loads(single_image_quality_path.read_text(encoding="utf-8"))
                input_quality["input_resolution"] = sq.get("input_resolution")
                input_quality["focal_length_pixels"] = sq.get("focal_length_pixels")
                reconstruction_metrics["vertex_count"] = sq.get("vertex_count", vpack.point_count)
                reconstruction_metrics["triangle_count"] = sq.get("triangle_count", vpack.triangle_count)
                reconstruction_metrics["triangle_retention_ratio"] = sq.get("triangle_retention_ratio", 0.0)
                reconstruction_metrics["inference_seconds"] = sq.get("inference_seconds")
                retention = sq.get("triangle_retention_ratio", 0.7)
                confidence = round(float(np_clip(retention * 0.95, 0.4, 0.9)), 2)
            except Exception:
                pass
        else:
            confidence = 0.75 if vpack.is_valid else 0.1

    elif pipeline in {"photo_set", "video", "colmap"}:
        metric_scale_status = "arbitrary"
        limitations.extend([
            "Monocular SfM produces arbitrary scale unless known ground-control points or metric scaling is applied.",
            "Textureless surfaces (blank white walls, clear glass) cannot produce dense point features.",
        ])
        if reconstruction_manifest_path.is_file():
            try:
                rm = json.loads(reconstruction_manifest_path.read_text(encoding="utf-8"))
                metrics = rm.get("metrics", {})
                status = rm.get("processing_status", status)
                reg_images = metrics.get("registered_images", vpack.camera_pose_count)
                total_images = metrics.get("input_images", 0)
                mean_error = metrics.get("mean_reprojection_error_pixels")
                reconstruction_metrics["registered_images"] = reg_images
                reconstruction_metrics["total_images"] = total_images
                reconstruction_metrics["mean_reprojection_error_pixels"] = mean_error
                reconstruction_metrics["points_3d"] = metrics.get("points_3d", vpack.point_count)

                if total_images > 0:
                    ratio = reg_images / total_images
                    reconstruction_metrics["registration_ratio"] = round(ratio, 4)
                    if ratio >= 0.8:
                        confidence = 0.9
                    elif ratio >= 0.5:
                        confidence = 0.7
                        recommendations.append("Moderate camera registration ratio; consider capturing more overlapping angles.")
                    else:
                        confidence = 0.4
                        recommendations.append("Low camera registration ratio. Increase overlap (>70%) and avoid fast camera rotation.")
            except Exception:
                pass

        if capture_manifest_path.is_file():
            try:
                cm = json.loads(capture_manifest_path.read_text(encoding="utf-8"))
                input_quality["accepted_frames"] = cm.get("accepted_frames")
                input_quality["rejected_frames"] = cm.get("rejected_frames")
            except Exception:
                pass

    geometry_summary = {
        "point_count": vpack.point_count,
        "triangle_count": vpack.triangle_count,
        "span": vpack.span,
        "bounding_box_min": vpack.bounding_box_min,
        "bounding_box_max": vpack.bounding_box_max,
        "center": vpack.center,
        "camera_pose_count": vpack.camera_pose_count,
        "geometry_format": vpack.geometry_format,
        "is_valid": vpack.is_valid,
    }

    return UnifiedQualityReport(
        scene_id=scene.name,
        pipeline=pipeline,
        status=status,
        confidence_score=confidence,
        metric_scale_status=metric_scale_status,
        geometry_summary=geometry_summary,
        input_quality=input_quality,
        reconstruction_metrics=reconstruction_metrics,
        limitations=limitations,
        recommendations=recommendations,
    )


def np_clip(val: float, low: float, high: float) -> float:
    return max(low, min(high, val))
