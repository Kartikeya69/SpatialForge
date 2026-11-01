"""Machine-readable camera pose export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .parser import ParsedModel, image_pose


def camera_pose_document(model: ParsedModel) -> dict[str, Any]:
    cameras = {
        camera.camera_id: {
            "camera_id": camera.camera_id,
            "model": camera.model,
            "width": camera.width,
            "height": camera.height,
            "parameters": list(camera.parameters),
        }
        for camera in model.cameras
    }
    return {
        "coordinate_convention": {
            "source": "COLMAP",
            "world_to_camera": "x_camera = R * x_world + t",
            "camera_to_world": "R_c2w = transpose(R); center_world = -transpose(R) * t",
            "scale": "arbitrary_monocular_sfm_scale",
            "axis_note": "No renderer-axis conversion has been applied.",
        },
        "cameras": list(cameras.values()),
        "poses": [image_pose(image) for image in model.images],
    }


def write_camera_poses(model: ParsedModel, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(camera_pose_document(model), indent=2), encoding="utf-8")
    temporary.replace(path)
    return path
