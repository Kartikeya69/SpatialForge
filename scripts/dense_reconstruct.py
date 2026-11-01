"""Run COLMAP dense reconstruction after a successful sparse reconstruction."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spatialforge.engine.reconstruction.dense import DenseReconstructionConfig, run_dense_reconstruction  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run COLMAP dense stereo, fusion, and meshing")
    parser.add_argument("scene", type=Path)
    parser.add_argument("--colmap-path")
    parser.add_argument("--quality", choices=("low", "balanced", "high"), default="balanced")
    parser.add_argument("--mesher", choices=("poisson", "delaunay", "none"), default="poisson")
    parser.add_argument("--no-geom-consistency", action="store_true")
    parser.add_argument("--timeout", type=int, default=7200)
    arguments = parser.parse_args()
    config = DenseReconstructionConfig(
        colmap_path=arguments.colmap_path,
        quality=arguments.quality,
        mesher=arguments.mesher,
        geom_consistency=not arguments.no_geom_consistency,
        timeout_seconds=arguments.timeout,
    )
    result = run_dense_reconstruction(arguments.scene, config)
    print(result["artifacts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
