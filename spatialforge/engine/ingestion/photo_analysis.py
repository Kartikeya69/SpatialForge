"""Feature-aware quality, metadata, overlap, and connectivity analysis for photo sets."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Callable, Sequence

import cv2
import numpy as np
from PIL import ExifTags, Image

from .images import decode_oriented_image
from spatialforge.engine.processing_profiles import ProcessingCancelled

_EXIF_NAMES = {key: value for key, value in ExifTags.TAGS.items()}


def _ratio(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def read_camera_metadata(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        with Image.open(source) as image:
            raw = image.getexif()
            values = {_EXIF_NAMES.get(key, str(key)): value for key, value in raw.items()}
    except (OSError, ValueError):
        return {"make": None, "model": None, "focal_length_mm": None, "focal_length_35mm": None}
    return {
        "make": str(values.get("Make")).strip() if values.get("Make") else None,
        "model": str(values.get("Model")).strip() if values.get("Model") else None,
        "focal_length_mm": _ratio(values.get("FocalLength")),
        "focal_length_35mm": _ratio(values.get("FocalLengthIn35mmFilm")),
    }


def focal_pixels_from_metadata(metadata: dict[str, Any], image_width: int) -> float | None:
    focal_35 = metadata.get("focal_length_35mm")
    if isinstance(focal_35, (int, float)) and focal_35 > 0:
        return float(image_width * focal_35 / 36.0)
    return None


def _standard_gray(image: np.ndarray, width: int = 1024) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if gray.shape[1] > width:
        height = max(1, round(gray.shape[0] * width / gray.shape[1]))
        gray = cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA)
    return gray


def _perceptual_hash(gray: np.ndarray) -> str:
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    coefficients = cv2.dct(small)[:8, :8]
    bits = coefficients > np.median(coefficients[1:])
    return f"{sum(int(bit) << index for index, bit in enumerate(bits.ravel())):016x}"


def _hash_distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def _entropy(gray: np.ndarray) -> float:
    histogram = cv2.calcHist([gray], [0], None, [256], [0, 256]).ravel()
    probabilities = histogram[histogram > 0] / gray.size
    return float(-(probabilities * np.log2(probabilities)).sum())


def _connected_components(count: int, edges: list[tuple[int, int]]) -> list[list[int]]:
    adjacency = [set() for _ in range(count)]
    for left, right in edges:
        adjacency[left].add(right)
        adjacency[right].add(left)
    unseen = set(range(count))
    components: list[list[int]] = []
    while unseen:
        start = unseen.pop()
        component = {start}
        frontier = [start]
        while frontier:
            current = frontier.pop()
            discovered = adjacency[current] & unseen
            unseen -= discovered
            component |= discovered
            frontier.extend(discovered)
        components.append(sorted(component))
    return sorted(components, key=lambda item: (-len(item), item))


def analyze_photo_set(
    paths: Sequence[str | Path],
    *,
    original_filenames: Sequence[str] | None = None,
    max_pairs: int = 5000,
    analysis_width: int = 1024,
    orb_features: int = 2000,
    max_source_megapixels: float | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> dict[str, Any]:
    if not paths:
        raise ValueError("At least one photo is required")
    if original_filenames is not None and len(original_filenames) != len(paths):
        raise ValueError("original_filenames must match paths")
    if max_pairs <= 0 or analysis_width < 128 or orb_features < 100:
        raise ValueError("Invalid photo analysis limits")
    detector = cv2.ORB_create(nfeatures=orb_features)
    records: list[dict[str, Any]] = []
    descriptors: list[np.ndarray | None] = []
    keypoints: list[list[cv2.KeyPoint]] = []
    for index, value in enumerate(paths):
        if is_cancelled and is_cancelled():
            raise ProcessingCancelled("Photo analysis was cancelled")
        path = Path(value).expanduser().resolve()
        image = decode_oriented_image(path)
        megapixels = image.shape[0] * image.shape[1] / 1_000_000
        if max_source_megapixels is not None and megapixels > max_source_megapixels:
            raise ValueError(
                f"{path.name} is {megapixels:.1f} MP, above the active profile limit of "
                f"{max_source_megapixels:.1f} MP"
            )
        gray = _standard_gray(image, analysis_width)
        points, description = detector.detectAndCompute(gray, None)
        camera = read_camera_metadata(path)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        saturated = float(np.mean((gray <= 4) | (gray >= 251)))
        records.append({
            "index": index,
            "filename": original_filenames[index] if original_filenames is not None else path.name,
            "width": int(image.shape[1]),
            "height": int(image.shape[0]),
            "megapixels": round(megapixels, 4),
            "aspect_ratio": round(image.shape[1] / image.shape[0], 5),
            "sharpness_standardized": round(sharpness, 3),
            "mean_brightness": round(float(gray.mean()), 3),
            "contrast_stddev": round(float(gray.std()), 3),
            "entropy_bits": round(_entropy(gray), 4),
            "saturated_pixel_ratio": round(saturated, 5),
            "feature_count": len(points),
            "feature_density_per_megapixel": round(len(points) / max(0.01, image.shape[0] * image.shape[1] / 1_000_000), 2),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "perceptual_hash": _perceptual_hash(gray),
            "camera": camera,
            "estimated_focal_pixels": focal_pixels_from_metadata(camera, image.shape[1]),
            "quality_flags": [],
        })
        descriptors.append(description)
        keypoints.append(points)
        if on_progress:
            on_progress("image_analysis", index + 1, len(paths))

    adaptive_blur_threshold = max(20.0, median(record["sharpness_standardized"] for record in records) * 0.28)
    for record in records:
        flags = record["quality_flags"]
        if record["sharpness_standardized"] < adaptive_blur_threshold:
            flags.append("adaptive_blur_outlier")
        if record["feature_count"] < 120 or record["entropy_bits"] < 4.2:
            flags.append("low_texture_or_feature_richness")
        if record["mean_brightness"] < 30 or record["mean_brightness"] > 225:
            flags.append("exposure_extreme")
        if record["contrast_stddev"] < 18:
            flags.append("low_contrast")
        if record["saturated_pixel_ratio"] > 0.35:
            flags.append("large_clipped_or_reflective_region")

    pair_count = len(paths) * (len(paths) - 1) // 2
    pair_limit_hit = pair_count > max_pairs
    if not pair_limit_hit:
        pair_candidates = list(itertools.combinations(range(len(paths)), 2))
    else:
        # Bound memory and CPU for large sets. Sorting by perceptual hash is a
        # cheap retrieval stage; ORB/RANSAC still makes the connectivity decision.
        ordered = sorted(range(len(records)), key=lambda index: int(records[index]["perceptual_hash"], 16))
        window = max(1, min(len(ordered) - 1, math.ceil(max_pairs / len(ordered))))
        candidate_set: set[tuple[int, int]] = set()
        for position, left in enumerate(ordered):
            for right in ordered[position + 1 : position + 1 + window]:
                candidate_set.add((min(left, right), max(left, right)))
                if len(candidate_set) >= max_pairs:
                    break
            if len(candidate_set) >= max_pairs:
                break
        pair_candidates = sorted(candidate_set)
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    pairs: list[dict[str, Any]] = []
    connected_edges: list[tuple[int, int]] = []
    near_duplicate_edges: list[tuple[int, int]] = []
    for left, right in pair_candidates:
        if is_cancelled and is_cancelled():
            raise ProcessingCancelled("Photo matching was cancelled")
        left_description, right_description = descriptors[left], descriptors[right]
        good = []
        inliers = 0
        median_displacement = None
        if left_description is not None and right_description is not None and len(left_description) >= 2 and len(right_description) >= 2:
            matches = matcher.knnMatch(left_description, right_description, k=2)
            good = [pair[0] for pair in matches if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance]
            if len(good) >= 8:
                source_points = np.float32([keypoints[left][match.queryIdx].pt for match in good])
                target_points = np.float32([keypoints[right][match.trainIdx].pt for match in good])
                try:
                    _, mask = cv2.findFundamentalMat(source_points, target_points, cv2.FM_RANSAC, 2.0, 0.995)
                    geometry_model = "fundamental"
                except cv2.error:
                    mask = None
                    geometry_model = None
                if mask is None:
                    try:
                        _, mask = cv2.findHomography(source_points, target_points, cv2.RANSAC, 4.0)
                        geometry_model = "homography_fallback"
                    except cv2.error:
                        mask = None
                        geometry_model = "degenerate_matches"
                inliers = int(mask.sum()) if mask is not None else 0
                median_displacement = float(np.median(np.linalg.norm(source_points - target_points, axis=1)))
            else:
                geometry_model = None
        else:
            geometry_model = None
        denominator = max(1, min(len(keypoints[left]), len(keypoints[right])))
        match_ratio = len(good) / denominator
        inlier_ratio = inliers / max(1, len(good))
        hash_distance = _hash_distance(records[left]["perceptual_hash"], records[right]["perceptual_hash"])
        connected = len(good) >= 20 and inliers >= 12 and inlier_ratio >= 0.25
        near_duplicate = hash_distance <= 4 and match_ratio >= 0.35 and (median_displacement is None or median_displacement < 8)
        if connected:
            connected_edges.append((left, right))
        if near_duplicate:
            near_duplicate_edges.append((left, right))
        pairs.append({
            "left_index": left, "right_index": right, "good_matches": len(good), "inliers": inliers,
            "match_ratio": round(match_ratio, 5), "inlier_ratio": round(inlier_ratio, 5),
            "median_displacement_pixels": round(median_displacement, 3) if median_displacement is not None else None,
            "perceptual_hash_distance": hash_distance, "connected": connected, "near_duplicate": near_duplicate,
            "geometry_model": geometry_model,
            "strong_perspective_change": bool(connected and inlier_ratio < 0.45 and (median_displacement or 0) > 40),
        })
        if on_progress:
            on_progress("pair_matching", len(pairs), len(pair_candidates))

    exact_groups: dict[str, list[int]] = {}
    for record in records:
        exact_groups.setdefault(record["sha256"], []).append(record["index"])
    exclusions: dict[int, str] = {}
    for group in exact_groups.values():
        for index in group[1:]:
            exclusions[index] = "exact_duplicate"
    for left, right in near_duplicate_edges:
        if left in exclusions or right in exclusions:
            continue
        loser = left if records[left]["sharpness_standardized"] < records[right]["sharpness_standardized"] else right
        exclusions[loser] = "near_duplicate_with_redundant_viewpoint"

    components = _connected_components(len(records), connected_edges)
    degrees = [0] * len(records)
    for left, right in connected_edges:
        degrees[left] += 1
        degrees[right] += 1
    weak_indices = [index for index, degree in enumerate(degrees) if degree <= 1]
    recommendations: list[str] = []
    if len(components) > 1:
        recommendations.append("Capture bridging photographs between disconnected image groups with 60–80% visual overlap.")
    if any("low_texture_or_feature_richness" in record["quality_flags"] for record in records):
        recommendations.append("Add angled views containing textured edges; avoid featureless walls filling the frame.")
    if any("adaptive_blur_outlier" in record["quality_flags"] for record in records):
        recommendations.append("Recapture blur outliers while moving more slowly and using steadier exposure.")
    if not connected_edges and len(records) > 1:
        recommendations.append("The uploaded photos have no verified feature-connected pairs; recapture with stronger overlap.")
    elif len(records) > 3 and len(weak_indices) / len(records) > 0.25:
        recommendations.append("More than a quarter of the photographs have one or fewer verified overlap links; add intermediate views.")
    return {
        "schema_version": "1.0.0",
        "input_count": len(records),
        "adaptive_blur_threshold": round(adaptive_blur_threshold, 3),
        "analysis_configuration": {
            "analysis_width": analysis_width,
            "orb_features": orb_features,
            "max_pairs": max_pairs,
            "max_source_megapixels": max_source_megapixels,
        },
        "images": records,
        "pair_analysis": pairs,
        "pair_analysis_truncated": pair_limit_hit,
        "pair_candidate_strategy": "all_pairs" if not pair_limit_hit else "perceptual_hash_retrieval_then_orb",
        "connectivity": {
            "connected_pair_count": len(connected_edges),
            "component_count": len(components),
            "components": components,
            "isolated_image_indices": [component[0] for component in components if len(component) == 1],
            "degree_by_image": degrees,
            "weakly_connected_image_indices": weak_indices,
        },
        "selection": {
            "recommended_exclusions": [
                {"index": index, "filename": records[index]["filename"], "reason": reason}
                for index, reason in sorted(exclusions.items())
            ],
            "retained_indices": [index for index in range(len(records)) if index not in exclusions],
        },
        "recommendations": recommendations,
        "limitations": [
            "Feature connectivity is a preflight heuristic; only camera registration proves SfM connectivity.",
            "Reflection and low-texture flags are image-statistic warnings, not semantic detections.",
        ],
    }


def write_photo_analysis(report: dict[str, Any], output_path: str | Path) -> Path:
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output)
    return output
