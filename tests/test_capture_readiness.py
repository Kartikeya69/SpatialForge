from pathlib import Path

import pytest

from spatialforge.engine.ingestion.readiness import CaptureReadinessError, analyze_capture_readiness


def test_capture_readiness_reports_small_fixture_without_treating_count_as_proof() -> None:
    scene = Path(__file__).resolve().parents[1] / "test_fixtures" / "legacy_datasets" / "scene_20261021T112616Z_f814edaf69"
    report = analyze_capture_readiness(scene)
    assert report["status"] == "ready_for_reconstruction"
    assert report["spatial_coverage_status"] == "unknown_until_camera_registration"
    assert any(item["code"] == "small_image_set" for item in report["findings"])
    assert report["metrics"]["adjacent_pairs_analyzed"] == 3


def test_capture_readiness_requires_manifest(tmp_path: Path) -> None:
    with pytest.raises(CaptureReadinessError, match="manifest is missing"):
        analyze_capture_readiness(tmp_path)
