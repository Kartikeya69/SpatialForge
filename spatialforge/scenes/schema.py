"""Versioned scene package contract shared by reconstruction and web clients."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Vector3 = tuple[float, float, float]
Matrix4 = tuple[
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CoordinateSystem(StrictModel):
    handedness: Literal["right"] = "right"
    up_axis: Literal["Y"] = "Y"
    forward_axis: Literal["-Z"] = "-Z"
    source_convention: str
    source_to_scene_matrix_row_major: Matrix4


class Units(StrictModel):
    name: Literal["meter", "scene_unit"]
    metric_scale_status: Literal["known", "estimated", "arbitrary"]
    meters_per_unit: float | None = None

    @model_validator(mode="after")
    def validate_scale(self) -> "Units":
        if self.metric_scale_status == "known" and (
            self.meters_per_unit is None or self.meters_per_unit <= 0
        ):
            raise ValueError("Known metric scale requires positive meters_per_unit")
        if self.meters_per_unit is not None and self.meters_per_unit <= 0:
            raise ValueError("meters_per_unit must be positive")
        return self


class BoundingBox(StrictModel):
    minimum: Vector3
    maximum: Vector3

    @model_validator(mode="after")
    def validate_extents(self) -> "BoundingBox":
        if any(low >= high for low, high in zip(self.minimum, self.maximum, strict=True)):
            raise ValueError("Bounding box minimum must be less than maximum on every axis")
        return self


AssetType = Literal[
    "glb",
    "gltf",
    "ply",
    "ply_mesh",
    "gaussian_splat",
    "navigation_grid",
    "collider_geometry",
    "camera_poses",
    "poi_metadata",
    "texture",
    "image",
]


class SceneAsset(StrictModel):
    id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
    type: AssetType
    path: str
    role: Literal["primary_visual", "diagnostic", "navigation", "metadata", "texture"]
    mime_type: str
    required: bool = True
    visible_by_default: bool = True

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value or "\\" in value or value.startswith("/") or ":" in value:
            raise ValueError("Asset paths must be non-empty portable relative paths")
        raw_parts = value.split("/")
        if any(part in {"", ".", ".."} for part in raw_parts):
            raise ValueError("Asset paths cannot contain empty, current, or parent segments")
        path = PurePosixPath(value)
        if path.is_absolute():
            raise ValueError("Asset path must be relative")
        return path.as_posix()


class ReconstructionMetadata(StrictModel):
    backend: str
    backend_version: str | None = None
    source: Literal["reconstruction", "synthetic", "imported"]
    status: Literal["completed", "demonstration", "pending", "failed"]
    metric_scale_calibrated: bool = False


class NavigationMetadata(StrictModel):
    enabled: bool
    spawn_position: Vector3
    spawn_yaw_degrees: float = 0
    camera_height: Annotated[float, Field(gt=0, le=3)] = 1.65
    movement_speed: Annotated[float, Field(gt=0, le=20)] = 2.5
    collision_radius: Annotated[float, Field(gt=0, le=2)] = 0.25
    collider_asset_id: str | None = None
    grid_asset_id: str | None = None
    zones: tuple[str, ...] = ()


class PoiMetadata(StrictModel):
    asset_id: str | None = None
    count: Annotated[int, Field(ge=0)] = 0


class CameraMetadata(StrictModel):
    pose_asset_id: str | None = None
    pose_convention: Literal["camera_to_world", "world_to_camera", "both"] = "both"


class ViewerSettings(StrictModel):
    background: str = "#07111f"
    ambient_light_intensity: Annotated[float, Field(ge=0, le=10)] = 0.8
    directional_light_intensity: Annotated[float, Field(ge=0, le=10)] = 1.8
    point_size: Annotated[float, Field(gt=0, le=1)] = 0.035
    is_2_5d: bool = False
    source_camera_position: Vector3 | None = None
    source_camera_look_at: Vector3 | None = None
    source_camera_fov: float | None = None


class SceneManifest(StrictModel):
    schema_version: Literal["1.0.0"]
    scene_id: Annotated[str, Field(pattern=r"^scene_[A-Za-z0-9_-]+$")]
    scene_name: Annotated[str, Field(min_length=1, max_length=120)]
    description: str = ""
    synthetic_demo: bool = False
    processing_status: Literal["completed", "demonstration", "pending", "failed"]
    coordinate_system: CoordinateSystem
    units: Units
    origin: Vector3
    bounding_box: BoundingBox
    reconstruction: ReconstructionMetadata
    assets: tuple[SceneAsset, ...]
    camera_metadata: CameraMetadata = CameraMetadata()
    navigation: NavigationMetadata
    poi_metadata: PoiMetadata = PoiMetadata()
    viewer: ViewerSettings = ViewerSettings()

    @model_validator(mode="after")
    def validate_references(self) -> "SceneManifest":
        ids = [asset.id for asset in self.assets]
        paths = [asset.path for asset in self.assets]
        if len(ids) != len(set(ids)):
            raise ValueError("Scene asset IDs must be unique")
        if len(paths) != len(set(paths)):
            raise ValueError("Scene asset paths must be unique")
        asset_types = {asset.id: asset.type for asset in self.assets}
        references = {
            "navigation.collider_asset_id": self.navigation.collider_asset_id,
            "navigation.grid_asset_id": self.navigation.grid_asset_id,
            "camera_metadata.pose_asset_id": self.camera_metadata.pose_asset_id,
            "poi_metadata.asset_id": self.poi_metadata.asset_id,
        }
        for label, asset_id in references.items():
            if asset_id is not None and asset_id not in asset_types:
                raise ValueError(f"{label} references unknown asset '{asset_id}'")
        if self.navigation.collider_asset_id and asset_types[self.navigation.collider_asset_id] != "collider_geometry":
            raise ValueError("collider_asset_id must reference collider_geometry")
        if self.navigation.grid_asset_id and asset_types[self.navigation.grid_asset_id] != "navigation_grid":
            raise ValueError("grid_asset_id must reference navigation_grid")
        if self.camera_metadata.pose_asset_id and asset_types[self.camera_metadata.pose_asset_id] != "camera_poses":
            raise ValueError("pose_asset_id must reference camera_poses")
        if self.poi_metadata.asset_id and asset_types[self.poi_metadata.asset_id] != "poi_metadata":
            raise ValueError("poi_metadata.asset_id must reference poi_metadata")
        if self.synthetic_demo and self.reconstruction.source != "synthetic":
            raise ValueError("Synthetic demos must declare reconstruction.source='synthetic'")
        return self
