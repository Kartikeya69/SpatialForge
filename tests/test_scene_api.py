from pathlib import Path

from fastapi.testclient import TestClient

import spatialforge.api.main as api
from spatialforge.scenes.demo import create_demo_scene
from spatialforge.scenes.package import export_scene_package


def test_scene_api_enumerates_manifest_and_serves_asset(tmp_path: Path, monkeypatch) -> None:
    create_demo_scene(tmp_path)
    monkeypatch.setattr(api, "DATASET_ROOT", tmp_path)
    client = TestClient(api.app)

    listing = client.get("/api/v1/scenes")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert listing.json()["scenes"][0]["scene_id"] == "scene_synthetic_loft"

    detail = client.get("/api/v1/scenes/scene_synthetic_loft")
    assert detail.status_code == 200
    assert detail.json()["synthetic_demo"] is True

    manifest = client.get("/api/v1/scenes/scene_synthetic_loft/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["coordinate_system"]["up_axis"] == "Y"

    asset = client.get("/api/v1/scenes/scene_synthetic_loft/assets/assets/demo-room.gltf")
    assert asset.status_code == 200
    assert asset.headers["content-type"].startswith("model/gltf+json")


def test_scene_api_blocks_unsafe_or_undeclared_assets(tmp_path: Path, monkeypatch) -> None:
    create_demo_scene(tmp_path)
    monkeypatch.setattr(api, "DATASET_ROOT", tmp_path)
    client = TestClient(api.app)
    response = client.get("/api/v1/scenes/scene_synthetic_loft/assets/assets/not-declared.glb")
    assert response.status_code == 400
    assert "not declared" in response.json()["detail"]


def test_scene_api_reports_missing_declared_asset(tmp_path: Path, monkeypatch) -> None:
    scene = create_demo_scene(tmp_path)
    (scene / "assets" / "demo-room.gltf").unlink()
    monkeypatch.setattr(api, "DATASET_ROOT", tmp_path)
    response = TestClient(api.app).get(
        "/api/v1/scenes/scene_synthetic_loft/assets/assets/demo-room.gltf"
    )
    assert response.status_code == 404


def test_scene_api_rejects_invalid_scene_identifier(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(api, "DATASET_ROOT", tmp_path)
    response = TestClient(api.app).get("/api/v1/scenes/not-a-scene/manifest")
    assert response.status_code == 400


def test_scene_api_imports_valid_user_package(tmp_path: Path, monkeypatch) -> None:
    source_scene = create_demo_scene(tmp_path / "source")
    archive = export_scene_package(source_scene, tmp_path / "scene.sfscene")
    destination = tmp_path / "datasets"
    monkeypatch.setattr(api, "DATASET_ROOT", destination)

    with archive.open("rb") as package:
        response = TestClient(api.app).post(
            "/api/v1/scenes/import",
            files={"scene_package": ("scene.sfscene", package, "application/zip")},
        )

    assert response.status_code == 201
    assert response.json()["scene_id"] == "scene_synthetic_loft"
    assert (destination / "scene_synthetic_loft" / "metadata" / "scene_manifest.json").is_file()


def test_scene_api_rejects_non_package_upload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(api, "DATASET_ROOT", tmp_path)
    response = TestClient(api.app).post(
        "/api/v1/scenes/import",
        files={"scene_package": ("scene.zip", b"not a package", "application/zip")},
    )
    assert response.status_code == 415
