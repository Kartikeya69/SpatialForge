"""Summarize measured SpatialForge reconstruction artifacts; never synthesizes results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def collect_scene_evidence(scene: Path) -> dict[str, Any]:
    metadata = scene / "metadata"
    capture = _load(metadata / "capture_manifest.json")
    sparse = _load(metadata / "reconstruction_manifest.json")
    dense = _load(metadata / "dense_reconstruction_manifest.json")
    single = _load(metadata / "single_image_manifest.json")
    unavailable: list[str] = []
    if sparse is None:
        unavailable.append("sparse reconstruction metrics")
    if dense is None:
        unavailable.append("dense reconstruction metrics")
    if single is None:
        unavailable.append("single-image processing metrics")
    return {
        "scene_id": scene.name,
        "capture": {
            "mode": (capture or single or {}).get("capture_mode"),
            "accepted_images": (capture or {}).get("accepted_frames"),
            "duration_seconds": (capture or single or {}).get("processing_duration_seconds"),
        },
        "sparse": {
            "status": (sparse or {}).get("processing_status"),
            "duration_seconds": (sparse or {}).get("processing_duration_seconds"),
            "metrics": (sparse or {}).get("metrics"),
        },
        "dense": {
            "status": (dense or {}).get("processing_status"),
            "duration_seconds": (dense or {}).get("processing_duration_seconds"),
            "artifacts": (dense or {}).get("artifacts"),
        },
        "single_image": {
            "status": (single or {}).get("processing_status"),
            "duration_seconds": (single or {}).get("processing_duration_seconds"),
        },
        "unavailable": unavailable,
        "visual_quality_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report only measured SpatialForge reconstruction evidence")
    parser.add_argument("scene", type=Path, help="Path to one scene directory")
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    args = parser.parse_args()
    scene = args.scene.expanduser().resolve()
    if not scene.is_dir():
        parser.error(f"Scene directory does not exist: {scene}")
    report = collect_scene_evidence(scene)
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
