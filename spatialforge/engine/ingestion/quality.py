"""Configurable frame quality checks for reconstruction datasets."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class QualityConfig:
    blur_threshold: float = 80.0
    min_width: int = 640
    min_height: int = 480
    max_width: int | None = 1920
    duplicate_threshold: float = 0.995
    enable_blur_filter: bool = True
    enable_duplicate_filter: bool = True

    def validate(self) -> None:
        if self.blur_threshold < 0:
            raise ValueError("blur_threshold must be zero or greater")
        if self.min_width <= 0 or self.min_height <= 0:
            raise ValueError("minimum resolution dimensions must be positive")
        if self.max_width is not None and self.max_width <= 0:
            raise ValueError("max_width must be positive or null")
        if not 0.0 <= self.duplicate_threshold <= 1.0:
            raise ValueError("duplicate_threshold must be between 0 and 1")


@dataclass(frozen=True)
class QualityResult:
    accepted: bool
    image: np.ndarray
    blur_score: float
    duplicate_similarity: float | None
    fingerprint: np.ndarray
    rejection_reasons: tuple[str, ...]


def calculate_blur_score(image: np.ndarray) -> float:
    if image.size == 0:
        raise ValueError("image must not be empty")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def downscale_image(image: np.ndarray, max_width: int | None) -> np.ndarray:
    if max_width is None or image.shape[1] <= max_width:
        return image
    scale = max_width / image.shape[1]
    target_height = max(1, round(image.shape[0] * scale))
    return cv2.resize(image, (max_width, target_height), interpolation=cv2.INTER_AREA)


def frame_fingerprint(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)


def fingerprint_similarity(left: np.ndarray, right: np.ndarray) -> float:
    difference = np.abs(left.astype(np.float32) - right.astype(np.float32))
    return float(1.0 - difference.mean() / 255.0)


def evaluate_frame(
    image: np.ndarray,
    config: QualityConfig,
    previous_accepted_fingerprint: np.ndarray | None = None,
) -> QualityResult:
    config.validate()
    if image.size == 0 or image.ndim != 3:
        raise ValueError("frame must be a non-empty color image")

    height, width = image.shape[:2]
    reasons: list[str] = []
    if width < config.min_width or height < config.min_height:
        reasons.append("below_minimum_resolution")

    blur_score = calculate_blur_score(image)
    if config.enable_blur_filter and blur_score < config.blur_threshold:
        reasons.append("blurry")

    processed = downscale_image(image, config.max_width)
    fingerprint = frame_fingerprint(processed)
    similarity: float | None = None
    if previous_accepted_fingerprint is not None:
        similarity = fingerprint_similarity(fingerprint, previous_accepted_fingerprint)
        if config.enable_duplicate_filter and similarity >= config.duplicate_threshold:
            reasons.append("near_duplicate")

    return QualityResult(
        accepted=not reasons,
        image=processed,
        blur_score=blur_score,
        duplicate_similarity=similarity,
        fingerprint=fingerprint,
        rejection_reasons=tuple(reasons),
    )
