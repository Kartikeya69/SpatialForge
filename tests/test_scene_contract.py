from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from spatialforge.scenes.coordinates import transform_camera_to_world, transform_point
from spatialforge.scenes.demo import IDENTITY_MATRIX, create_demo_scene
from spatialforge.scenes.schema import SceneManifest
from spatialforge.scenes.store import SceneAssetError, SceneStore


def test_generated_demo_scene_satisfies_manifest_contract(tmp_path: Path) -> None:
    scene = create_demo_scene(tmp_path)
    manifest = SceneStore(tmp_path).load_manifest(scene.name)
    assert manifest.schema_version == "1.0.0"
    assert manifest.synthetic_demo is True
    assert manifest.units.metric_scale_status == "known"
    assert {asset.type for asset in manifest.assets} >= {"gltf", "ply", "collider_geometry"}
    assert all((scene / asset.path).is_file() for asset in manifest.assets)


@pytest.mark.parametrize(
    "path",
    ["../secret.txt", "/absolute/model.glb", "assets\\model.glb", "C:/model.glb", "assets//model.glb"],
)
def test_manifest_rejects_unsafe_asset_paths(tmp_path: Path, path: str) -> None:
    scene = create_demo_scene(tmp_path)
    document = json.loads((scene / "metadata" / "scene_manifest.json").read_text(encoding="utf-8"))
    document["assets"][0]["path"] = path
    with pytest.raises(ValidationError):
        SceneManifest.model_validate(document)


def test_store_rejects_undeclared_and_traversal_assets(tmp_path: Path) -> None:
    create_demo_scene(tmp_path)
    store = SceneStore(tmp_path)
    with pytest.raises(SceneAssetError, match="traversal"):
        store.resolve_asset("scene_synthetic_loft", "../outside.txt")
    with pytest.raises(SceneAssetError, match="not declared"):
        store.resolve_asset("scene_synthetic_loft", "assets/unknown.glb")


def test_scene_enumeration_ignores_invalid_packages(tmp_path: Path) -> None:
    create_demo_scene(tmp_path)
    invalid = tmp_path / "scene_invalid"
    (invalid / "metadata").mkdir(parents=True)
    (invalid / "metadata" / "scene_manifest.json").write_text("{}", encoding="utf-8")
    manifests = SceneStore(tmp_path).list_manifests()
    assert [manifest.scene_id for manifest in manifests] == ["scene_synthetic_loft"]


def test_coordinate_conversion_policy() -> None:
    transform = (
        2.0, 0.0, 0.0, 10.0,
        0.0, 2.0, 0.0, 20.0,
        0.0, 0.0, 2.0, 30.0,
        0.0, 0.0, 0.0, 1.0,
    )
    assert transform_point((1, 2, 3), transform) == pytest.approx((12, 24, 36))
    camera = transform_camera_to_world(tuple(float(value) for value in IDENTITY_MATRIX), transform)
    assert camera[3] == 10
    assert camera[7] == 20
    assert camera[11] == 30
