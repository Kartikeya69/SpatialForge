"""Streaming video validation, metadata inspection, and frame sampling."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np


SUPPORTED_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".m4v", ".mkv", ".webm"})


class VideoError(ValueError):
    """Raised when a capture video cannot be safely processed."""


@dataclass(frozen=True)
class VideoMetadata:
    fps: float
    width: int
    height: int
    frame_count: int
    duration_seconds: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass(frozen=True)
class SampledFrame:
    source_index: int
    timestamp_seconds: float
    image: np.ndarray


def validate_video_path(path: str | Path) -> Path:
    video_path = Path(path).expanduser().resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Video file does not exist: {video_path}")
    if not video_path.is_file():
        raise VideoError(f"Video path is not a file: {video_path}")
    if video_path.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_VIDEO_EXTENSIONS))
        raise VideoError(
            f"Unsupported video format '{video_path.suffix or '<none>'}'. "
            f"Supported formats: {supported}"
        )
    return video_path


def inspect_video(path: str | Path) -> VideoMetadata:
    video_path = validate_video_path(path)
    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            raise VideoError(f"OpenCV could not open video: {video_path}")

        fps = float(capture.get(cv2.CAP_PROP_FPS))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))

        if fps <= 0 or width <= 0 or height <= 0 or frame_count <= 0:
            raise VideoError(
                "Video metadata is invalid or incomplete: "
                f"fps={fps}, resolution={width}x{height}, frames={frame_count}"
            )

        return VideoMetadata(
            fps=fps,
            width=width,
            height=height,
            frame_count=frame_count,
            duration_seconds=frame_count / fps,
        )
    finally:
        capture.release()


def iter_sampled_frames(
    path: str | Path,
    sample_fps: float,
    metadata: VideoMetadata | None = None,
) -> Iterator[SampledFrame]:
    """Yield sampled frames sequentially without loading the video into memory."""
    if sample_fps <= 0:
        raise ValueError("sample_fps must be greater than zero")

    video_path = validate_video_path(path)
    video_metadata = metadata or inspect_video(video_path)
    effective_fps = min(sample_fps, video_metadata.fps)
    sample_period = 1.0 / effective_fps
    next_sample_time = 0.0
    frame_index = 0

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise VideoError(f"OpenCV could not reopen video: {video_path}")

    try:
        while True:
            readable, frame = capture.read()
            if not readable:
                break

            timestamp = frame_index / video_metadata.fps
            if timestamp + (0.5 / video_metadata.fps) >= next_sample_time:
                yield SampledFrame(frame_index, timestamp, frame)
                next_sample_time += sample_period
            frame_index += 1
    finally:
        capture.release()
