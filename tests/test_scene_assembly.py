import json
from pathlib import Path

import pytest

from spatialforge.scenes.assemble import SceneAssemblyError, assemble_reconstructed_scene
from spatialforge.scenes.store import SceneStore


def _scene(root: Path) -> tuple[Path, Path]:
    scene = root / "scene_real_test"
    exports = scene / "reconstruction" / "colmap" / "exports"
    exports.mkdir(parents=True)
    (scene / "metadata").mkdir()
    points = [f"{index % 5} {(index // 5) % 2} {index // 10}" for index in range(20)]
    (exports / "sparse.ply").write_text(
        "\n".join(["ply", "format ascii 1.0", "element vertex 20", "property float x", "property float y", "property float z", "end_header", *points]) + "\n",
        encoding="ascii",
    )
    (exports / "camera_poses.json").write_text(json.dumps({"poses": [{"camera_center_world": [0, 1, 0]}]}), encoding="utf-8")
    (scene / "metadata" / "reconstruction_manifest.json").write_text(json.dumps({
        "processing_status": "completed", "backend": "colmap", "backend_version": "test",
        "artifacts": {"point_cloud_ply": "reconstruction/colmap/exports/sparse.ply", "camera_poses": "reconstruction/colmap/exports/camera_poses.json"},
    }), encoding="utf-8")
    calibration = root / "calibration.json"
    calibration.write_text(json.dumps({"matrix_row_major": [1, 0, 0, 2, 0, 1, 0, 0, 0, 0, 1, -1, 0, 0, 0, 1], "target_units": "scene_unit", "metric_scale_status": "arbitrary"}), encoding="utf-8")
    return scene, calibration


def test_assemble_reconstruction_creates_valid_browser_manifest(tmp_path: Path) -> None:
    scene, calibration = _scene(tmp_path)
    output = assemble_reconstructed_scene(scene, calibration, scene_name="Real Test")
    assert output.is_file()
    manifest = SceneStore(tmp_path).load_manifest(scene.name)
    assert manifest.reconstruction.source == "reconstruction"
    assert manifest.navigation.enabled is False
    assert manifest.coordinate_system.source_to_scene_matrix_row_major[3] == 2


def test_assembly_requires_completed_reconstruction(tmp_path: Path) -> None:
    scene, calibration = _scene(tmp_path)
    path = scene / "metadata" / "reconstruction_manifest.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["processing_status"] = "failed"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(SceneAssemblyError, match="completed real reconstruction"):
        assemble_reconstructed_scene(scene, calibration)
