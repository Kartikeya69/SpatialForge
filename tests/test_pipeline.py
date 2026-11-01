from __future__ import annotations

import json
from pathlib import Path

import pytest

from spatialforge.engine.ingestion.pipeline import (
    CaptureConfig,
    CapturePipeline,
    create_scene_layout,
    load_capture_config,
)


def test_invalid_capture_configuration() -> None:
    with pytest.raises(ValueError, match="sample_fps"):
        CaptureConfig(sample_fps=0).validate()
    with pytest.raises(ValueError, match="jpeg_quality"):
        CaptureConfig(jpeg_quality=101).validate()


def test_unknown_yaml_configuration_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "capture.yaml"
    path.write_text("unknown_value: true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown"):
        load_capture_config(path)


def test_scene_layout_is_unique_and_complete(tmp_path: Path) -> None:
    first_id, first_dir = create_scene_layout(tmp_path)
    second_id, _ = create_scene_layout(tmp_path)
    assert first_id != second_id
    assert {path.name for path in first_dir.iterdir()} == {
        "input",
        "images",
        "metadata",
        "logs",
    }


def test_end_to_end_pipeline_generates_images_and_manifest(
    synthetic_video: Path, tmp_path: Path
) -> None:
    dataset_root = tmp_path / "datasets"
    config = CaptureConfig(
        sample_fps=2.0,
        min_width=100,
        min_height=100,
        max_width=200,
        enable_blur_filter=False,
        enable_duplicate_filter=False,
    )
    manifest = CapturePipeline(config).process(synthetic_video, dataset_root)

    scene_dir = dataset_root / manifest["scene_id"]
    manifest_path = scene_dir / "metadata" / "capture_manifest.json"
    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["processing_status"] == "completed"
    assert manifest["total_frames_sampled"] == 4
    assert manifest["accepted_frames"] == 4
    assert manifest["rejected_frames"] == 0
    assert persisted["processing_status"] == "completed"
    assert (scene_dir / "input" / synthetic_video.name).is_file()
    assert all((scene_dir / item["path"]).is_file() for item in manifest["images"])
    assert all("\\" not in item["path"] for item in manifest["images"])
    events = [
        json.loads(line)
        for line in (scene_dir / "logs" / "capture.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [event["event"] for event in events] == ["capture_started", "capture_completed"]


def test_failed_quality_run_persists_failed_manifest(
    synthetic_video: Path, tmp_path: Path
) -> None:
    config = CaptureConfig(
        sample_fps=1,
        min_width=10_000,
        min_height=10_000,
        enable_blur_filter=False,
        enable_duplicate_filter=False,
    )
    with pytest.raises(ValueError, match="No frames"):
        CapturePipeline(config).process(synthetic_video, tmp_path / "datasets")

    manifests = list((tmp_path / "datasets").glob("scene_*/metadata/capture_manifest.json"))
    assert len(manifests) == 1
    failed = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert failed["processing_status"] == "failed"
    assert failed["rejection_reasons"] == {"below_minimum_resolution": 2}


def test_pipeline_bounds_frame_extraction(synthetic_video: Path, tmp_path: Path) -> None:
    dataset_root = tmp_path / "datasets"
    config = CaptureConfig(
        sample_fps=2.0,
        min_width=100,
        min_height=100,
        max_width=200,
        enable_blur_filter=False,
        enable_duplicate_filter=False,
        max_extracted_frames=2,
    )
    manifest = CapturePipeline(config).process(synthetic_video, dataset_root)
    assert manifest["processing_status"] == "completed"
    assert manifest["accepted_frames"] == 2
    assert len(manifest["images"]) == 2
    assert any("Bounded capture frame selection" in w for w in manifest.get("warnings", []))
