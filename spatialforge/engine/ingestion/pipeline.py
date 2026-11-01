"""Orchestration for converting a capture video into COLMAP-ready images."""

from __future__ import annotations

import json
import logging
import shutil
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import yaml

from spatialforge import __version__

from .quality import QualityConfig, evaluate_frame
from .video import inspect_video, iter_sampled_frames, validate_video_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaptureConfig:
    sample_fps: float = 2.0
    blur_threshold: float = 80.0
    min_width: int = 640
    min_height: int = 480
    max_width: int | None = 1920
    duplicate_threshold: float = 0.995
    enable_blur_filter: bool = True
    enable_duplicate_filter: bool = True
    jpeg_quality: int = 92
    dataset_root: str = "datasets"
    upload_size_limit_mb: int = 1024
    worker_count: int = 2
    max_extracted_frames: int | None = 120

    def validate(self) -> None:
        if self.sample_fps <= 0:
            raise ValueError("sample_fps must be greater than zero")
        if self.max_extracted_frames is not None and self.max_extracted_frames <= 0:
            raise ValueError("max_extracted_frames must be greater than zero")
        QualityConfig(
            blur_threshold=self.blur_threshold,
            min_width=self.min_width,
            min_height=self.min_height,
            max_width=self.max_width,
            duplicate_threshold=self.duplicate_threshold,
            enable_blur_filter=self.enable_blur_filter,
            enable_duplicate_filter=self.enable_duplicate_filter,
        ).validate()
        if not 1 <= self.jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be between 1 and 100")
        if self.upload_size_limit_mb <= 0:
            raise ValueError("upload_size_limit_mb must be greater than zero")
        if not 1 <= self.worker_count <= 16:
            raise ValueError("worker_count must be between 1 and 16")

    def quality_config(self) -> QualityConfig:
        return QualityConfig(
            blur_threshold=self.blur_threshold,
            min_width=self.min_width,
            min_height=self.min_height,
            max_width=self.max_width,
            duplicate_threshold=self.duplicate_threshold,
            enable_blur_filter=self.enable_blur_filter,
            enable_duplicate_filter=self.enable_duplicate_filter,
        )


def load_capture_config(path: str | Path) -> CaptureConfig:
    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Capture configuration not found: {config_path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Capture configuration must be a YAML mapping")
    unknown = set(raw) - set(CaptureConfig.__dataclass_fields__)
    if unknown:
        raise ValueError(f"Unknown capture configuration values: {', '.join(sorted(unknown))}")
    config = CaptureConfig(**raw)
    config.validate()
    return config


def generate_scene_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"scene_{timestamp}_{uuid.uuid4().hex[:10]}"


def create_scene_layout(dataset_root: str | Path, scene_id: str | None = None) -> tuple[str, Path]:
    root = Path(dataset_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    identifier = scene_id or generate_scene_id()
    if not identifier.startswith("scene_") or not all(
        character.isalnum() or character in {"_", "-"} for character in identifier
    ):
        raise ValueError("Invalid scene identifier")
    scene_dir = root / identifier
    scene_dir.mkdir(parents=False, exist_ok=False)
    for child in ("input", "images", "metadata", "logs"):
        (scene_dir / child).mkdir()
    return identifier, scene_dir


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    temporary.replace(path)


def _append_job_event(scene_dir: Path, event: str, **values: Any) -> None:
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        **values,
    }
    with (scene_dir / "logs" / "capture.jsonl").open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, separators=(",", ":")) + "\n")


class CapturePipeline:
    def __init__(self, config: CaptureConfig) -> None:
        config.validate()
        self.config = config

    def process(
        self,
        input_path: str | Path,
        dataset_root: str | Path | None = None,
        *,
        scene_id: str | None = None,
        existing_scene_dir: str | Path | None = None,
        copy_input: bool = True,
        original_filename: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        source = validate_video_path(input_path)
        root = Path(dataset_root or self.config.dataset_root)

        if existing_scene_dir is None:
            identifier, scene_dir = create_scene_layout(root, scene_id)
        else:
            scene_dir = Path(existing_scene_dir).resolve()
            identifier = scene_id or scene_dir.name
            if scene_dir.name != identifier:
                raise ValueError("scene_id does not match existing scene directory")
            for child in ("input", "images", "metadata", "logs"):
                (scene_dir / child).mkdir(parents=True, exist_ok=True)

        manifest_path = scene_dir / "metadata" / "capture_manifest.json"
        manifest: dict[str, Any] = {
            "scene_id": identifier,
            "capture_mode": "video",
            "original_input_filename": original_filename or source.name,
            "video_metadata": None,
            "extraction_config": asdict(self.config),
            "total_frames_sampled": 0,
            "accepted_frames": 0,
            "rejected_frames": 0,
            "rejection_reasons": {},
            "images": [],
            "rejections": [],
            "processing_duration_seconds": 0.0,
            "pipeline_version": __version__,
            "processing_status": "processing",
        }
        _write_manifest(manifest_path, manifest)
        _append_job_event(scene_dir, "capture_started", scene_id=identifier, input=source.name)
        logger.info("capture_started", extra={"scene_id": identifier, "input": source.name})

        try:
            stored_input = scene_dir / "input" / source.name
            if copy_input:
                if stored_input.exists():
                    raise FileExistsError(f"Input already exists in scene: {stored_input}")
                shutil.copy2(source, stored_input)
            else:
                stored_input = source

            metadata = inspect_video(stored_input)
            manifest["video_metadata"] = metadata.to_dict()
            previous_fingerprint = None
            reasons = Counter()

            for sampled in iter_sampled_frames(stored_input, self.config.sample_fps, metadata):
                if self.config.max_extracted_frames is not None and manifest["accepted_frames"] >= self.config.max_extracted_frames:
                    manifest["warnings"] = manifest.get("warnings", [])
                    manifest["warnings"].append(
                        f"Bounded capture frame selection reached max limit of {self.config.max_extracted_frames} frames."
                    )
                    break
                manifest["total_frames_sampled"] += 1
                result = evaluate_frame(
                    sampled.image,
                    self.config.quality_config(),
                    previous_accepted_fingerprint=previous_fingerprint,
                )
                if result.accepted:
                    output_name = f"frame_{manifest['accepted_frames'] + 1:06d}.jpg"
                    output_path = scene_dir / "images" / output_name
                    written = cv2.imwrite(
                        str(output_path),
                        result.image,
                        [cv2.IMWRITE_JPEG_QUALITY, self.config.jpeg_quality],
                    )
                    if not written:
                        raise OSError(f"Failed to write frame: {output_path}")
                    previous_fingerprint = result.fingerprint
                    manifest["accepted_frames"] += 1
                    manifest["images"].append(
                        {
                            "path": output_path.relative_to(scene_dir).as_posix(),
                            "source_frame_index": sampled.source_index,
                            "timestamp_seconds": round(sampled.timestamp_seconds, 6),
                            "blur_score": round(result.blur_score, 3),
                        }
                    )
                else:
                    manifest["rejected_frames"] += 1
                    reasons.update(result.rejection_reasons)
                    manifest["rejections"].append(
                        {
                            "source_frame_index": sampled.source_index,
                            "timestamp_seconds": round(sampled.timestamp_seconds, 6),
                            "reasons": list(result.rejection_reasons),
                            "blur_score": round(result.blur_score, 3),
                            "duplicate_similarity": result.duplicate_similarity,
                        }
                    )

            manifest["rejection_reasons"] = dict(sorted(reasons.items()))
            if manifest["accepted_frames"] == 0:
                raise ValueError(
                    "No frames passed quality filtering. Lower thresholds or inspect capture quality."
                )

            manifest["processing_status"] = "completed"
            _append_job_event(
                scene_dir,
                "capture_completed",
                scene_id=identifier,
                accepted_frames=manifest["accepted_frames"],
                rejected_frames=manifest["rejected_frames"],
            )
            logger.info(
                "capture_completed",
                extra={"scene_id": identifier, "accepted_frames": manifest["accepted_frames"]},
            )
        except Exception as exc:
            manifest["processing_status"] = "failed"
            manifest["error"] = str(exc)
            _append_job_event(
                scene_dir,
                "capture_failed",
                scene_id=identifier,
                error=str(exc),
            )
            logger.exception("capture_failed", extra={"scene_id": identifier})
            raise
        finally:
            manifest["processing_duration_seconds"] = round(time.perf_counter() - started, 6)
            _write_manifest(manifest_path, manifest)

        manifest["manifest_path"] = manifest_path.relative_to(scene_dir).as_posix()
        return manifest
