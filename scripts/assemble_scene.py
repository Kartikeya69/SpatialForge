"""Create a browser scene manifest from completed, calibrated reconstruction outputs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spatialforge.scenes.assemble import SceneAssemblyError, assemble_reconstructed_scene  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble calibrated reconstruction outputs for the browser viewer")
    parser.add_argument("scene", type=Path)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--name")
    parser.add_argument("--visual-asset", help="Scene-relative GLB/glTF/PLY path; defaults to sparse PLY")
    arguments = parser.parse_args()
    try:
        print(assemble_reconstructed_scene(arguments.scene, arguments.calibration, scene_name=arguments.name, visual_asset=arguments.visual_asset))
    except SceneAssemblyError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
