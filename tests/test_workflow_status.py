import json
from pathlib import Path

from fastapi.testclient import TestClient

import spatialforge.api.main as api
from spatialforge.scenes.demo import create_demo_scene
from spatialforge.workflows import inspect_scene_job, list_scene_jobs


def test_workflow_status_uses_durable_manifests(tmp_path: Path) -> None:
    scene = tmp_path / "scene_capture"
    (scene / "metadata").mkdir(parents=True)
    (scene / "input").mkdir()
    (scene / "input" / "room.mp4").write_bytes(b"video")
    (scene / "metadata" / "capture_manifest.json").write_text(json.dumps({"processing_status": "completed", "accepted_frames": 40, "rejected_frames": 2}), encoding="utf-8")
    job = inspect_scene_job(scene)
    assert job["status"] == "awaiting_reconstruction"
    assert job["has_original_input"] is True


def test_workflow_lists_synthetic_ready_scene(tmp_path: Path) -> None:
    create_demo_scene(tmp_path)
    jobs = list_scene_jobs(tmp_path)
    assert jobs[0]["status"] == "ready"
    assert jobs[0]["current_stage"] == "viewer_package"


def test_workflow_api_lists_all_scene_directories(tmp_path: Path, monkeypatch) -> None:
    create_demo_scene(tmp_path)
    monkeypatch.setattr(api, "DATASET_ROOT", tmp_path)
    response = TestClient(api.app).get("/api/v1/pipeline/jobs")
    assert response.status_code == 200
    assert response.json()["count"] == 1
