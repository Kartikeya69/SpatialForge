import json
import zipfile
from pathlib import Path

import pytest

from spatialforge.scenes.demo import create_demo_scene
from spatialforge.scenes.package import (
    ScenePackageError,
    export_scene_package,
    import_scene_package,
    validate_scene_package,
)


def test_scene_package_round_trip(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    scene = create_demo_scene(source_root)
    archive = export_scene_package(scene, tmp_path / "loft.sfscene")
    validation = validate_scene_package(archive)
    assert validation.scene_id == scene.name
    assert validation.file_count >= 7
    imported = import_scene_package(archive, tmp_path / "destination")
    assert (imported / "metadata" / "scene_manifest.json").read_bytes() == (
        scene / "metadata" / "scene_manifest.json"
    ).read_bytes()


def test_package_refuses_overwrite(tmp_path: Path) -> None:
    source = create_demo_scene(tmp_path / "source")
    archive = export_scene_package(source, tmp_path / "scene.sfscene")
    destination = tmp_path / "destination"
    import_scene_package(archive, destination)
    with pytest.raises(ScenePackageError, match="will not be overwritten"):
        import_scene_package(archive, destination)


def test_package_detects_tampered_file(tmp_path: Path) -> None:
    source = create_demo_scene(tmp_path / "source")
    archive = export_scene_package(source, tmp_path / "scene.sfscene")
    broken = tmp_path / "broken.sfscene"
    with zipfile.ZipFile(archive) as original, zipfile.ZipFile(broken, "w") as output:
        for info in original.infolist():
            data = original.read(info.filename)
            output.writestr(info.filename, b"changed" if info.filename.endswith("pois.json") else data)
    with pytest.raises(ScenePackageError, match="mismatch"):
        validate_scene_package(broken)


def test_package_blocks_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.sfscene"
    manifest = {"package_schema_version": "1.0.0", "scene_id": "scene_unsafe", "files": [], "total_bytes": 0}
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("package_manifest.json", json.dumps(manifest))
        package.writestr("../outside.txt", "unsafe")
    with pytest.raises(ScenePackageError, match="Unsafe"):
        validate_scene_package(archive)


def test_package_rejects_missing_manifest_asset(tmp_path: Path) -> None:
    source = create_demo_scene(tmp_path / "source")
    (source / "assets" / "demo-room.gltf").unlink()
    archive = export_scene_package(source, tmp_path / "missing-asset.sfscene")
    with pytest.raises(ScenePackageError, match="missing declared asset"):
        import_scene_package(archive, tmp_path / "destination")
