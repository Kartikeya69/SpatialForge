from pathlib import Path

import cv2
import numpy as np
import pytest

from spatialforge.engine.reconstruction.single_image import (
    DepthAnythingV2Onnx,
    DepthModelUnavailable,
    SingleImagePipeline,
    depth_to_colored_points,
    validate_relative_depth,
)
from spatialforge.scenes.schema import SceneManifest


def _image(path: Path) -> Path:
    image = np.zeros((60, 80, 3), dtype=np.uint8)
    image[:, :, 1] = np.arange(80, dtype=np.uint8)
    assert cv2.imwrite(str(path), image)
    return path


def test_depth_geometry_is_colored_and_camera_space() -> None:
    image = np.full((10, 20, 3), (10, 20, 30), dtype=np.uint8)
    depth = np.tile(np.linspace(0, 1, 20, dtype=np.float32), (10, 1))
    points, colors = depth_to_colored_points(image, depth, max_dimension=20)
    assert points.shape == colors.shape == (200, 3)
    assert np.all(points[:, 2] < 0)
    assert colors[0].tolist() == [30, 20, 10]


def test_single_image_pipeline_packages_non_metric_preview(tmp_path: Path) -> None:
    source = _image(tmp_path / "room.jpg")
    scene = tmp_path / "scene_single"
    depth = np.tile(np.linspace(0, 1, 80, dtype=np.float32), (60, 1))
    result = SingleImagePipeline(estimator=lambda _: depth).process(source, scene, "room.jpg")
    assert result["processing_status"] == "completed"
    manifest = SceneManifest.model_validate_json((scene / "metadata" / "scene_manifest.json").read_text())
    assert manifest.units.metric_scale_status == "arbitrary"
    assert manifest.navigation.enabled is False
    assert "AI-estimated" in manifest.description
    assert (scene / "assets" / "single-photo-depth.ply").is_file()


def test_invalid_depth_is_rejected() -> None:
    with pytest.raises(Exception, match="no usable variation"):
        validate_relative_depth(np.ones((10, 10), dtype=np.float32))


def test_missing_depth_weights_report_setup(monkeypatch) -> None:
    monkeypatch.delenv("SPATIALFORGE_DEPTH_MODEL", raising=False)
    with pytest.raises(DepthModelUnavailable, match="SPATIALFORGE_DEPTH_MODEL"):
        DepthAnythingV2Onnx()
