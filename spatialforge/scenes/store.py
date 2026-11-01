"""Safe access to independent scene packages below a configured root."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from .schema import SceneAsset, SceneManifest

SCENE_ID_PATTERN = re.compile(r"^scene_[A-Za-z0-9_-]+$")


class SceneStoreError(RuntimeError):
    pass


class SceneNotFoundError(SceneStoreError):
    pass


class SceneManifestError(SceneStoreError):
    pass


class SceneAssetError(SceneStoreError):
    pass


@dataclass(frozen=True)
class ResolvedAsset:
    definition: SceneAsset
    path: Path


class SceneStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    @staticmethod
    def validate_scene_id(scene_id: str) -> str:
        if not SCENE_ID_PATTERN.fullmatch(scene_id):
            raise SceneStoreError("Invalid scene identifier")
        return scene_id

    def scene_dir(self, scene_id: str) -> Path:
        self.validate_scene_id(scene_id)
        scene = (self.root / scene_id).resolve()
        try:
            scene.relative_to(self.root)
        except ValueError as exc:
            raise SceneStoreError("Scene path escapes dataset root") from exc
        if not scene.is_dir():
            raise SceneNotFoundError(f"Scene not found: {scene_id}")
        return scene

    def manifest_path(self, scene_id: str) -> Path:
        return self.scene_dir(scene_id) / "metadata" / "scene_manifest.json"

    def load_manifest(self, scene_id: str) -> SceneManifest:
        path = self.manifest_path(scene_id)
        if not path.is_file():
            raise SceneNotFoundError(f"Scene manifest not found: {scene_id}")
        try:
            return SceneManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValidationError, ValueError, OSError, json.JSONDecodeError) as exc:
            raise SceneManifestError(f"Invalid scene manifest for {scene_id}: {exc}") from exc

    def update_scene_name(self, scene_id: str, new_name: str) -> SceneManifest:
        clean = new_name.strip()
        if not clean:
            raise SceneStoreError("Scene name cannot be empty")
        manifest = self.load_manifest(scene_id)
        path = self.manifest_path(scene_id)
        updated = manifest.model_copy(update={"scene_name": clean})
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
        temp_path.replace(path)
        return updated

    def list_manifests(self) -> list[SceneManifest]:
        if not self.root.is_dir():
            return []
        manifests: list[SceneManifest] = []
        for scene in sorted(self.root.iterdir(), key=lambda item: item.name.lower()):
            if not scene.is_dir() or not SCENE_ID_PATTERN.fullmatch(scene.name):
                continue
            try:
                manifests.append(self.load_manifest(scene.name))
            except SceneStoreError:
                continue
        return manifests

    def resolve_asset(self, scene_id: str, asset_path: str) -> ResolvedAsset:
        if not asset_path or "\\" in asset_path or asset_path.startswith("/") or ":" in asset_path:
            raise SceneAssetError("Invalid asset path")
        parts = asset_path.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise SceneAssetError("Asset path traversal is not allowed")
        portable = PurePosixPath(asset_path).as_posix()
        manifest = self.load_manifest(scene_id)
        definition = next((asset for asset in manifest.assets if asset.path == portable), None)
        if definition is None:
            raise SceneAssetError("Asset is not declared by this scene manifest")
        scene = self.scene_dir(scene_id)
        resolved = (scene / Path(*PurePosixPath(portable).parts)).resolve()
        try:
            resolved.relative_to(scene)
        except ValueError as exc:
            raise SceneAssetError("Asset path escapes scene directory") from exc
        if not resolved.is_file():
            raise SceneAssetError(f"Scene asset is missing: {portable}")
        return ResolvedAsset(definition, resolved)
