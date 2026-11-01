from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest


@pytest.fixture
def synthetic_video(tmp_path: Path) -> Path:
    path = tmp_path / "room.mp4"
    width, height, fps, frame_count = 320, 240, 10.0, 20
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        pytest.skip("OpenCV build cannot encode MP4 test fixtures")
    for index in range(frame_count):
        x = np.arange(width, dtype=np.uint16)[None, :]
        y = np.arange(height, dtype=np.uint16)[:, None]
        pattern = ((x // 12 + y // 12 + index) % 2 * 255).astype(np.uint8)
        frame = np.dstack((pattern, np.roll(pattern, index, axis=1), 255 - pattern))
        cv2.putText(
            frame,
            str(index),
            (20 + index * 2, 120),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            2,
        )
        writer.write(frame)
    writer.release()
    return path
