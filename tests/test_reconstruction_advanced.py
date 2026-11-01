from pathlib import Path

import cv2
import numpy as np

from spatialforge.engine.reconstruction.base import ReconstructionConfig, SceneInput
from spatialforge.engine.reconstruction.colmap import choose_matching_strategy
from spatialforge.engine.reconstruction.single_image import depth_to_colored_mesh


def _scene_input(tmp_path: Path, mode: str, count: int) -> SceneInput:
    images = tuple(tmp_path / f"{index}.jpg" for index in range(count))
    return SceneInput("scene_x", tmp_path, tmp_path, images, {"capture_mode": mode})


def test_auto_matcher_respects_capture_order_and_bound(tmp_path: Path) -> None:
    config = ReconstructionConfig(max_exhaustive_images=5)
    assert choose_matching_strategy(config, _scene_input(tmp_path, "video", 100)) == "sequential"
    assert choose_matching_strategy(config, _scene_input(tmp_path, "photo_set", 5)) == "exhaustive"


def test_mesh_does_not_bridge_large_depth_discontinuity() -> None:
    image = np.full((4, 4, 3), 128, np.uint8)
    depth = np.zeros((4, 4), np.float32)
    depth[:, 2:] = 1
    points, _, faces, rejected = depth_to_colored_mesh(image, depth, max_dimension=4, discontinuity_threshold=0.05)
    assert rejected > 0
    assert len(faces) < 18
    assert faces.max() < len(points)
