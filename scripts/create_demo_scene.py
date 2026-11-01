"""Generate the deterministic SpatialForge browser demo scene."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spatialforge.scenes.demo import create_demo_scene  # noqa: E402
from spatialforge.scenes.store import SceneStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the deterministic SpatialForge demo scene")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "test_fixtures" / "demo_scenes")
    arguments = parser.parse_args()
    scene = create_demo_scene(arguments.output)
    manifest = SceneStore(arguments.output).load_manifest(scene.name)
    print(f"Generated {manifest.scene_name}: {scene}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
