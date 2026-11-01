"""Export, validate, and safely import portable .sfscene archives."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spatialforge.scenes.package import (  # noqa: E402
    ScenePackageError,
    export_scene_package,
    import_scene_package,
    validate_scene_package,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage portable SpatialForge scene packages")
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="Create an integrity-checked package")
    export.add_argument("scene", type=Path)
    export.add_argument("archive", type=Path)
    validate = commands.add_parser("validate", help="Validate an existing package")
    validate.add_argument("archive", type=Path)
    import_command = commands.add_parser("import", help="Import without overwriting scenes")
    import_command.add_argument("archive", type=Path)
    import_command.add_argument("--datasets", type=Path, default=PROJECT_ROOT / "datasets")
    arguments = parser.parse_args()
    try:
        if arguments.command == "export":
            print(export_scene_package(arguments.scene, arguments.archive))
        elif arguments.command == "import":
            print(import_scene_package(arguments.archive, arguments.datasets))
        else:
            print(json.dumps(validate_scene_package(arguments.archive).__dict__, indent=2))
    except ScenePackageError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
