"""Derive truthful pipeline state from durable scene manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spatialforge.scenes.store import SCENE_ID_PATTERN


def _read(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def inspect_scene_job(scene_dir: str | Path) -> dict[str, Any]:
    scene = Path(scene_dir).expanduser().resolve()
    if not scene.is_dir() or not SCENE_ID_PATTERN.fullmatch(scene.name):
        raise ValueError("Invalid scene directory")
    metadata = scene / "metadata"
    capture = _read(metadata / "capture_manifest.json")
    single = _read(metadata / "single_image_manifest.json")
    readiness = _read(metadata / "capture_readiness.json")
    reconstruction = _read(metadata / "reconstruction_manifest.json")
    dense = _read(metadata / "dense_reconstruction_manifest.json")
    viewer = _read(metadata / "scene_manifest.json")

    stages: list[dict[str, Any]] = []
    if capture:
        capture_mode = capture.get("capture_mode", "video")
        stage_name = "photo_validation" if capture_mode == "photo_set" else "frame_extraction"
        stages.append({"name": stage_name, "status": capture.get("processing_status", "unknown"), "details": {"capture_mode": capture_mode, "accepted_frames": capture.get("accepted_frames"), "rejected_frames": capture.get("rejected_frames")}})
    if single:
        current = single.get("current_stage", "image_validation")
        ordered = ("image_validation", "depth_inference", "geometry_generation", "packaging")
        current_index = ordered.index(current) if current in ordered else -1
        for index, name in enumerate(ordered):
            if single.get("processing_status") == "completed":
                stage_status = "completed"
            elif single.get("processing_status") == "failed" and name == current:
                stage_status = "failed"
            elif index < current_index:
                stage_status = "completed"
            elif index == current_index:
                stage_status = "processing"
            else:
                stage_status = "pending"
            stages.append({"name": name, "status": stage_status, "details": {"capture_mode": "single_photo"}})
    if readiness:
        stages.append({"name": "readiness", "status": readiness.get("status", "unknown"), "details": readiness.get("metrics", {})})
    if reconstruction:
        stages.append({
            "name": "sparse_reconstruction",
            "status": reconstruction.get("processing_status", "unknown"),
            "current_stage": reconstruction.get("current_stage"),
            "stage_timings": reconstruction.get("stage_timings", {}),
            "details": reconstruction.get("metrics", {}),
        })
    if dense:
        stages.append({"name": "dense_reconstruction", "status": dense.get("processing_status", "unknown"), "current_stage": dense.get("current_stage"), "details": dense.get("artifacts", {})})
    if viewer:
        stages.append({"name": "viewer_package", "status": viewer.get("processing_status", "unknown"), "details": {"scene_name": viewer.get("scene_name"), "synthetic_demo": viewer.get("synthetic_demo", False)}})

    error = None
    for document in (dense, reconstruction, single, capture):
        if document and document.get("processing_status") == "failed":
            error = document.get("error") or "Stage failed without an error message"
            break
    if viewer and viewer.get("processing_status") in {"completed", "demonstration"}:
        status, current_stage = "ready", "viewer_package"
    elif dense and dense.get("processing_status") == "completed":
        status, current_stage = "awaiting_packaging", "dense_reconstruction"
    elif reconstruction and reconstruction.get("processing_status") == "completed":
        sparse_ply = scene / "reconstruction" / "colmap" / "exports" / "sparse.ply"
        camera_poses = scene / "reconstruction" / "colmap" / "exports" / "camera_poses.json"
        if sparse_ply.is_file() and camera_poses.is_file():
            try:
                import tempfile
                from spatialforge.scenes.assemble import assemble_reconstructed_scene
                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as cal:
                    json.dump(
                        {"matrix_row_major": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], "target_units": "scene_unit", "metric_scale_status": "arbitrary"},
                        cal,
                    )
                    cal_path = cal.name
                try:
                    assemble_reconstructed_scene(scene, cal_path, overwrite=True)
                    viewer = _read(metadata / "scene_manifest.json")
                    if viewer:
                        stages.append({"name": "viewer_package", "status": viewer.get("processing_status", "completed"), "details": {"scene_name": viewer.get("scene_name"), "synthetic_demo": False}})
                        status, current_stage = "ready", "viewer_package"
                    else:
                        status, current_stage = "sparse_ready", "sparse_reconstruction"
                finally:
                    Path(cal_path).unlink(missing_ok=True)
            except Exception:
                status, current_stage = "sparse_ready", "sparse_reconstruction"
        else:
            status, current_stage = "sparse_ready", "sparse_reconstruction"
    elif error:
        status, current_stage = "failed", next((stage.get("current_stage") or stage["name"] for stage in reversed(stages) if stage["status"] == "failed"), "unknown")
    elif single and single.get("processing_status") == "failed":
        status, current_stage = "failed", single.get("current_stage", "depth_inference")
    elif single:
        status, current_stage = single.get("processing_status", "unknown"), single.get("current_stage", "image_validation")
    elif capture and capture.get("processing_status") == "completed":
        status, current_stage = "awaiting_reconstruction", "capture"
    elif capture:
        status, current_stage = capture.get("processing_status", "unknown"), "capture"
    elif (scene / "input").is_dir() and any((scene / "input").iterdir()):
        inputs = [p for p in (scene / "input").iterdir() if p.is_file()]
        is_video = any(p.suffix.lower() in {".mp4", ".mov", ".m4v", ".mkv", ".webm"} for p in inputs)
        is_single = len(inputs) == 1 and not is_video
        derived_mode = "video" if is_video else ("single_photo" if is_single else "photo_set")
        status = "queued"
        current_stage = "frame_extraction" if is_video else "image_validation"
        if derived_mode == "single_photo":
            ordered = ("image_validation", "depth_inference", "geometry_generation", "packaging")
            for name in ordered:
                stages.append({"name": name, "status": "pending", "details": {"capture_mode": "single_photo"}})
        elif derived_mode == "photo_set":
            stages.append({"name": "photo_validation", "status": "pending", "details": {"capture_mode": "photo_set"}})
        else:
            stages.append({"name": "frame_extraction", "status": "pending", "details": {"capture_mode": "video"}})
    else:
        status, current_stage = "invalid", "discovery"

    derived_cap_mode = None
    if single:
        derived_cap_mode = single.get("capture_mode")
    elif capture:
        derived_cap_mode = capture.get("capture_mode", "video")
    elif (scene / "input").is_dir() and any((scene / "input").iterdir()):
        inputs = [p for p in (scene / "input").iterdir() if p.is_file()]
        is_video = any(p.suffix.lower() in {".mp4", ".mov", ".m4v", ".mkv", ".webm"} for p in inputs)
        derived_cap_mode = "video" if is_video else ("single_photo" if len(inputs) == 1 else "photo_set")

    return {
        "scene_id": scene.name,
        "status": status,
        "current_stage": current_stage,
        "stages": stages,
        "error": error,
        "has_original_input": (scene / "input").is_dir() and any((scene / "input").iterdir()),
        "has_viewer_manifest": viewer is not None,
        "capture_mode": derived_cap_mode,
    }


def list_scene_jobs(dataset_root: str | Path) -> list[dict[str, Any]]:
    root = Path(dataset_root).expanduser().resolve()
    if not root.is_dir():
        return []
    jobs = [inspect_scene_job(path) for path in root.iterdir() if path.is_dir() and SCENE_ID_PATTERN.fullmatch(path.name)]
    return sorted(jobs, key=lambda item: item["scene_id"], reverse=True)
