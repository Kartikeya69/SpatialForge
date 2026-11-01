"""Intelligent input media analysis for SpatialForge Reconstruction Engine 3.0.

Provides rigorous, resource-aware quality assessment for images, photo collections,
and video sequences prior to reconstruction.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import cv2
import numpy as np


@dataclass(frozen=True)
class FrameAnalysis:
    width: int
    height: int
    megapixels: float
    sharpness: float
    brightness_mean: float
    contrast_std: float
    underexposed_pct: float
    overexposed_pct: float
    feature_count: int
    feature_density_per_mp: float
    textureless_pct: float
    has_sufficient_texture: bool
    is_sharp: bool
    is_well_exposed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MultiViewAnalysis:
    total_inputs: int
    usable_inputs: int
    mean_sharpness: float
    sharpness_variance: float
    mean_feature_density: float
    estimated_overlap_pct: float
    viewpoint_diversity_score: float
    redundant_frames_count: int
    texture_warning_count: int
    exposure_warning_count: int
    continuity_status: str
    actionable_recommendations: list[str]
    actionable_warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analyze_single_frame(
    image: np.ndarray,
    *,
    blur_threshold: float = 80.0,
    min_feature_density: float = 200.0,
) -> FrameAnalysis:
    """Evaluate quality, exposure, sharpness, and feature richness of a single image."""
    height, width = image.shape[:2]
    mp = (width * height) / 1_000_000.0
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image

    # Sharpness via Laplacian variance
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    sharpness = float(laplacian.var())

    # Exposure & Contrast
    mean_brightness = float(np.mean(gray))
    contrast_std = float(np.std(gray))
    underexposed = float(np.mean(gray < 15) * 100.0)
    overexposed = float(np.mean(gray > 240) * 100.0)

    # Feature extraction (FAST detector for high speed on CPU)
    fast = cv2.FastFeatureDetector_create(threshold=20, nonmaxSuppression=True)
    keypoints = fast.detect(gray, None)
    feature_count = len(keypoints)
    feature_density = feature_count / max(mp, 0.01)

    # Textureless analysis (flat region percentage via Sobel magnitude)
    sobelx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    sobely = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(sobelx, sobely)
    textureless_pct = float(np.mean(magnitude < 12.0) * 100.0)

    is_sharp = sharpness >= blur_threshold
    is_well_exposed = underexposed < 25.0 and overexposed < 20.0
    has_sufficient_texture = feature_density >= min_feature_density and textureless_pct < 65.0

    return FrameAnalysis(
        width=width,
        height=height,
        megapixels=round(mp, 2),
        sharpness=round(sharpness, 2),
        brightness_mean=round(mean_brightness, 2),
        contrast_std=round(contrast_std, 2),
        underexposed_pct=round(underexposed, 2),
        overexposed_pct=round(overexposed, 2),
        feature_count=feature_count,
        feature_density_per_mp=round(feature_density, 1),
        textureless_pct=round(textureless_pct, 1),
        has_sufficient_texture=has_sufficient_texture,
        is_sharp=is_sharp,
        is_well_exposed=is_well_exposed,
    )


def estimate_pairwise_overlap(
    image_a: np.ndarray,
    image_b: np.ndarray,
    *,
    max_features: int = 500,
) -> tuple[float, float]:
    """Estimate visual overlap percentage and translation displacement between two consecutive views.

    Returns:
        (overlap_pct [0-100], translation_magnitude_ratio [0-1])
    """
    gray_a = cv2.cvtColor(image_a, cv2.COLOR_BGR2GRAY) if image_a.ndim == 3 else image_a
    gray_b = cv2.cvtColor(image_b, cv2.COLOR_BGR2GRAY) if image_b.ndim == 3 else image_b

    # Downsample for rapid matching
    h, w = gray_a.shape[:2]
    scale = min(1.0, 640.0 / max(h, w))
    if scale < 1.0:
        gray_a = cv2.resize(gray_a, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        gray_b = cv2.resize(gray_b, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    orb = cv2.ORB_create(nfeatures=max_features)
    kp_a, des_a = orb.detectAndCompute(gray_a, None)
    kp_b, des_b = orb.detectAndCompute(gray_b, None)

    if des_a is None or des_b is None or len(kp_a) < 10 or len(kp_b) < 10:
        return 0.0, 0.0

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    matches = matcher.knnMatch(des_a, des_b, k=2)

    # Lowe's ratio test
    good_matches = []
    for m, n in matches:
        if m.distance < 0.75 * n.distance:
            good_matches.append(m)

    if len(good_matches) < 8:
        return 0.0, 0.0

    pts_a = np.float32([kp_a[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    pts_b = np.float32([kp_b[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    # Find Homography with RANSAC
    _, mask = cv2.findHomography(pts_a, pts_b, cv2.RANSAC, 4.0)
    inliers = int(np.sum(mask)) if mask is not None else 0
    inlier_ratio = inliers / max(min(len(kp_a), len(kp_b)), 1)
    overlap_pct = min(100.0, inlier_ratio * 120.0)

    # Calculate average motion displacement of inliers
    if mask is not None and inliers > 0:
        valid_a = pts_a[mask.ravel() == 1]
        valid_b = pts_b[mask.ravel() == 1]
        disp = np.mean(np.linalg.norm(valid_b - valid_a, axis=1))
        diag = math.hypot(gray_a.shape[1], gray_a.shape[0])
        disp_ratio = min(1.0, float(disp / max(diag, 1.0)))
    else:
        disp_ratio = 0.0

    return round(float(overlap_pct), 1), round(disp_ratio, 3)


def analyze_sequence(
    images: Sequence[np.ndarray],
    *,
    blur_threshold: float = 80.0,
) -> MultiViewAnalysis:
    """Comprehensive multi-view dataset analysis for photo sets or video keyframes."""
    total = len(images)
    if total == 0:
        return MultiViewAnalysis(
            total_inputs=0,
            usable_inputs=0,
            mean_sharpness=0.0,
            sharpness_variance=0.0,
            mean_feature_density=0.0,
            estimated_overlap_pct=0.0,
            viewpoint_diversity_score=0.0,
            redundant_frames_count=0,
            texture_warning_count=0,
            exposure_warning_count=0,
            continuity_status="no_input",
            actionable_recommendations=["Provide input media (photos or video) to begin."],
            actionable_warnings=["No images supplied for analysis."],
        )

    frame_analyses = [analyze_single_frame(img, blur_threshold=blur_threshold) for img in images]
    sharpness_values = [fa.sharpness for fa in frame_analyses]
    mean_sharp = float(np.mean(sharpness_values))
    var_sharp = float(np.var(sharpness_values))
    mean_density = float(np.mean([fa.feature_density_per_mp for fa in frame_analyses]))

    texture_warnings = sum(1 for fa in frame_analyses if not fa.has_sufficient_texture)
    exposure_warnings = sum(1 for fa in frame_analyses if not fa.is_well_exposed)
    usable_count = sum(1 for fa in frame_analyses if fa.is_sharp)

    # Estimate sequential overlap and motion diversity
    overlaps: list[float] = []
    displacements: list[float] = []
    redundant_count = 0

    for i in range(total - 1):
        overlap, disp = estimate_pairwise_overlap(images[i], images[i + 1])
        overlaps.append(overlap)
        displacements.append(disp)
        if overlap > 88.0 and disp < 0.015:
            redundant_count += 1

    mean_overlap = float(np.mean(overlaps)) if overlaps else 0.0
    mean_displacement = float(np.mean(displacements)) if displacements else 0.0

    # Viewpoint diversity: combination of baseline displacement and lack of excessive redundancy
    diversity_score = min(1.0, max(0.0, mean_displacement * 4.5))

    # Determine continuity status
    if total < 3:
        continuity = "insufficient_inputs"
    elif mean_overlap >= 45.0 and diversity_score >= 0.15:
        continuity = "good_continuity"
    elif mean_overlap < 35.0:
        continuity = "poor_overlap"
    elif diversity_score < 0.10:
        continuity = "insufficient_viewpoint_variation"
    else:
        continuity = "acceptable_continuity"

    # Actionable guidance
    recs: list[str] = []
    warns: list[str] = []

    if total < 15:
        warns.append(f"Only {total} views provided. Indoor 3D reconstruction typically produces best results with 25+ overlapping views.")
        recs.append("Capture more overlapping angles around the space or object.")

    if usable_count < total * 0.7:
        warns.append(f"{total - usable_count} images have motion blur or low sharpness.")
        recs.append("Slow down camera motion or increase lighting to reduce motion blur.")

    if mean_overlap < 40.0:
        warns.append("Average visual overlap between adjacent frames is low (< 40%).")
        recs.append("Capture frames closer together to avoid feature matching dropouts.")

    if diversity_score < 0.12 and total > 5:
        warns.append("Camera appears to have rotated in place with minimal lateral translation.")
        recs.append("Move the camera along a physical arc or line to create stereoscopic parallax.")

    if texture_warnings > total * 0.35:
        warns.append(f"{texture_warnings} frames contain large textureless regions (e.g. plain walls).")
        recs.append("Include identifiable objects, posters, or architectural edges in the frame.")

    if exposure_warnings > total * 0.3:
        warns.append(f"{exposure_warnings} frames show underexposure or washed out highlights.")
        recs.append("Adjust room lighting or camera exposure for even illumination.")

    if not recs:
        recs.append("Dataset verified with healthy overlap and texture density; ready for reconstruction.")

    return MultiViewAnalysis(
        total_inputs=total,
        usable_inputs=usable_count,
        mean_sharpness=round(mean_sharp, 2),
        sharpness_variance=round(var_sharp, 2),
        mean_feature_density=round(mean_density, 1),
        estimated_overlap_pct=round(mean_overlap, 1),
        viewpoint_diversity_score=round(diversity_score, 3),
        redundant_frames_count=redundant_count,
        texture_warning_count=texture_warnings,
        exposure_warning_count=exposure_warnings,
        continuity_status=continuity,
        actionable_recommendations=recs,
        actionable_warnings=warns,
    )
