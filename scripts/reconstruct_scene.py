"""Command-line entry point for sparse scene reconstruction."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spatialforge.engine.reconstruction import ColmapBackend  # noqa: E402
from spatialforge.engine.reconstruction.colmap import load_reconstruction_config  # noqa: E402


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Estimate camera poses and a sparse point cloud using COLMAP."
    )
    parser.add_argument("--scene", required=True, type=Path, help="Capture scene directory")
    parser.add_argument("--backend", choices=["colmap"], default="colmap")
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "configs" / "reconstruction.yaml",
    )
    parser.add_argument("--colmap-path", help="Path to colmap.exe or COLMAP.bat")
    parser.add_argument("--matcher", choices=["sequential", "exhaustive"])
    parser.add_argument("--timeout", type=positive_int, help="Per-stage timeout in seconds")
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_reconstruction_config(arguments.config)
    config = replace(
        config,
        backend=arguments.backend,
        **({"colmap_path": arguments.colmap_path} if arguments.colmap_path else {}),
        **({"matcher": arguments.matcher} if arguments.matcher else {}),
        **({"timeout_seconds": arguments.timeout} if arguments.timeout else {}),
    )
    print(f"Starting {config.backend} reconstruction for {arguments.scene}", flush=True)
    try:
        manifest = ColmapBackend(config).reconstruct(arguments.scene)
    except Exception as exc:
        logging.error("Reconstruction failed: %s", exc)
        return 1
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
