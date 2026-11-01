"""Portable, integrity-checked SpatialForge scene package archives."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from spatialforge import __version__

from .schema import SceneManifest
from .store import SCENE_ID_PATTERN

PACKAGE_MANIFEST = "package_manifest.json"
MAX_ARCHIVE_FILES = 50_000
MAX_UNCOMPRESSED_BYTES = 100 * 1024**3


class ScenePackageError(RuntimeError):
    """Raised when a portable package is unsafe, corrupt, or incompatible."""


@dataclass(frozen=True)
class PackageValidation:
    scene_id: str
    file_count: int
    total_bytes: int
    package_version: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_files(scene_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(scene_dir.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_symlink():
            raise ScenePackageError(f"Scene packages cannot contain symbolic links: {path}")
        if path.is_file():
            files.append(path)
    return files


def export_scene_package(scene_dir: str | Path, archive_path: str | Path) -> Path:
    scene = Path(scene_dir).expanduser().resolve()
    archive = Path(archive_path).expanduser().resolve()
    if not scene.is_dir() or not SCENE_ID_PATTERN.fullmatch(scene.name):
        raise ScenePackageError("Source must be an existing scene_* directory")
    if not (scene / "metadata").is_dir():
        raise ScenePackageError("Scene is missing its metadata directory")
    if archive.exists():
        raise ScenePackageError(f"Archive already exists: {archive}")

    files = _portable_files(scene)
    entries = [
        {
            "path": path.relative_to(scene).as_posix(),
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in files
    ]
    manifest = {
        "package_schema_version": "1.0.0",
        "spatialforge_version": __version__,
        "scene_id": scene.name,
        "created_at": datetime.now(UTC).isoformat(),
        "files": entries,
        "total_bytes": sum(entry["size"] for entry in entries),
    }
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive.with_suffix(archive.suffix + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as package:
            package.writestr(PACKAGE_MANIFEST, json.dumps(manifest, indent=2))
            for path in files:
                package.write(path, path.relative_to(scene).as_posix())
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)
    return archive


def _validate_member_name(name: str) -> str:
    if not name or "\\" in name or name.startswith("/") or ":" in name:
        raise ScenePackageError(f"Unsafe archive member path: {name!r}")
    parts = name.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ScenePackageError(f"Unsafe archive member path: {name!r}")
    return PurePosixPath(name).as_posix()


def validate_scene_package(archive_path: str | Path) -> PackageValidation:
    archive = Path(archive_path).expanduser().resolve()
    if not archive.is_file():
        raise ScenePackageError(f"Scene package not found: {archive}")
    try:
        with zipfile.ZipFile(archive, "r") as package:
            infos = package.infolist()
            if len(infos) > MAX_ARCHIVE_FILES + 1:
                raise ScenePackageError("Scene package contains too many files")
            names = [_validate_member_name(info.filename) for info in infos]
            if len(names) != len(set(names)):
                raise ScenePackageError("Scene package contains duplicate paths")
            if PACKAGE_MANIFEST not in names:
                raise ScenePackageError("Scene package manifest is missing")
            total_uncompressed = sum(info.file_size for info in infos)
            if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                raise ScenePackageError("Scene package exceeds the uncompressed size limit")
            manifest: dict[str, Any] = json.loads(package.read(PACKAGE_MANIFEST))
            if manifest.get("package_schema_version") != "1.0.0":
                raise ScenePackageError("Unsupported scene package schema")
            scene_id = manifest.get("scene_id", "")
            if not SCENE_ID_PATTERN.fullmatch(scene_id):
                raise ScenePackageError("Package has an invalid scene identifier")
            declared = manifest.get("files")
            if not isinstance(declared, list):
                raise ScenePackageError("Package file inventory is invalid")
            actual_names = set(names) - {PACKAGE_MANIFEST}
            declared_names = {entry.get("path") for entry in declared if isinstance(entry, dict)}
            if declared_names != actual_names:
                raise ScenePackageError("Package inventory does not match archive contents")
            total = 0
            for entry in declared:
                path = _validate_member_name(entry["path"])
                payload = package.read(path)
                total += len(payload)
                if entry.get("size") != len(payload):
                    raise ScenePackageError(f"Size mismatch for {path}")
                if entry.get("sha256") != hashlib.sha256(payload).hexdigest():
                    raise ScenePackageError(f"Checksum mismatch for {path}")
            if manifest.get("total_bytes") != total:
                raise ScenePackageError("Package total byte count is invalid")
            return PackageValidation(scene_id, len(declared), total, manifest.get("spatialforge_version", "unknown"))
    except (zipfile.BadZipFile, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, ScenePackageError):
            raise
        raise ScenePackageError(f"Invalid scene package: {exc}") from exc


def import_scene_package(archive_path: str | Path, dataset_root: str | Path) -> Path:
    archive = Path(archive_path).expanduser().resolve()
    root = Path(dataset_root).expanduser().resolve()
    validation = validate_scene_package(archive)
    root.mkdir(parents=True, exist_ok=True)
    target = root / validation.scene_id
    if target.exists():
        raise ScenePackageError(f"Scene already exists and will not be overwritten: {target}")
    staging = Path(tempfile.mkdtemp(prefix=f".{validation.scene_id}-", dir=root))
    try:
        with zipfile.ZipFile(archive, "r") as package:
            for info in package.infolist():
                if info.filename == PACKAGE_MANIFEST:
                    continue
                relative = PurePosixPath(_validate_member_name(info.filename))
                destination = (staging / Path(*relative.parts)).resolve()
                destination.relative_to(staging)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with package.open(info, "r") as source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
        scene_manifest_path = staging / "metadata" / "scene_manifest.json"
        if not scene_manifest_path.is_file():
            raise ScenePackageError("Scene package is missing metadata/scene_manifest.json")
        try:
            scene_manifest = SceneManifest.model_validate_json(scene_manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ScenePackageError(f"Scene package has an invalid scene manifest: {exc}") from exc
        if scene_manifest.scene_id != validation.scene_id:
            raise ScenePackageError("Scene manifest identifier does not match the package identifier")
        for asset in scene_manifest.assets:
            portable_path = _validate_member_name(asset.path)
            resolved_asset = (staging / Path(*PurePosixPath(portable_path).parts)).resolve()
            try:
                resolved_asset.relative_to(staging)
            except ValueError as exc:
                raise ScenePackageError(f"Scene asset escapes the package root: {asset.path}") from exc
            if not resolved_asset.is_file():
                raise ScenePackageError(f"Scene package is missing declared asset: {asset.path}")
        staging.replace(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target
