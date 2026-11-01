from pathlib import Path

import cv2
import numpy as np
import pytest

from spatialforge.engine.ingestion.photo_analysis import analyze_photo_set
from spatialforge.engine.processing_profiles import ProcessingCancelled


def _write(path: Path, offset: int = 0) -> Path:
    image = np.zeros((180, 240, 3), np.uint8)
    for x in range(20, 220, 30):
        cv2.circle(image, (x + offset, 90), 8, (255, 255, 255), -1)
    assert cv2.imwrite(str(path), image)
    return path


def test_photo_analysis_records_exact_duplicate_and_connectivity(tmp_path: Path) -> None:
    first = _write(tmp_path / "first.jpg")
    duplicate = tmp_path / "duplicate.jpg"
    duplicate.write_bytes(first.read_bytes())
    report = analyze_photo_set([first, duplicate], original_filenames=["a.jpg", "b.jpg"])
    assert report["input_count"] == 2
    assert report["images"][0]["filename"] == "a.jpg"
    assert report["selection"]["recommended_exclusions"] == [
        {"index": 1, "filename": "b.jpg", "reason": "exact_duplicate"}
    ]


def test_photo_analysis_honors_cancellation(tmp_path: Path) -> None:
    source = _write(tmp_path / "first.jpg")
    with pytest.raises(ProcessingCancelled):
        analyze_photo_set([source], is_cancelled=lambda: True)
