"""Generate a capture-readiness report without claiming reconstruction success."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spatialforge.engine.ingestion.readiness import (  # noqa: E402
    CaptureReadinessError,
    analyze_capture_readiness,
    write_capture_readiness_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze a SpatialForge capture dataset before reconstruction")
    parser.add_argument("scene", type=Path)
    parser.add_argument("--write", action="store_true", help="Persist metadata/capture_readiness.json")
    arguments = parser.parse_args()
    try:
        if arguments.write:
            path = write_capture_readiness_report(arguments.scene)
            print(path)
        else:
            print(json.dumps(analyze_capture_readiness(arguments.scene), indent=2))
    except CaptureReadinessError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
