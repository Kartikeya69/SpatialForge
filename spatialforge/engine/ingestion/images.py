"""Real-image validation and photo-set preparation for reconstruction."""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Sequence

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from spatialforge import __version__
from spatialforge.engine.processing_profiles import (
    ProcessingCancelled,
    ProcessingProfileName,
    resolve_processing_profile,
    validate_memory_headroom,
)

from .pipeline import CaptureConfig, _write_manifest
from .quality import evaluate_frame

SUPPORTED_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".heic", ".heif"})


class ImageIngestionError(ValueError):
    """Raised when a user-supplied image cannot be decoded or normalized."""


def decode_oriented_image(path: str | Path) -> np.ndarray:
    """Decode an image and apply its EXIF orientation without changing the source file."""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Image file does not exist: {source}")
    if source.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ImageIngestionError(f"Unsupported image format: {source.suffix or '<none>'}")
    try:
        with Image.open(source) as opened:
            oriented = ImageOps.exif_transpose(opened)
            rgb = np.asarray(oriented.convert("RGB"))
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        if source.suffix.lower() in {".heic", ".heif"}:
            raise ImageIngestionError(
                "HEIC/HEIF decoding is unavailable in this Python image-decoder build; "
                "convert the file to JPEG/PNG or install a compatible Pillow HEIF plugin"
            ) from exc
        raise ImageIngestionError(f"Image is corrupt or unreadable: {source.name}") from exc
    if rgb.size == 0 or rgb.ndim != 3:
        raise ImageIngestionError(f"Image decoded to invalid pixel data: {source.name}")
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


class PhotoSetPipeline:
    """Normalize a genuine overlapping photo collection into COLMAP-ready JPEGs."""

    def __init__(self, config: CaptureConfig) -> None:
        config.validate()
        self.config = config

    def process(
        self,
        source_paths: Sequence[str | Path],
        scene_dir: str | Path,
        *,
        original_filenames: Sequence[str] | None = None,
        override_noncritical: bool = False,
        profile: ProcessingProfileName = "auto",
        is_cancelled: Callable[[], bool] | None = None,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        scene = Path(scene_dir).expanduser().resolve()
        if not source_paths:
            raise ImageIngestionError("At least one uploaded photograph is required")
        names = list(original_filenames or [Path(path).name for path in source_paths])
        if len(names) != len(source_paths):
            raise ValueError("original_filenames must match source_paths")
        active_profile = resolve_processing_profile(profile)
        if len(source_paths) > active_profile.max_photo_count:
            raise ImageIngestionError(
                f"The {active_profile.name} profile accepts at most {active_profile.max_photo_count} photos; "
                f"received {len(source_paths)}. Split the capture or choose a larger profile."
            )
        memory = validate_memory_headroom(active_profile)
        for child in ("input", "images", "metadata", "logs"):
            (scene / child).mkdir(parents=True, exist_ok=True)

        manifest_path = scene / "metadata" / "capture_manifest.json"
        manifest: dict[str, Any] = {
            "scene_id": scene.name,
            "capture_mode": "photo_set",
            "original_input_filenames": names,
            "video_metadata": None,
            "extraction_config": {"quality": self.config.quality_config().__dict__, "jpeg_quality": self.config.jpeg_quality},
            "total_frames_sampled": len(source_paths),
            "accepted_frames": 0,
            "rejected_frames": 0,
            "rejection_reasons": {},
            "images": [],
            "rejections": [],
            "processing_duration_seconds": 0.0,
            "pipeline_version": __version__,
            "processing_status": "processing",
            "warnings": [],
            "override_noncritical_filtering": override_noncritical,
            "processing_profile": active_profile.to_dict(),
            "memory_at_start": memory,
        }
        _write_manifest(manifest_path, manifest)
        reasons: Counter[str] = Counter()
        exported_paths: list[Path] = []
        try:
            # Imported here to avoid a module cycle: the analyzer deliberately reuses
            # this module's EXIF-aware decoder.
            from .photo_analysis import analyze_photo_set, write_photo_analysis

            analysis = analyze_photo_set(
                source_paths,
                original_filenames=names,
                max_pairs=active_profile.max_match_pairs,
                analysis_width=active_profile.analysis_width,
                orb_features=active_profile.orb_features,
                max_source_megapixels=active_profile.max_source_megapixels,
                is_cancelled=is_cancelled,
                on_progress=on_progress,
            )
            analysis_path = write_photo_analysis(analysis, scene / "metadata" / "photo_quality_report.json")
            manifest["quality_report"] = analysis_path.relative_to(scene).as_posix()
            manifest["connectivity_summary"] = analysis["connectivity"]
            manifest["warnings"].extend(analysis["recommendations"])
            exclusions = {
                int(item["index"]): str(item["reason"])
                for item in analysis["selection"]["recommended_exclusions"]
            }
            analysis_images = {int(item["index"]): item for item in analysis["images"]}
            basic_quality = replace(
                self.config.quality_config(),
                enable_blur_filter=False,
                enable_duplicate_filter=False,
            )
            for index, (source_value, original_name) in enumerate(zip(source_paths, names, strict=True), start=1):
                if is_cancelled and is_cancelled():
                    raise ProcessingCancelled("Photo-set processing was cancelled")
                source = Path(source_value).expanduser().resolve()
                image = decode_oriented_image(source)
                initial = evaluate_frame(image, basic_quality)
                image_analysis = analysis_images[index - 1]
                rejection_reasons = list(initial.rejection_reasons)
                quality_flags = set(image_analysis["quality_flags"])
                if self.config.enable_blur_filter and "adaptive_blur_outlier" in quality_flags and not override_noncritical:
                    rejection_reasons.append("adaptive_blur_outlier")
                recommended_exclusion = exclusions.get(index - 1)
                if recommended_exclusion == "exact_duplicate":
                    # Preserve the capture-manifest vocabulary used by v0.1 clients;
                    # the linked quality report retains the stricter exact-duplicate evidence.
                    rejection_reasons.append("near_duplicate")
                elif (
                    self.config.enable_duplicate_filter
                    and recommended_exclusion == "near_duplicate_with_redundant_viewpoint"
                    and not override_noncritical
                ):
                    rejection_reasons.append(recommended_exclusion)
                if rejection_reasons:
                    manifest["rejected_frames"] += 1
                    reasons.update(rejection_reasons)
                    manifest["rejections"].append({
                        "source_index": index - 1,
                        "original_filename": original_name,
                        "reasons": rejection_reasons,
                        "blur_score": round(initial.blur_score, 3),
                        "quality_flags": sorted(quality_flags),
                    })
                    continue
                output_name = f"photo_{manifest['accepted_frames'] + 1:06d}.jpg"
                output = scene / "images" / output_name
                if not cv2.imwrite(str(output), initial.image, [cv2.IMWRITE_JPEG_QUALITY, self.config.jpeg_quality]):
                    raise OSError(f"Failed to write normalized photograph: {output}")
                exported_paths.append(output)
                manifest["accepted_frames"] += 1
                manifest["images"].append({
                    "path": output.relative_to(scene).as_posix(),
                    "source_index": index - 1,
                    "original_filename": original_name,
                    "blur_score": round(initial.blur_score, 3),
                    "quality_flags": sorted(quality_flags),
                    "estimated_focal_pixels": image_analysis.get("estimated_focal_pixels"),
                    "camera_make": image_analysis.get("camera", {}).get("make"),
                    "camera_model": image_analysis.get("camera", {}).get("model"),
                })
                if on_progress:
                    on_progress("image_export", index, len(source_paths))
            manifest["rejection_reasons"] = dict(sorted(reasons.items()))
            if manifest["accepted_frames"] == 0:
                raise ImageIngestionError("No photographs passed quality validation")
            if manifest["accepted_frames"] < 3:
                manifest["warnings"].append(
                    "Fewer than three images passed validation; multi-view reconstruction cannot start."
                )
            elif manifest["accepted_frames"] < 15:
                manifest["warnings"].append(
                    "The set may be too small for a robust indoor reconstruction; overlap must be verified by COLMAP."
                )
            manifest["processing_status"] = "completed"
        except Exception as exc:
            manifest["processing_status"] = "cancelled" if isinstance(exc, ProcessingCancelled) else "failed"
            manifest["error"] = str(exc)
            for output in exported_paths:
                output.unlink(missing_ok=True)
            manifest["partial_outputs_removed"] = len(exported_paths)
            manifest["accepted_frames"] = 0
            manifest["images"] = []
            raise
        finally:
            manifest["processing_duration_seconds"] = round(time.perf_counter() - started, 6)
            _write_manifest(manifest_path, manifest)
        return manifest


def stage_uploaded_images(
    uploads: Sequence[tuple[str, bytes]], scene_dir: str | Path
) -> tuple[list[Path], list[str]]:
    """Persist uploaded bytes with generated names while retaining original names separately."""
    scene = Path(scene_dir).expanduser().resolve()
    staged: list[Path] = []
    originals: list[str] = []
    try:
        for index, (original_name, payload) in enumerate(uploads, start=1):
            safe_name = Path(original_name).name
            suffix = Path(safe_name).suffix.lower()
            if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
                raise ImageIngestionError(f"Unsupported image format: {suffix or '<none>'}")
            if not payload:
                raise ImageIngestionError(f"Uploaded image is empty: {safe_name}")
            destination = scene / "input" / f"upload_{index:06d}{suffix}"
            destination.write_bytes(payload)
            staged.append(destination)
            originals.append(safe_name)
    except Exception:
        for path in staged:
            path.unlink(missing_ok=True)
        raise
    return staged, originals
