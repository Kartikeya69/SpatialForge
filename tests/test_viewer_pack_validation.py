import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from spatialforge.api.main import app
from spatialforge.scenes.assemble import SceneAssemblyError, assemble_reconstructed_scene
from spatialforge.scenes.validate import validate_viewer_pack, ViewerPackValidationError


def _create_mock_scene(
    root: Path,
    scene_id: str,
    ply_content: str,
    poses: list[dict] | None = None,
    backend: str = "colmap",
) -> tuple[Path, Path]:
    scene = root / scene_id
    exports = scene / "reconstruction" / "colmap" / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    metadata = scene / "metadata"
    metadata.mkdir(parents=True, exist_ok=True)

    ply_path = exports / "sparse.ply"
    ply_path.write_text(ply_content, encoding="ascii")

    pose_data = {"poses": poses or [{"camera_center_world": [0.0, 0.0, 0.0]}]}
    (exports / "camera_poses.json").write_text(json.dumps(pose_data), encoding="utf-8")

    (metadata / "reconstruction_manifest.json").write_text(
        json.dumps({
            "processing_status": "completed",
            "backend": backend,
            "backend_version": "test",
            "artifacts": {
                "point_cloud_ply": "reconstruction/colmap/exports/sparse.ply",
                "camera_poses": "reconstruction/colmap/exports/camera_poses.json",
            },
        }),
        encoding="utf-8",
    )

    cal_path = root / "calibration.json"
    cal_path.write_text(
        json.dumps({
            "matrix_row_major": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
            "target_units": "scene_unit",
            "metric_scale_status": "arbitrary",
        }),
        encoding="utf-8",
    )
    return scene, cal_path


def test_validate_viewer_pack_rejects_empty_ply(tmp_path: Path) -> None:
    scene, _ = _create_mock_scene(
        tmp_path,
        "scene_empty_ply",
        "ply\nformat ascii 1.0\nelement vertex 0\nproperty float x\nproperty float y\nproperty float z\nend_header\n",
    )
    # Assemble should reject empty PLY
    with pytest.raises(SceneAssemblyError, match="contains zero vertices"):
        assemble_reconstructed_scene(scene, tmp_path / "calibration.json")


def test_validate_viewer_pack_rejects_non_finite_coordinates(tmp_path: Path) -> None:
    scene, _ = _create_mock_scene(
        tmp_path,
        "scene_nan_ply",
        "ply\nformat ascii 1.0\nelement vertex 2\nproperty float x\nproperty float y\nproperty float z\nend_header\n0.0 0.0 0.0\nNaN 1.0 Inf\n",
    )
    with pytest.raises(SceneAssemblyError, match="non-finite coordinates"):
        assemble_reconstructed_scene(scene, tmp_path / "calibration.json")


def test_assemble_reconstruction_calculates_adaptive_point_size_and_yaw(tmp_path: Path) -> None:
    # 5 points stretching along +Z (from Z=10 to Z=50, span=40)
    pts = [f"0.0 0.0 {10.0 * i}" for i in range(1, 6)]
    scene, cal_path = _create_mock_scene(
        tmp_path,
        "scene_adaptive_test",
        f"ply\nformat ascii 1.0\nelement vertex 5\nproperty float x\nproperty float y\nproperty float z\nend_header\n" + "\n".join(pts) + "\n",
        poses=[{"camera_center_world": [0.0, 0.0, 0.0]}],
    )
    manifest_path = assemble_reconstructed_scene(scene, cal_path)
    assert manifest_path.is_file()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Point size should be scaled adaptively
    assert manifest["viewer"]["point_size"] >= 0.15
    # Spawn yaw should face the points at positive Z (around 180 deg)
    assert abs(manifest["navigation"]["spawn_yaw_degrees"] - 180.0) < 5.0

    # Validation must succeed
    validation = validate_viewer_pack(scene)
    assert validation.is_valid is True
    assert validation.point_count == 5
    assert validation.camera_pose_count == 1


def test_validate_viewer_pack_rejects_missing_geometry(tmp_path: Path) -> None:
    scene, cal_path = _create_mock_scene(
        tmp_path,
        "scene_missing_geom",
        "ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nend_header\n1.0 1.0 1.0\n",
    )
    assemble_reconstructed_scene(scene, cal_path)

    # Remove the geometry file
    (scene / "reconstruction" / "colmap" / "exports" / "sparse.ply").unlink()

    validation = validate_viewer_pack(scene)
    assert validation.is_valid is False
    assert any("does not exist on disk" in err for err in validation.errors)


def test_backend_validate_viewer_pack_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/scenes/scene_20261031T132349Z_4bfe84b483/validate-viewer-pack")
    assert response.status_code == 200
    doc = response.json()
    assert doc["is_valid"] is True
    assert doc["scene_id"] == "scene_20261031T132349Z_4bfe84b483"
    assert doc["point_count"] == 987
    assert doc["geometry_format"] == "ply"
    assert doc["camera_pose_count"] == 19
    assert doc["errors"] == []


def test_backend_asset_delivery_endpoints() -> None:
    client = TestClient(app)
    # Manifest endpoint
    m_resp = client.get("/api/v1/scenes/scene_20261031T132349Z_4bfe84b483/manifest")
    assert m_resp.status_code == 200
    manifest = m_resp.json()
    assert manifest["scene_id"] == "scene_20261031T132349Z_4bfe84b483"
    assert manifest["reconstruction"]["backend"] == "colmap"
    assert manifest["viewer"]["point_size"] > 0.1

    # Geometry asset endpoint
    g_resp = client.get("/api/v1/scenes/scene_20261031T132349Z_4bfe84b483/assets/reconstruction/colmap/exports/sparse.ply")
    assert g_resp.status_code == 200
    assert len(g_resp.content) == 14992
    assert g_resp.content.startswith(b"ply")

    # Camera poses endpoint
    p_resp = client.get("/api/v1/scenes/scene_20261031T132349Z_4bfe84b483/assets/reconstruction/colmap/exports/camera_poses.json")
    assert p_resp.status_code == 200
    poses_doc = p_resp.json()
    assert len(poses_doc["poses"]) == 19


def test_unified_quality_report_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/scenes/scene_20261031T132349Z_4bfe84b483/quality-report")
    assert response.status_code == 200
    report = response.json()
    assert report["scene_id"] == "scene_20261031T132349Z_4bfe84b483"
    assert report["pipeline"] == "video"
    assert report["geometry_summary"]["point_count"] == 987
    assert report["geometry_summary"]["is_valid"] is True
    assert "limitations" in report
