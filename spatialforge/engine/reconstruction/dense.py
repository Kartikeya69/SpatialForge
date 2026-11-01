"""COLMAP dense reconstruction stages for machines with a compatible build."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from .base import ReconstructionError
from .runner import ColmapRunner, resolve_colmap_executable


@dataclass(frozen=True)
class DenseReconstructionConfig:
    colmap_path: str | None = None
    quality: Literal["low", "balanced", "high"] = "balanced"
    geom_consistency: bool = True
    mesher: Literal["poisson", "delaunay", "none"] = "poisson"
    timeout_seconds: int = 7200

    def validate(self) -> None:
        if self.quality not in {"low", "balanced", "high"}:
            raise ValueError("quality must be low, balanced, or high")
        if self.mesher not in {"poisson", "delaunay", "none"}:
            raise ValueError("mesher must be poisson, delaunay, or none")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    @property
    def max_image_size(self) -> int:
        return {"low": 1200, "balanced": 2000, "high": 3200}[self.quality]

    @property
    def stereo_settings(self) -> dict[str, str]:
        return {
            "window_radius": {"low": "3", "balanced": "5", "high": "7"}[self.quality],
            "num_samples": {"low": "8", "balanced": "15", "high": "25"}[self.quality],
            "fusion_min_pixels": {"low": "3", "balanced": "5", "high": "7"}[self.quality],
            "fusion_max_reprojection_error": {"low": "3", "balanced": "2", "high": "1.5"}[self.quality],
        }


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2), encoding="utf-8")
    temporary.replace(path)


def run_dense_reconstruction(
    scene_dir: str | Path,
    config: DenseReconstructionConfig,
    *,
    runner: ColmapRunner | None = None,
) -> dict[str, Any]:
    config.validate()
    scene = Path(scene_dir).expanduser().resolve()
    reconstruction_manifest_path = scene / "metadata" / "reconstruction_manifest.json"
    if not reconstruction_manifest_path.is_file():
        raise ReconstructionError("Sparse reconstruction manifest is missing")
    sparse_manifest = json.loads(reconstruction_manifest_path.read_text(encoding="utf-8"))
    if sparse_manifest.get("processing_status") != "completed":
        raise ReconstructionError("Sparse reconstruction must be completed before dense processing")
    primary_relative = (sparse_manifest.get("artifacts") or {}).get("primary_model")
    if not isinstance(primary_relative, str):
        raise ReconstructionError("Sparse reconstruction does not declare a primary model")
    primary_model = (scene / primary_relative).resolve()
    try:
        primary_model.relative_to(scene)
    except ValueError as exc:
        raise ReconstructionError("Primary sparse model path escapes the scene") from exc
    if not primary_model.is_dir():
        raise ReconstructionError("Primary sparse model directory is missing")
    image_path = scene / "images"
    dense_root = scene / "reconstruction" / "colmap" / "dense"
    manifest_path = scene / "metadata" / "dense_reconstruction_manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("processing_status") == "completed":
            raise ReconstructionError("Completed dense reconstruction exists; refusing to overwrite it")
    logs = dense_root / "logs"
    workspace = dense_root / "workspace"
    fused = dense_root / "fused.ply"
    mesh = dense_root / f"mesh-{config.mesher}.ply"
    stage = "environment"
    started = time.perf_counter()
    document: dict[str, Any] = {
        "schema_version": "1.0.0",
        "scene_id": scene.name,
        "backend": "colmap_dense",
        "backend_version": None,
        "configuration": asdict(config),
        "processing_status": "running",
        "current_stage": stage,
        "failed_stage": None,
        "artifacts": {},
        "processing_duration_seconds": 0.0,
    }
    dense_root.mkdir(parents=True, exist_ok=True)
    _write_json(manifest_path, document)
    try:
        active_runner = runner or ColmapRunner(resolve_colmap_executable(config.colmap_path), config.timeout_seconds)
        document["backend_version"] = active_runner.version(logs)

        stage = "image_undistortion"
        document["current_stage"] = stage
        active_runner.run([
            "image_undistorter", "--image_path", str(image_path), "--input_path", str(primary_model),
            "--output_path", str(workspace), "--output_type", "COLMAP", "--max_image_size", str(config.max_image_size),
        ], stage=stage, log_path=logs / f"{stage}.log")

        stage = "dense_stereo"
        document["current_stage"] = stage
        active_runner.run([
            "patch_match_stereo", "--workspace_path", str(workspace), "--workspace_format", "COLMAP",
            "--PatchMatchStereo.geom_consistency", "true" if config.geom_consistency else "false",
            "--PatchMatchStereo.window_radius", config.stereo_settings["window_radius"],
            "--PatchMatchStereo.num_samples", config.stereo_settings["num_samples"],
        ], stage=stage, log_path=logs / f"{stage}.log")

        stage = "depth_fusion"
        document["current_stage"] = stage
        active_runner.run([
            "stereo_fusion", "--workspace_path", str(workspace), "--workspace_format", "COLMAP",
            "--input_type", "geometric" if config.geom_consistency else "photometric", "--output_path", str(fused),
            "--StereoFusion.min_num_pixels", config.stereo_settings["fusion_min_pixels"],
            "--StereoFusion.max_reproj_error", config.stereo_settings["fusion_max_reprojection_error"],
        ], stage=stage, log_path=logs / f"{stage}.log")
        if not fused.is_file() or fused.stat().st_size == 0:
            raise ReconstructionError("COLMAP stereo fusion produced no dense point cloud")

        artifacts = {"dense_point_cloud": fused.relative_to(scene).as_posix(), "logs": logs.relative_to(scene).as_posix()}
        if config.mesher != "none":
            stage = "mesh_generation"
            document["current_stage"] = stage
            command = "poisson_mesher" if config.mesher == "poisson" else "delaunay_mesher"
            if config.mesher == "poisson":
                arguments = [command, "--input_path", str(fused), "--output_path", str(mesh)]
            else:
                arguments = [command, "--input_path", str(workspace), "--output_path", str(mesh)]
            active_runner.run(arguments, stage=stage, log_path=logs / f"{stage}.log")
            if not mesh.is_file() or mesh.stat().st_size == 0:
                raise ReconstructionError("COLMAP mesher produced no mesh")
            artifacts["mesh_ply"] = mesh.relative_to(scene).as_posix()
        document["artifacts"] = artifacts
        document["processing_status"] = "completed"
        document["current_stage"] = "completed"
    except Exception as exc:
        document["processing_status"] = "failed"
        document["current_stage"] = stage
        document["failed_stage"] = stage
        document["error"] = str(exc)
        raise
    finally:
        document["processing_duration_seconds"] = round(time.perf_counter() - started, 6)
        _write_json(manifest_path, document)
    return document
