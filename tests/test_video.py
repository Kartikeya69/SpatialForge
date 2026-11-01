from pathlib import Path

import pytest

from spatialforge.engine.ingestion.video import (
    VideoError,
    inspect_video,
    iter_sampled_frames,
)


def test_missing_video_path_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="does not exist"):
        inspect_video(tmp_path / "missing.mp4")


def test_unsupported_input_format_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "capture.avi"
    path.write_bytes(b"not a video")
    with pytest.raises(VideoError, match="Unsupported video format"):
        inspect_video(path)


def test_corrupt_video_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.mp4"
    path.write_bytes(b"not a real mp4")
    with pytest.raises(VideoError, match="could not open"):
        inspect_video(path)


def test_video_metadata_and_frame_sampling(synthetic_video: Path) -> None:
    metadata = inspect_video(synthetic_video)
    assert metadata.width == 320
    assert metadata.height == 240
    assert metadata.frame_count == 20
    assert metadata.fps == pytest.approx(10.0)

    frames = list(iter_sampled_frames(synthetic_video, 2.0, metadata))
    assert [frame.source_index for frame in frames] == [0, 5, 10, 15]
    assert [frame.timestamp_seconds for frame in frames] == pytest.approx([0.0, 0.5, 1.0, 1.5])
