from pathlib import Path

import numpy as np
import pytest

from spatialforge.engine.reconstruction.exporter import camera_pose_document
from spatialforge.engine.reconstruction.metrics import compute_reconstruction_metrics
from spatialforge.engine.reconstruction.parser import image_pose, parse_text_model


@pytest.fixture
def text_model(tmp_path: Path) -> Path:
    (tmp_path / "cameras.txt").write_text(
        "# cameras\n1 PINHOLE 640 480 500 500 320 240\n", encoding="utf-8"
    )
    (tmp_path / "images.txt").write_text(
        "# images\n1 1 0 0 0 1 2 3 1 frame_1.jpg\n10 20 -1\n"
        "2 1 0 0 0 0 0 0 1 frame_2.jpg\n\n",
        encoding="utf-8",
    )
    (tmp_path / "points3D.txt").write_text(
        "# points\n1 0 1 2 255 128 0 0.25 1 0 2 0\n"
        "2 2 3 4 0 128 255 0.75 1 1 2 1\n",
        encoding="utf-8",
    )
    return tmp_path


def test_parse_valid_colmap_text_model(text_model: Path) -> None:
    model = parse_text_model(text_model)
    assert len(model.cameras) == 1
    assert [image.name for image in model.images] == ["frame_1.jpg", "frame_2.jpg"]
    assert len(model.points) == 2
    metrics = compute_reconstruction_metrics(model, total_input_images=4, submodel_count=1)
    assert metrics["registered_images"] == 2
    assert metrics["registration_percentage"] == 50
    assert metrics["mean_reprojection_error_pixels"] == 0.5


def test_world_to_camera_pose_is_inverted_correctly(text_model: Path) -> None:
    model = parse_text_model(text_model)
    pose = image_pose(model.images[0])
    assert pose["camera_center_world"] == pytest.approx([-1, -2, -3])
    world_to_camera = np.asarray(pose["world_to_camera_matrix"])
    camera_to_world = np.asarray(pose["camera_to_world_matrix"])
    assert world_to_camera @ camera_to_world == pytest.approx(np.eye(4))
    document = camera_pose_document(model)
    assert document["coordinate_convention"]["scale"] == "arbitrary_monocular_sfm_scale"
