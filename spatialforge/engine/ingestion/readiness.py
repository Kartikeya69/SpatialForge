"""Evidence-based capture readiness analysis for extracted image datasets."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean, median
from typing import Any

import cv2
import numpy as np


class CaptureReadinessError(RuntimeError):
    pass


def _pair_overlap(left: np.ndarray, right: np.ndarray) -> dict[str, float | int | None]:
    detector = cv2.ORB_create(nfeatures=1200)
    left_points, left_descriptors = detector.detectAndCompute(left, None)
    right_points, right_descriptors = detector.detectAndCompute(right, None)
    if left_descriptors is None or right_descriptors is None or not left_points or not right_points:
        return {"good_matches": 0, "match_ratio": 0.0, "median_displacement_pixels": None}
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs = matcher.knnMatch(left_descriptors, right_descriptors, k=2)
    good = [first for first, second in pairs if first.distance < 0.75 * second.distance]
    displacements = [
        float(np.linalg.norm(np.asarray(left_points[item.queryIdx].pt) - np.asarray(right_points[item.trainIdx].pt)))
        for item in good
    ]
    return {
        "good_matches": len(good),
        "match_ratio": round(len(good) / max(1, min(len(left_points), len(right_points))), 4),
        "median_displacement_pixels": round(median(displacements), 3) if displacements else None,
    }


def analyze_capture_readiness(scene_dir: str | Path) -> dict[str, Any]:
    scene = Path(scene_dir).expanduser().resolve()
    manifest_path = scene / "metadata" / "capture_manifest.json"
    if not manifest_path.is_file():
        raise CaptureReadinessError("Capture manifest is missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise CaptureReadinessError(f"Capture manifest is invalid: {exc}") from exc

    accepted = int(manifest.get("accepted_frames", 0))
    capture_mode = manifest.get("capture_mode", "video")
    sampled = int(manifest.get("total_frames_sampled", 0))
    metadata = manifest.get("video_metadata") or {}
    duration = float(metadata.get("duration_seconds") or 0)
    image_records = manifest.get("images") or []
    if accepted != len(image_records):
        raise CaptureReadinessError("Accepted frame count does not match the image inventory")

    images: list[np.ndarray] = []
    brightness: list[float] = []
    for record in image_records:
        relative = Path(record.get("path", ""))
        path = (scene / relative).resolve()
        try:
            path.relative_to(scene)
        except ValueError as exc:
            raise CaptureReadinessError("Capture image path escapes the scene directory") from exc
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise CaptureReadinessError(f"Capture image is missing or unreadable: {relative.as_posix()}")
        images.append(image)
        brightness.append(float(np.mean(image)))

    overlaps = [_pair_overlap(left, right) for left, right in zip(images, images[1:])]
    match_ratios = [float(item["match_ratio"]) for item in overlaps]
    displacements = [float(item["median_displacement_pixels"]) for item in overlaps if item["median_displacement_pixels"] is not None]
    sharpness = [float(record.get("blur_score", 0)) for record in image_records]
    accepted_ratio = accepted / sampled if sampled else 0.0

    findings: list[dict[str, str]] = []
    if accepted < 3:
        findings.append({"severity": "error", "code": "insufficient_multiview_images", "message": "At least three distinct views are required to start multi-view reconstruction."})
    elif accepted < 15:
        findings.append({"severity": "warning", "code": "small_image_set", "message": "The image set is small for an indoor scene; COLMAP registration, not image count alone, determines reconstruction viability."})
    if capture_mode == "video" and duration < 20:
        findings.append({"severity": "warning", "code": "short_capture", "message": "Capture is shorter than 20 seconds and may not cover the environment."})
    if accepted_ratio < 0.5:
        findings.append({"severity": "warning", "code": "high_rejection_rate", "message": "More than half of sampled frames were rejected."})
    if match_ratios and median(match_ratios) < 0.04:
        findings.append({"severity": "error", "code": "weak_adjacent_overlap", "message": "Adjacent accepted frames have very few repeatable ORB features."})
    if match_ratios and median(match_ratios) > 0.82 and (not displacements or median(displacements) < 2):
        findings.append({"severity": "warning", "code": "low_camera_motion", "message": "Adjacent frames appear nearly identical; capture more translation and parallax."})
    if brightness and (median(brightness) < 35 or median(brightness) > 220):
        findings.append({"severity": "warning", "code": "exposure", "message": "Median brightness suggests under- or over-exposure."})

    blocking = any(item["severity"] == "error" for item in findings)
    return {
        "schema_version": "1.0.0",
        "scene_id": manifest.get("scene_id", scene.name),
        "status": "ready_for_reconstruction" if accepted and not blocking else "not_ready",
        "spatial_coverage_status": "unknown_until_camera_registration",
        "metrics": {
            "duration_seconds": duration,
            "capture_mode": capture_mode,
            "sampled_frames": sampled,
            "accepted_frames": accepted,
            "accepted_ratio": round(accepted_ratio, 4),
            "median_blur_score": round(median(sharpness), 3) if sharpness else None,
            "median_brightness": round(median(brightness), 3) if brightness else None,
            "adjacent_pairs_analyzed": len(overlaps),
            "median_orb_match_ratio": round(median(match_ratios), 4) if match_ratios else None,
            "median_feature_displacement_pixels": round(median(displacements), 3) if displacements else None,
            "mean_good_matches": round(mean(float(item["good_matches"]) for item in overlaps), 2) if overlaps else None,
        },
        "findings": findings,
        "limitations": [
            "Image overlap is a feature-match heuristic, not proof of successful camera registration.",
            "Room coverage and reconstruction completeness require an actual reconstruction run.",
        ],
    }


def write_capture_readiness_report(scene_dir: str | Path) -> Path:
    scene = Path(scene_dir).expanduser().resolve()
    report = analyze_capture_readiness(scene)
    output = scene / "metadata" / "capture_readiness.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output)
    return output
