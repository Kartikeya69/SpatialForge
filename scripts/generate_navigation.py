"""Generate reviewable navigation drafts from aligned PLY geometry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spatialforge.navigation.geometry import (  # noqa: E402
    GeometryNavigationError,
    generate_navigation_from_ply,
    write_navigation_draft,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a manual-review navigation draft from aligned PLY geometry")
    parser.add_argument("geometry", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resolution", type=float, default=0.25)
    parser.add_argument("--clearance", type=float, default=0.25)
    parser.add_argument("--unit", choices=("meter", "scene_unit"), default="scene_unit")
    parser.add_argument("--metric-scale-status", choices=("known", "estimated", "arbitrary"), default="arbitrary")
    parser.add_argument("--confirm-y-up", action="store_true", help="Confirm input has already been transformed to SpatialForge Y-up world coordinates")
    arguments = parser.parse_args()
    if not arguments.confirm_y_up:
        parser.error("Refusing silent axis assumptions. Calibrate the geometry and pass --confirm-y-up.")
    try:
        result = generate_navigation_from_ply(
            arguments.geometry,
            resolution=arguments.resolution,
            obstacle_clearance=arguments.clearance,
            unit=arguments.unit,
            metric_scale_status=arguments.metric_scale_status,
        )
        print(write_navigation_draft(result, arguments.output))
    except GeometryNavigationError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
