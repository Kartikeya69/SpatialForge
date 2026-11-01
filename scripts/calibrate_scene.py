"""Estimate an explicit reconstruction-to-viewer similarity transform."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spatialforge.scenes.calibration import CalibrationError, estimate_similarity_transform  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate COLMAP coordinates against known viewer-world points")
    parser.add_argument("correspondences", type=Path, help="JSON with source_points and target_points arrays")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-scale", action="store_true", help="Solve only rotation and translation")
    arguments = parser.parse_args()
    try:
        document = json.loads(arguments.correspondences.read_text(encoding="utf-8"))
        result = estimate_similarity_transform(
            document["source_points"], document["target_points"], estimate_scale=not arguments.no_scale
        )
    except (OSError, KeyError, ValueError, json.JSONDecodeError, CalibrationError) as exc:
        parser.error(str(exc))
    output = {
        "schema_version": "1.0.0",
        "coordinate_convention": "SpatialForge right-handed Y-up",
        "target_units": document.get("target_units", "scene_unit"),
        "metric_scale_status": "known" if document.get("target_units") == "meter" else "arbitrary",
        **result.__dict__,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_suffix(arguments.output.suffix + ".tmp")
    temporary.write_text(json.dumps(output, indent=2), encoding="utf-8")
    temporary.replace(arguments.output)
    print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
