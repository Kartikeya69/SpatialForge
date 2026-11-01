"""Command-line entry point for the SpatialForge capture pipeline."""

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

from spatialforge.engine.ingestion.pipeline import (  # noqa: E402
    CapturePipeline,
    load_capture_config,
)


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be zero or greater")
    return parsed


def unit_float(value: str) -> float:
    parsed = float(value)
    if not 0 <= parsed <= 1:
        raise argparse.ArgumentTypeError("value must be between 0 and 1")
    return parsed


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract validated, COLMAP-ready JPEG frames from a smartphone video."
    )
    parser.add_argument("--input", required=True, type=Path, help="MP4 or MOV capture video")
    parser.add_argument("--output", type=Path, help="Dataset root (defaults to configuration)")
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "configs" / "capture.yaml",
        help="Capture YAML configuration",
    )
    parser.add_argument("--sample-fps", type=positive_float)
    parser.add_argument("--blur-threshold", type=non_negative_float)
    parser.add_argument("--max-width", type=positive_int)
    parser.add_argument("--duplicate-threshold", type=unit_float)
    parser.add_argument("--disable-blur-filter", action="store_true")
    parser.add_argument("--disable-duplicate-filter", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    config = load_capture_config(args.config)
    overrides = {
        key: value
        for key, value in {
            "sample_fps": args.sample_fps,
            "blur_threshold": args.blur_threshold,
            "max_width": args.max_width,
        }.items()
        if value is not None
    }
    if args.duplicate_threshold is not None:
        overrides["duplicate_threshold"] = args.duplicate_threshold
    if args.disable_blur_filter:
        overrides["enable_blur_filter"] = False
    if args.disable_duplicate_filter:
        overrides["enable_duplicate_filter"] = False
    config = replace(config, **overrides)

    try:
        manifest = CapturePipeline(config).process(args.input, args.output)
    except Exception as exc:
        logging.getLogger(__name__).error("Capture processing failed: %s", exc)
        return 1

    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
