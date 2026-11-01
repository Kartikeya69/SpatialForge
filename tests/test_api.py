from dataclasses import replace
import json
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

import spatialforge.api.main as api


def test_health_endpoint() -> None:
    response = TestClient(api.app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_capture_upload_and_status(
    synthetic_video: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(api, "DATASET_ROOT", tmp_path / "datasets")
    monkeypatch.setattr(
        api,
        "CONFIG",
        replace(
            api.CONFIG,
            sample_fps=2,
            min_width=100,
            min_height=100,
            enable_blur_filter=False,
            enable_duplicate_filter=False,
        ),
    )
    client = TestClient(api.app)
    with synthetic_video.open("rb") as source:
        response = client.post(
            "/api/v1/captures",
            files={"video": ("phone-room.mp4", source, "video/mp4")},
        )
    assert response.status_code == 202
    body = response.json()
    assert body["scene_id"].startswith("scene_")

    import time

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status_response = client.get(f"/api/v1/captures/{body['scene_id']}")
        assert status_response.status_code == 200
        status_body = status_response.json()
        if status_body["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)
    assert status_body["status"] == "completed"
    assert status_body["accepted_frames"] > 0


def test_capture_upload_rejects_unsupported_extension(tmp_path: Path) -> None:
    response = TestClient(api.app).post(
        "/api/v1/captures",
        files={"video": ("capture.avi", b"data", "video/x-msvideo")},
    )
    assert response.status_code == 415


def _jpeg_bytes(seed: int) -> bytes:
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    cv2.rectangle(image, (10 + seed, 10), (100 + seed, 90), (40, 170, 230), -1)
    success, encoded = cv2.imencode(".jpg", image)
    assert success
    return encoded.tobytes()


def test_multi_photo_upload_creates_real_image_dataset(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(api, "DATASET_ROOT", tmp_path / "datasets")
    monkeypatch.setattr(api, "_executor", ImmediateExecutor())
    monkeypatch.setattr(api, "CONFIG", replace(api.CONFIG, min_width=80, min_height=60, enable_blur_filter=False, enable_duplicate_filter=False))
    api._jobs.clear()
    response = TestClient(api.app).post(
        "/api/v1/captures/photos",
        files=[("photos", (f"room-{index}.jpg", _jpeg_bytes(index * 8), "image/jpeg")) for index in range(3)],
    )
    assert response.status_code == 202
    scene_id = response.json()["scene_id"]
    status_response = TestClient(api.app).get(f"/api/v1/captures/{scene_id}")
    assert status_response.json()["status"] == "ready_for_reconstruction"
    assert status_response.json()["accepted_frames"] == 3


def test_single_photo_reports_missing_depth_model(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(api, "DATASET_ROOT", tmp_path / "datasets")
    monkeypatch.setattr(api, "_executor", ImmediateExecutor())
    monkeypatch.delenv("SPATIALFORGE_DEPTH_MODEL", raising=False)
    api._jobs.clear()
    response = TestClient(api.app).post(
        "/api/v1/captures/single",
        files={"image": ("room.jpg", _jpeg_bytes(0), "image/jpeg")},
    )
    assert response.status_code == 202
    status_response = TestClient(api.app).get(f"/api/v1/captures/{response.json()['scene_id']}")
    assert status_response.json()["status"] == "failed"
    assert "SPATIALFORGE_DEPTH_MODEL" in status_response.json()["error"]


def test_photo_upload_rejects_unknown_processing_profile() -> None:
    response = TestClient(api.app).post(
        "/api/v1/captures/photos",
        data={"profile": "unlimited"},
        files={"photos": ("room.jpg", _jpeg_bytes(0), "image/jpeg")},
    )
    assert response.status_code == 422


def test_capture_cancellation_sets_cooperative_event() -> None:
    scene_id = "scene_cancel_test"
    event = api.threading.Event()
    api._job_cancel_events[scene_id] = event
    api._jobs[scene_id] = {"scene_id": scene_id, "status": "processing"}
    response = TestClient(api.app).post(f"/api/v1/captures/{scene_id}/cancel")
    assert response.status_code == 202
    assert event.is_set()
    assert api._jobs[scene_id]["status"] == "cancelling"
    api._job_cancel_events.pop(scene_id, None)
    api._jobs.pop(scene_id, None)


def _make_reconstruction_scene(root: Path, scene_id: str) -> Path:
    scene = root / scene_id
    (scene / "images").mkdir(parents=True)
    (scene / "metadata").mkdir()
    images = []
    for index in range(3):
        image = scene / "images" / f"frame_{index:06d}.jpg"
        image.write_bytes(b"jpeg")
        images.append({"path": f"images/{image.name}"})
    (scene / "metadata" / "capture_manifest.json").write_text(
        json.dumps({"processing_status": "completed", "images": images}), encoding="utf-8"
    )
    return scene


class ImmediateExecutor:
    def submit(self, function, *arguments):
        function(*arguments)


class DeferredExecutor:
    def __init__(self) -> None:
        self.submissions = []

    def submit(self, function, *arguments):
        self.submissions.append((function, arguments))


class SuccessfulBackend:
    def __init__(self, config) -> None:
        pass

    def reconstruct(self, scene_dir: Path):
        return {
            "processing_status": "completed",
            "metrics": {"registered_images": 3},
        }


def test_reconstruction_api_job_lifecycle(tmp_path: Path, monkeypatch) -> None:
    dataset_root = tmp_path / "datasets"
    scene = _make_reconstruction_scene(dataset_root, "scene_api_lifecycle")
    monkeypatch.setattr(api, "DATASET_ROOT", dataset_root)
    monkeypatch.setattr(api, "ColmapBackend", SuccessfulBackend)
    monkeypatch.setattr(api, "_reconstruction_executor", ImmediateExecutor())
    api._reconstruction_jobs.clear()

    client = TestClient(api.app)
    response = client.post(f"/api/v1/scenes/{scene.name}/reconstruct")
    assert response.status_code == 202
    status_response = client.get(f"/api/v1/scenes/{scene.name}/reconstruction")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"
    assert status_response.json()["metrics"]["registered_images"] == 3


def test_reconstruction_api_prevents_duplicate_jobs(tmp_path: Path, monkeypatch) -> None:
    dataset_root = tmp_path / "datasets"
    scene = _make_reconstruction_scene(dataset_root, "scene_api_duplicate")
    executor = DeferredExecutor()
    monkeypatch.setattr(api, "DATASET_ROOT", dataset_root)
    monkeypatch.setattr(api, "_reconstruction_executor", executor)
    api._reconstruction_jobs.clear()

    client = TestClient(api.app)
    first = client.post(f"/api/v1/scenes/{scene.name}/reconstruct")
    second = client.post(f"/api/v1/scenes/{scene.name}/reconstruct")
    assert first.status_code == 202
    assert second.status_code == 409
    assert len(executor.submissions) == 1


def test_reconstruction_api_accepts_profile(tmp_path: Path, monkeypatch) -> None:
    dataset_root = tmp_path / "datasets"
    scene = _make_reconstruction_scene(dataset_root, "scene_api_profile")
    captured_config = []

    class ConfigRecordingBackend:
        def __init__(self, config):
            captured_config.append(config)

        def reconstruct(self, scene_dir: Path):
            return {
                "processing_status": "completed",
                "metrics": {"registered_images": 3},
            }

    monkeypatch.setattr(api, "DATASET_ROOT", dataset_root)
    monkeypatch.setattr(api, "ColmapBackend", ConfigRecordingBackend)
    monkeypatch.setattr(api, "_reconstruction_executor", ImmediateExecutor())
    api._reconstruction_jobs.clear()

    client = TestClient(api.app)
    response = client.post(f"/api/v1/scenes/{scene.name}/reconstruct", json={"profile": "fast"})
    assert response.status_code == 202
    assert response.json()["profile"] == "cpu_fast"
    assert len(captured_config) == 1
    assert captured_config[0].profile == "cpu_fast"
    assert captured_config[0].max_num_features == 4096
