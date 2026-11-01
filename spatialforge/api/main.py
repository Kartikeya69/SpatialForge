"""FastAPI endpoints for capture upload and background processing."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from spatialforge import __version__
from spatialforge.engine.ingestion.pipeline import (
    CapturePipeline,
    create_scene_layout,
    load_capture_config,
)
from spatialforge.engine.ingestion.images import ImageIngestionError, PhotoSetPipeline, SUPPORTED_IMAGE_EXTENSIONS
from spatialforge.engine.ingestion.video import SUPPORTED_VIDEO_EXTENSIONS, VideoError, inspect_video
from spatialforge.engine.reconstruction import ColmapBackend
from spatialforge.engine.reconstruction.base import ReconstructionConfig, resolve_reconstruction_profile
from spatialforge.engine.reconstruction.single_image import SingleImagePipeline
from spatialforge.engine.reconstruction.colmap import load_reconstruction_config, validate_scene
from spatialforge.scenes import SceneStore
from spatialforge.scenes.package import ScenePackageError, export_scene_package, import_scene_package
from spatialforge.scenes.store import SceneAssetError, SceneManifestError, SceneNotFoundError, SceneStoreError
from spatialforge.scenes.validate import validate_viewer_pack, ViewerPackValidation
from spatialforge.engine.quality.report import generate_quality_report
from spatialforge.engine.analysis.media_analyzer import analyze_single_frame, analyze_sequence
from spatialforge.navigation import NavigationService, NavigationServiceError, POI, RouteRequest
from spatialforge.engine.ingestion.readiness import CaptureReadinessError, analyze_capture_readiness, write_capture_readiness_report
from spatialforge.workflows import inspect_scene_job, list_scene_jobs
from spatialforge.engine.processing_profiles import ProcessingCancelled, memory_snapshot, resolve_processing_profile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(os.getenv("SPATIALFORGE_CAPTURE_CONFIG", PROJECT_ROOT / "configs" / "capture.yaml"))
CONFIG = load_capture_config(CONFIG_PATH)
DATASET_ROOT = Path(os.getenv("SPATIALFORGE_DATASET_ROOT", CONFIG.dataset_root))
if not DATASET_ROOT.is_absolute():
    DATASET_ROOT = PROJECT_ROOT / DATASET_ROOT

app = FastAPI(title="SpatialForge Capture API", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("SPATIALFORGE_CORS_ORIGINS", "http://localhost:5173").split(",")],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
_executor = ThreadPoolExecutor(max_workers=CONFIG.worker_count, thread_name_prefix="capture")
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_job_cancel_events: dict[str, threading.Event] = {}
RECONSTRUCTION_CONFIG_PATH = Path(
    os.getenv("SPATIALFORGE_RECONSTRUCTION_CONFIG", PROJECT_ROOT / "configs" / "reconstruction.yaml")
)
RECONSTRUCTION_CONFIG = load_reconstruction_config(RECONSTRUCTION_CONFIG_PATH)
_reconstruction_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="reconstruction")
_reconstruction_jobs: dict[str, dict[str, Any]] = {}
_reconstruction_jobs_lock = threading.Lock()


def _set_job(scene_key: str, **values: Any) -> None:
    with _jobs_lock:
        _jobs.setdefault(scene_key, {}).update(values)


def _run_capture(scene_id: str, scene_dir: Path, video_path: Path, original_filename: str) -> None:
    _set_job(scene_id, status="processing")
    try:
        manifest = CapturePipeline(CONFIG).process(
            video_path,
            DATASET_ROOT,
            scene_id=scene_id,
            existing_scene_dir=scene_dir,
            copy_input=False,
            original_filename=original_filename,
        )
        _set_job(
            scene_id,
            status=manifest["processing_status"],
            accepted_frames=manifest["accepted_frames"],
            rejected_frames=manifest["rejected_frames"],
        )
    except Exception as exc:  # The manifest contains the detailed processing failure.
        _set_job(scene_id, status="failed", error=str(exc))


def _run_photo_set(
    scene_id: str,
    scene_dir: Path,
    paths: list[Path],
    names: list[str],
    override_noncritical: bool = False,
    profile: str = "auto",
    cancel_event: threading.Event | None = None,
) -> None:
    _set_job(scene_id, status="processing", current_stage="image_validation")
    try:
        manifest = PhotoSetPipeline(CONFIG).process(
            paths,
            scene_dir,
            original_filenames=names,
            override_noncritical=override_noncritical,
            profile=profile,  # type: ignore[arg-type]
            is_cancelled=cancel_event.is_set if cancel_event else None,
            on_progress=lambda stage, current, total: _set_job(
                scene_id, current_stage=stage, completed_units=current, total_units=total
            ),
        )
        _set_job(
            scene_id,
            status="ready_for_reconstruction",
            current_stage="validation",
            accepted_frames=manifest["accepted_frames"],
            rejected_frames=manifest["rejected_frames"],
        )
    except Exception as exc:
        _set_job(
            scene_id,
            status="cancelled" if isinstance(exc, ProcessingCancelled) else "failed",
            current_stage="cancelled" if isinstance(exc, ProcessingCancelled) else "image_validation",
            error=str(exc),
        )
    finally:
        _job_cancel_events.pop(scene_id, None)


def _run_single_image(
    scene_id: str,
    scene_dir: Path,
    image_path: Path,
    original_filename: str,
    depth_exaggeration: float = 1.0,
    profile: str = "auto",
    cancel_event: threading.Event | None = None,
) -> None:
    _set_job(scene_id, status="processing", current_stage="image_validation")
    try:
        manifest = SingleImagePipeline().process(
            image_path,
            scene_dir,
            original_filename,
            depth_exaggeration=depth_exaggeration,
            profile=profile,  # type: ignore[arg-type]
            is_cancelled=cancel_event.is_set if cancel_event else None,
            on_stage=lambda stage: _set_job(scene_id, current_stage=stage),
        )
        _set_job(
            scene_id,
            status=manifest["processing_status"],
            current_stage=manifest["current_stage"],
            manifest_location=f"{scene_id}/metadata/single_image_manifest.json",
        )
    except Exception as exc:
        failed_stage = "image_validation"
        manifest_path = scene_dir / "metadata" / "single_image_manifest.json"
        if manifest_path.is_file():
            try:
                import json

                failed_stage = json.loads(manifest_path.read_text(encoding="utf-8")).get("current_stage", failed_stage)
            except (OSError, ValueError):
                pass
        _set_job(
            scene_id,
            status="cancelled" if isinstance(exc, ProcessingCancelled) else "failed",
            current_stage="cancelled" if isinstance(exc, ProcessingCancelled) else failed_stage,
            error=str(exc),
        )
    finally:
        _job_cancel_events.pop(scene_id, None)


async def _store_image_uploads(uploads: list[UploadFile], scene_dir: Path) -> tuple[list[Path], list[str]]:
    if not uploads:
        raise HTTPException(status_code=400, detail="At least one image is required")
    size_limit = CONFIG.upload_size_limit_mb * 1024 * 1024
    total_bytes = 0
    paths: list[Path] = []
    names: list[str] = []
    try:
        for index, upload in enumerate(uploads, start=1):
            original_name = Path(upload.filename or "").name
            suffix = Path(original_name).suffix.lower()
            if not original_name or suffix not in SUPPORTED_IMAGE_EXTENSIONS:
                supported = ", ".join(sorted(SUPPORTED_IMAGE_EXTENSIONS))
                raise HTTPException(status_code=415, detail=f"Supported image formats: {supported}")
            destination = scene_dir / "input" / f"upload_{index:06d}{suffix}"
            written = 0
            with destination.open("xb") as output:
                while chunk := await upload.read(1024 * 1024):
                    written += len(chunk)
                    total_bytes += len(chunk)
                    if total_bytes > size_limit:
                        raise HTTPException(
                            status_code=413,
                            detail=f"Combined upload exceeds {CONFIG.upload_size_limit_mb} MB limit",
                        )
                    output.write(chunk)
            if written == 0:
                raise HTTPException(status_code=400, detail=f"Uploaded image is empty: {original_name}")
            paths.append(destination)
            names.append(original_name)
    finally:
        for upload in uploads:
            await upload.close()
    return paths, names


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post("/api/v1/captures", status_code=status.HTTP_202_ACCEPTED)
async def create_capture(video: UploadFile = File(...)) -> dict[str, str]:
    original_name = Path(video.filename or "").name
    suffix = Path(original_name).suffix.lower()
    if not original_name or suffix not in SUPPORTED_VIDEO_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_VIDEO_EXTENSIONS))
        raise HTTPException(status_code=415, detail=f"Supported video formats: {supported}")

    scene_id, scene_dir = create_scene_layout(DATASET_ROOT)
    stored_path = scene_dir / "input" / f"capture{suffix}"
    size_limit = CONFIG.upload_size_limit_mb * 1024 * 1024
    bytes_written = 0

    try:
        with stored_path.open("xb") as destination:
            while chunk := await video.read(1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > size_limit:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload exceeds {CONFIG.upload_size_limit_mb} MB limit",
                    )
                destination.write(chunk)
    except HTTPException:
        stored_path.unlink(missing_ok=True)
        raise
    finally:
        await video.close()

    if bytes_written == 0:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded video is empty")

    try:
        # OpenCV inspection is sent to a worker so the event loop stays responsive.
        import asyncio

        await asyncio.get_running_loop().run_in_executor(_executor, inspect_video, stored_path)
    except (VideoError, ValueError) as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    manifest_relative = f"{scene_id}/metadata/capture_manifest.json"
    _set_job(
        scene_id,
        status="queued",
        scene_id=scene_id,
        manifest_location=manifest_relative,
    )
    _executor.submit(_run_capture, scene_id, scene_dir, stored_path, original_name)
    return {
        "scene_id": scene_id,
        "status": "queued",
        "manifest_location": manifest_relative,
    }


@app.post("/api/v1/captures/photos", status_code=status.HTTP_202_ACCEPTED)
async def create_photo_set(
    photos: list[UploadFile] = File(...),
    override_noncritical: bool = Form(False),
    profile: str = Form("auto"),
) -> dict[str, str]:
    try:
        resolve_processing_profile(profile)  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    scene_id, scene_dir = create_scene_layout(DATASET_ROOT)
    try:
        paths, names = await _store_image_uploads(photos, scene_dir)
    except Exception:
        shutil.rmtree(scene_dir, ignore_errors=True)
        raise
    _set_job(
        scene_id,
        scene_id=scene_id,
        capture_mode="photo_set",
        status="queued",
        current_stage="image_validation",
        manifest_location=f"{scene_id}/metadata/capture_manifest.json",
    )
    cancel_event = threading.Event()
    _job_cancel_events[scene_id] = cancel_event
    _executor.submit(_run_photo_set, scene_id, scene_dir, paths, names, override_noncritical, profile, cancel_event)
    return {"scene_id": scene_id, "status": "queued", "capture_mode": "photo_set", "profile": profile}


@app.post("/api/v1/captures/single", status_code=status.HTTP_202_ACCEPTED)
async def create_single_image(
    image: UploadFile = File(...),
    depth_exaggeration: float = Form(1.0),
    profile: str = Form("auto"),
) -> dict[str, str]:
    if not 0.25 <= depth_exaggeration <= 3.0:
        raise HTTPException(status_code=422, detail="depth_exaggeration must be between 0.25 and 3.0")
    try:
        resolve_processing_profile(profile)  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    scene_id, scene_dir = create_scene_layout(DATASET_ROOT)
    try:
        paths, names = await _store_image_uploads([image], scene_dir)
    except Exception:
        shutil.rmtree(scene_dir, ignore_errors=True)
        raise
    _set_job(
        scene_id,
        scene_id=scene_id,
        capture_mode="single_photo",
        status="queued",
        current_stage="image_validation",
        manifest_location=f"{scene_id}/metadata/single_image_manifest.json",
    )
    cancel_event = threading.Event()
    _job_cancel_events[scene_id] = cancel_event
    _executor.submit(_run_single_image, scene_id, scene_dir, paths[0], names[0], depth_exaggeration, profile, cancel_event)
    return {"scene_id": scene_id, "status": "queued", "capture_mode": "single_photo", "profile": profile}


@app.post("/api/v1/captures/{scene_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
def cancel_capture(scene_id: str) -> dict[str, str]:
    if not _valid_scene_id(scene_id):
        raise HTTPException(status_code=400, detail="Invalid scene identifier")
    event = _job_cancel_events.get(scene_id)
    if event is None:
        raise HTTPException(status_code=409, detail="This capture is not cancellable or is no longer running")
    event.set()
    _set_job(scene_id, status="cancelling", current_stage="cancellation_requested")
    return {"scene_id": scene_id, "status": "cancelling"}


@app.get("/api/v1/captures/{scene_id}")
def capture_status(scene_id: str) -> dict[str, Any]:
    if not scene_id.startswith("scene_") or not all(
        character.isalnum() or character in {"_", "-"} for character in scene_id
    ):
        raise HTTPException(status_code=400, detail="Invalid scene identifier")

    with _jobs_lock:
        job = _jobs.get(scene_id)
        if job is not None:
            return dict(job)

    metadata_dir = DATASET_ROOT / scene_id / "metadata"
    manifest_path = metadata_dir / "capture_manifest.json"
    single_manifest_path = metadata_dir / "single_image_manifest.json"
    if not manifest_path.is_file() and not single_manifest_path.is_file():
        raise HTTPException(status_code=404, detail="Capture job not found")

    import json

    selected_manifest = manifest_path if manifest_path.is_file() else single_manifest_path
    manifest = json.loads(selected_manifest.read_text(encoding="utf-8"))
    return {
        "scene_id": scene_id,
        "status": manifest["processing_status"],
        "capture_mode": manifest.get("capture_mode", "video"),
        "manifest_location": f"{scene_id}/metadata/{selected_manifest.name}",
        **({"accepted_frames": manifest["accepted_frames"]} if "accepted_frames" in manifest else {}),
        **({"rejected_frames": manifest["rejected_frames"]} if "rejected_frames" in manifest else {}),
        **({"error": manifest["error"]} if "error" in manifest else {}),
    }


def _valid_scene_id(scene_id: str) -> bool:
    return scene_id.startswith("scene_") and all(
        character.isalnum() or character in {"_", "-"} for character in scene_id
    )


class ReconstructScenePayload(BaseModel):
    profile: str | None = None


def _run_reconstruction(scene_id: str, scene_dir: Path, config: ReconstructionConfig | None = None) -> None:
    active_config = config or RECONSTRUCTION_CONFIG
    with _reconstruction_jobs_lock:
        _reconstruction_jobs[scene_id] = {
            "scene_id": scene_id,
            "status": "running",
            "profile": active_config.profile,
        }
    try:
        manifest = ColmapBackend(active_config).reconstruct(scene_dir)
        if manifest.get("processing_status") == "completed":
            reconstruction_manifest_file = scene_dir / "metadata" / "reconstruction_manifest.json"
            if reconstruction_manifest_file.is_file():
                import tempfile
                from spatialforge.scenes.assemble import assemble_reconstructed_scene
                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as cal:
                    json.dump(
                        {"matrix_row_major": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], "target_units": "scene_unit", "metric_scale_status": "arbitrary"},
                        cal,
                    )
                    cal_path = cal.name
                try:
                    assemble_reconstructed_scene(scene_dir, cal_path, overwrite=True)
                finally:
                    Path(cal_path).unlink(missing_ok=True)

                # Rigorously validate the assembled viewer pack
                validation = validate_viewer_pack(scene_dir)
                if not validation.is_valid:
                    errors_str = "; ".join(validation.errors)
                    raise RuntimeError(f"Viewer pack validation failed: {errors_str}")

        result = {
            "scene_id": scene_id,
            "status": manifest["processing_status"],
            "current_stage": manifest.get("current_stage"),
            "stage_timings": manifest.get("stage_timings", {}),
            "manifest_location": f"{scene_id}/metadata/reconstruction_manifest.json",
            "metrics": manifest.get("metrics", {}),
        }
    except Exception as exc:
        result = {
            "scene_id": scene_id,
            "status": "failed",
            "manifest_location": f"{scene_id}/metadata/reconstruction_manifest.json",
            "error": str(exc),
        }
    with _reconstruction_jobs_lock:
        _reconstruction_jobs[scene_id] = result


@app.post("/api/v1/scenes/{scene_id}/reconstruct", status_code=status.HTTP_202_ACCEPTED)
def reconstruct_scene(scene_id: str, payload: ReconstructScenePayload | None = None) -> dict[str, str]:
    if not _valid_scene_id(scene_id):
        raise HTTPException(status_code=400, detail="Invalid scene identifier")
    scene_dir = (DATASET_ROOT / scene_id).resolve()
    try:
        scene_dir.relative_to(DATASET_ROOT.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid scene path") from exc

    effective_config = (
        resolve_reconstruction_profile(RECONSTRUCTION_CONFIG, payload.profile)
        if payload and payload.profile
        else RECONSTRUCTION_CONFIG
    )

    try:
        validate_scene(scene_dir, effective_config.minimum_images)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with _reconstruction_jobs_lock:
        existing_job = _reconstruction_jobs.get(scene_id)
        if existing_job and existing_job.get("status") in {"pending", "running"}:
            raise HTTPException(status_code=409, detail="Reconstruction is already in progress")

        manifest_path = scene_dir / "metadata" / "reconstruction_manifest.json"
        if manifest_path.is_file():
            import json

            existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing_manifest.get("processing_status") == "completed":
                raise HTTPException(status_code=409, detail="A completed reconstruction already exists")

        result = {
            "scene_id": scene_id,
            "status": "pending",
            "manifest_location": f"{scene_id}/metadata/reconstruction_manifest.json",
            "profile": effective_config.profile,
        }
        _reconstruction_jobs[scene_id] = result
    _reconstruction_executor.submit(_run_reconstruction, scene_id, scene_dir, effective_config)
    return result


@app.get("/api/v1/scenes/{scene_id}/reconstruction")
def reconstruction_status(scene_id: str) -> dict[str, Any]:
    if not _valid_scene_id(scene_id):
        raise HTTPException(status_code=400, detail="Invalid scene identifier")
    manifest_path = DATASET_ROOT / scene_id / "metadata" / "reconstruction_manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    with _reconstruction_jobs_lock:
        job = _reconstruction_jobs.get(scene_id)
        if job is not None:
            combined = dict(job)
            if manifest:
                combined["current_stage"] = manifest.get("current_stage")
                combined["stage_timings"] = manifest.get("stage_timings", {})
                if "metrics" in manifest and not combined.get("metrics"):
                    combined["metrics"] = manifest["metrics"]
            return combined

    if not manifest_path.is_file():
        raise HTTPException(status_code=404, detail="Reconstruction job not found")

    return {
        "scene_id": scene_id,
        "status": manifest.get("processing_status", "unknown"),
        "current_stage": manifest.get("current_stage"),
        "stage_timings": manifest.get("stage_timings", {}),
        "manifest_location": f"{scene_id}/metadata/reconstruction_manifest.json",
        "metrics": manifest.get("metrics", {}),
        **({"error": manifest["error"]} if "error" in manifest else {}),
    }


def _scene_store() -> SceneStore:
    return SceneStore(DATASET_ROOT)


def _navigation_service() -> NavigationService:
    return NavigationService(_scene_store())


def _navigation_error(exc: Exception) -> HTTPException:
    message = str(exc)
    if isinstance(exc, SceneNotFoundError):
        return HTTPException(status_code=404, detail=message)
    if "not found" in message.lower():
        return HTTPException(status_code=404, detail=message)
    if "duplicate" in message.lower():
        return HTTPException(status_code=409, detail=message)
    return HTTPException(status_code=422, detail=message)


def _scene_summary(manifest) -> dict[str, Any]:
    scene_dir = DATASET_ROOT / manifest.scene_id
    created_at = None
    if scene_dir.is_dir():
        import datetime
        mtime = scene_dir.stat().st_mtime
        created_at = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc).isoformat()
    primary = next((a for a in manifest.assets if a.role == "primary_visual"), None)
    return {
        "scene_id": manifest.scene_id,
        "scene_name": manifest.scene_name,
        "description": manifest.description,
        "processing_status": manifest.processing_status,
        "synthetic_demo": manifest.synthetic_demo,
        "asset_types": sorted({asset.type for asset in manifest.assets}),
        "primary_asset_type": primary.type if primary else None,
        "backend": manifest.reconstruction.backend,
        "metric_scale_status": manifest.units.metric_scale_status,
        "created_at": created_at,
        "manifest_url": f"/api/v1/scenes/{manifest.scene_id}/manifest",
    }


@app.patch("/api/v1/scenes/{scene_id}/rename")
def rename_scene(scene_id: str, payload: dict[str, str]) -> dict[str, Any]:
    if not _valid_scene_id(scene_id):
        raise HTTPException(status_code=400, detail="Invalid scene identifier")
    name = payload.get("scene_name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="scene_name cannot be empty")
    try:
        updated = _scene_store().update_scene_name(scene_id, name)
        return _scene_summary(updated)
    except SceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SceneStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/scenes/{scene_id}/export")
def export_scene(scene_id: str) -> FileResponse:
    if not _valid_scene_id(scene_id):
        raise HTTPException(status_code=400, detail="Invalid scene identifier")
    scene_dir = (DATASET_ROOT / scene_id).resolve()
    try:
        scene_dir.relative_to(DATASET_ROOT.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid scene path") from exc
    if not scene_dir.is_dir():
        raise HTTPException(status_code=404, detail="Scene not found")
    archive_dir = DATASET_ROOT / ".exports"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{scene_id}.sfscene"
    archive_path.unlink(missing_ok=True)
    try:
        export_scene_package(scene_dir, archive_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to export scene package: {exc}") from exc
    return FileResponse(archive_path, media_type="application/octet-stream", filename=f"{scene_id}.sfscene")


@app.get("/api/v1/scenes")
def list_scenes() -> dict[str, Any]:
    manifests = _scene_store().list_manifests()
    return {"scenes": [_scene_summary(manifest) for manifest in manifests], "count": len(manifests)}


@app.post("/api/v1/scenes/import", status_code=status.HTTP_201_CREATED)
async def import_scene(scene_package: UploadFile = File(...)) -> dict[str, Any]:
    """Validate and atomically import a user-provided portable scene package."""
    import asyncio

    original_name = Path(scene_package.filename or "").name
    if not original_name or Path(original_name).suffix.lower() != ".sfscene":
        raise HTTPException(status_code=415, detail="A .sfscene package is required")
    size_limit = CONFIG.upload_size_limit_mb * 1024 * 1024
    bytes_written = 0
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="spatialforge-import-", suffix=".sfscene", delete=False) as temporary:
            temporary_path = Path(temporary.name)
            while chunk := await scene_package.read(1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > size_limit:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Scene package exceeds {CONFIG.upload_size_limit_mb} MB limit",
                    )
                temporary.write(chunk)
        if bytes_written == 0:
            raise HTTPException(status_code=400, detail="Uploaded scene package is empty")
        imported = await asyncio.get_running_loop().run_in_executor(
            _executor, import_scene_package, temporary_path, DATASET_ROOT
        )
        manifest = _scene_store().load_manifest(imported.name)
        return _scene_summary(manifest)
    except ScenePackageError as exc:
        status_code = 409 if "already exists" in str(exc).lower() else 422
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    finally:
        await scene_package.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


@app.get("/api/v1/scenes/{scene_id}")
def get_scene(scene_id: str) -> dict[str, Any]:
    try:
        return _scene_summary(_scene_store().load_manifest(scene_id))
    except SceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SceneManifestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SceneStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/scenes/{scene_id}/manifest")
def get_scene_manifest(scene_id: str) -> dict[str, Any]:
    try:
        return _scene_store().load_manifest(scene_id).model_dump(mode="json")
    except SceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SceneManifestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SceneStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/scenes/{scene_id}/assets/{asset_path:path}")
def get_scene_asset(scene_id: str, asset_path: str) -> FileResponse:
    try:
        asset = _scene_store().resolve_asset(scene_id, asset_path)
    except SceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SceneManifestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SceneAssetError as exc:
        status_code = 404 if "missing" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    except SceneStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(asset.path, media_type=asset.definition.mime_type, filename=asset.path.name)


@app.get("/api/v1/scenes/{scene_id}/pois")
def list_scene_pois(
    scene_id: str,
    q: str = Query(default="", max_length=120),
    category: str = Query(default="", max_length=60),
) -> dict[str, Any]:
    try:
        manifest = _scene_store().load_manifest(scene_id)
        if not any(item.type == "poi_metadata" for item in manifest.assets):
            return {"points": [], "count": 0}
        points = _navigation_service().list_pois(scene_id, q, category)
        return {"points": [point.model_dump(mode="json") for point in points], "count": len(points)}
    except (NavigationServiceError, SceneStoreError) as exc:
        raise _navigation_error(exc) from exc


@app.get("/api/v1/scenes/{scene_id}/pois/{poi_id}")
def get_scene_poi(scene_id: str, poi_id: str) -> dict[str, Any]:
    try:
        return _navigation_service().get_poi(scene_id, poi_id).model_dump(mode="json")
    except (NavigationServiceError, SceneStoreError) as exc:
        raise _navigation_error(exc) from exc


@app.post("/api/v1/scenes/{scene_id}/pois", status_code=status.HTTP_201_CREATED)
def create_scene_poi(scene_id: str, poi: POI) -> dict[str, Any]:
    try:
        return _navigation_service().create_poi(scene_id, poi).model_dump(mode="json")
    except (NavigationServiceError, SceneStoreError) as exc:
        raise _navigation_error(exc) from exc


@app.put("/api/v1/scenes/{scene_id}/pois/{poi_id}")
def update_scene_poi(scene_id: str, poi_id: str, poi: POI) -> dict[str, Any]:
    try:
        return _navigation_service().update_poi(scene_id, poi_id, poi).model_dump(mode="json")
    except (NavigationServiceError, SceneStoreError) as exc:
        raise _navigation_error(exc) from exc


@app.delete("/api/v1/scenes/{scene_id}/pois/{poi_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scene_poi(scene_id: str, poi_id: str) -> Response:
    try:
        _navigation_service().delete_poi(scene_id, poi_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except (NavigationServiceError, SceneStoreError) as exc:
        raise _navigation_error(exc) from exc


@app.post("/api/v1/scenes/{scene_id}/routes")
def create_scene_route(scene_id: str, route_request: RouteRequest) -> dict[str, Any]:
    try:
        return _navigation_service().route(scene_id, route_request).model_dump(mode="json")
    except (NavigationServiceError, SceneStoreError) as exc:
        raise _navigation_error(exc) from exc


@app.get("/api/v1/pipeline/jobs")
def list_pipeline_jobs() -> dict[str, Any]:
    jobs = list_scene_jobs(DATASET_ROOT)
    return {"jobs": jobs, "count": len(jobs)}


@app.get("/api/v1/pipeline/jobs/{scene_id}")
def get_pipeline_job(scene_id: str) -> dict[str, Any]:
    try:
        scene = _scene_store().scene_dir(scene_id)
        return inspect_scene_job(scene)
    except SceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (SceneStoreError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/pipeline/jobs/{scene_id}/analyze-capture")
def analyze_pipeline_capture(scene_id: str) -> dict[str, Any]:
    try:
        scene = _scene_store().scene_dir(scene_id)
        if (scene / "metadata" / "single_image_manifest.json").is_file() or (scene / "assets" / "single-photo-depth-mesh.ply").is_file():
            raise HTTPException(
                status_code=400,
                detail="Capture analysis evaluates multi-view overlap for COLMAP and is not needed for single-photo digital twins, which are already completed."
            )
        if not (scene / "metadata" / "capture_manifest.json").is_file():
            raise HTTPException(
                status_code=400,
                detail="Capture analysis requires an extracted multi-view capture manifest (from a video or photo set). Single-photo scenes do not require capture analysis."
            )
        write_capture_readiness_report(scene)
        return {"report": analyze_capture_readiness(scene), "job": inspect_scene_job(scene)}
    except HTTPException:
        raise
    except SceneNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (SceneStoreError, CaptureReadinessError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/scenes/{scene_id}/validate-viewer-pack")
def get_scene_viewer_pack_validation(scene_id: str) -> dict[str, Any]:
    if not _valid_scene_id(scene_id):
        raise HTTPException(status_code=400, detail="Invalid scene identifier")
    scene_dir = (DATASET_ROOT / scene_id).resolve()
    try:
        scene_dir.relative_to(DATASET_ROOT.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid scene path") from exc
    if not scene_dir.is_dir():
        raise HTTPException(status_code=404, detail="Scene not found")
    validation = validate_viewer_pack(scene_dir)
    return validation.to_dict()


@app.get("/api/v1/scenes/{scene_id}/quality-report")
def get_scene_quality_report(scene_id: str) -> dict[str, Any]:
    if not _valid_scene_id(scene_id):
        raise HTTPException(status_code=400, detail="Invalid scene identifier")
    scene_dir = (DATASET_ROOT / scene_id).resolve()
    try:
        scene_dir.relative_to(DATASET_ROOT.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid scene path") from exc
    if not scene_dir.is_dir():
        raise HTTPException(status_code=404, detail="Scene not found")
    report = generate_quality_report(scene_dir)
    return report.to_dict()


@app.delete("/api/v1/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scene(scene_id: str) -> Response:
    if not _valid_scene_id(scene_id):
        raise HTTPException(status_code=400, detail="Invalid scene identifier")
    scene_dir = (DATASET_ROOT / scene_id).resolve()
    try:
        scene_dir.relative_to(DATASET_ROOT.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid scene path") from exc
    if not scene_dir.is_dir():
        raise HTTPException(status_code=404, detail="Scene not found")
    import shutil
    try:
        shutil.rmtree(scene_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete scene: {exc}") from exc
    with _reconstruction_jobs_lock:
        _reconstruction_jobs.pop(scene_id, None)
    with _jobs_lock:
        _jobs.pop(scene_id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete("/api/v1/pipeline/jobs/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pipeline_job(scene_id: str) -> Response:
    return delete_scene(scene_id)


@app.post("/api/v1/pipeline/jobs/clear-history")
def clear_pipeline_history() -> dict[str, Any]:
    deleted: list[str] = []
    if not DATASET_ROOT.is_dir():
        return {"deleted": deleted, "count": 0}
    import shutil
    for item in DATASET_ROOT.iterdir():
        if not item.is_dir() or not item.name.startswith("scene_"):
            continue
        try:
            job = inspect_scene_job(item)
            has_viewer_manifest = (item / "metadata" / "scene_manifest.json").is_file()
            # Clear failed or incomplete jobs that are not currently running and have no completed viewer manifest
            if not has_viewer_manifest and job.get("status") in {"failed", "invalid", "cancelled", "awaiting_reconstruction"}:
                shutil.rmtree(item)
                deleted.append(item.name)
        except Exception:
            continue
    with _jobs_lock:
        for sid in deleted:
            _jobs.pop(sid, None)
    return {"deleted": deleted, "count": len(deleted)}


@app.post("/api/v1/pipeline/jobs/clear-completed-jobs")
def clear_completed_jobs() -> dict[str, Any]:
    """Clears in-memory completed jobs without removing reconstructed scene assets."""
    cleared: list[str] = []
    with _jobs_lock:
        to_remove = [k for k, v in _jobs.items() if v.get("status") in {"ready", "completed", "ready_for_reconstruction"}]
        for k in to_remove:
            _jobs.pop(k, None)
            cleared.append(k)
    with _reconstruction_jobs_lock:
        to_remove_rec = [k for k, v in _reconstruction_jobs.items() if v.get("status") in {"completed"}]
        for k in to_remove_rec:
            _reconstruction_jobs.pop(k, None)
    return {"cleared": cleared, "count": len(cleared)}


@app.get("/api/v1/system/diagnostics")
def get_system_diagnostics() -> dict[str, Any]:
    """Returns platform, memory, models, COLMAP, and storage diagnostics."""
    import platform
    mem = memory_snapshot() or {"total_mb": 16384, "available_mb": 8192, "load_percent": 50.0}

    # Model checks
    depth_model_path = Path(os.getenv("SPATIALFORGE_DEPTH_MODEL", PROJECT_ROOT / "models" / "depth_anything_v2_small.onnx"))
    depth_model_ok = depth_model_path.is_file()
    depth_model_size_mb = round(depth_model_path.stat().st_size / (1024 * 1024), 2) if depth_model_ok else 0.0

    # COLMAP checks
    colmap_path = os.getenv("SPATIALFORGE_COLMAP_PATH", "colmap")
    colmap_found = False
    if Path(colmap_path).is_file():
        colmap_found = True
    else:
        import shutil
        colmap_found = shutil.which(colmap_path) is not None

    # Storage statistics
    total_scenes = 0
    total_bytes = 0
    if DATASET_ROOT.is_dir():
        for item in DATASET_ROOT.iterdir():
            if item.is_dir() and item.name.startswith("scene_"):
                total_scenes += 1
                for f in item.rglob("*"):
                    if f.is_file():
                        total_bytes += f.stat().st_size

    return {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor() or "Intel Core Processor",
            "execution_mode": "CPU-first (Intel integrated graphics compatible, No CUDA required)",
        },
        "memory": mem,
        "models": {
            "depth_anything_v2": {
                "name": "Depth Anything V2 Small ONNX",
                "path": str(depth_model_path),
                "available": depth_model_ok,
                "size_mb": depth_model_size_mb,
                "runtime": "ONNX Runtime (CPUExecutionProvider)",
            }
        },
        "colmap": {
            "configured_path": str(colmap_path),
            "available": colmap_found,
            "mode": "CPU Sparse Bundle Adjustment",
        },
        "reconstruction": {
            "active_profile": RECONSTRUCTION_CONFIG.profile,
            "supported_profiles": ["cpu_sparse", "external_gpu_dense"],
            "colmap_available": colmap_found,
            "colmap_path": str(colmap_path),
            "colmap_mode": "CPU Sparse Bundle Adjustment",
            "cuda_available": False,
            "dense_stereo_supported": False,
            "num_threads": RECONSTRUCTION_CONFIG.num_threads,
            "max_image_size": RECONSTRUCTION_CONFIG.max_image_size,
        },
        "storage": {
            "dataset_root": str(DATASET_ROOT),
            "total_scenes": total_scenes,
            "total_size_mb": round(total_bytes / (1024 * 1024), 2),
        },
        "concurrency": {
            "worker_count": CONFIG.worker_count,
            "reconstruction_workers": 1,
        },
    }
