import cv2
import numpy as np
import pytest

from spatialforge.engine.ingestion.quality import (
    QualityConfig,
    calculate_blur_score,
    evaluate_frame,
)


def test_blur_detection_distinguishes_flat_and_sharp_images() -> None:
    flat = np.full((200, 200, 3), 127, dtype=np.uint8)
    checker = np.indices((200, 200)).sum(axis=0) % 2 * 255
    sharp = np.dstack([checker, checker, checker]).astype(np.uint8)

    assert calculate_blur_score(flat) == 0
    assert calculate_blur_score(sharp) > 100
    result = evaluate_frame(
        flat,
        QualityConfig(min_width=100, min_height=100, blur_threshold=1),
    )
    assert not result.accepted
    assert "blurry" in result.rejection_reasons


def test_duplicate_filtering_is_conservative_and_optional() -> None:
    image = np.random.default_rng(7).integers(0, 256, (120, 160, 3), dtype=np.uint8)
    config = QualityConfig(
        min_width=100,
        min_height=100,
        enable_blur_filter=False,
        duplicate_threshold=0.995,
    )
    first = evaluate_frame(image, config)
    duplicate = evaluate_frame(image.copy(), config, first.fingerprint)
    assert not duplicate.accepted
    assert duplicate.duplicate_similarity == pytest.approx(1.0)
    assert duplicate.rejection_reasons == ("near_duplicate",)

    disabled = evaluate_frame(
        image,
        QualityConfig(
            min_width=100,
            min_height=100,
            enable_blur_filter=False,
            enable_duplicate_filter=False,
        ),
        first.fingerprint,
    )
    assert disabled.accepted


def test_downscaling_preserves_aspect_ratio() -> None:
    image = np.zeros((300, 600, 3), dtype=np.uint8)
    result = evaluate_frame(
        image,
        QualityConfig(
            min_width=1,
            min_height=1,
            max_width=200,
            enable_blur_filter=False,
            enable_duplicate_filter=False,
        ),
    )
    assert result.image.shape[:2] == (100, 200)


@pytest.mark.parametrize(
    "config",
    [
        QualityConfig(blur_threshold=-1),
        QualityConfig(min_width=0),
        QualityConfig(max_width=0),
        QualityConfig(duplicate_threshold=1.1),
    ],
)
def test_invalid_quality_configuration(config: QualityConfig) -> None:
    with pytest.raises(ValueError):
        config.validate()
