"""Versioned data contracts for POIs, navigation grids, and routes."""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Vector3 = tuple[float, float, float]


class NavigationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class POI(NavigationModel):
    id: Annotated[str, Field(pattern=r"^poi_[A-Za-z0-9_-]+$")]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    category: Annotated[str, Field(min_length=1, max_length=60)] = "place"
    description: Annotated[str, Field(max_length=500)] = ""
    aliases: tuple[Annotated[str, Field(min_length=1, max_length=80)], ...] = ()
    position: Vector3
    arrival_points: tuple[Vector3, ...] = ()
    floor_id: Annotated[str, Field(min_length=1, max_length=64)] = "ground"
    bounds: tuple[Vector3, Vector3] | None = None
    zone: str | None = None

    @field_validator("position", "arrival_points")
    @classmethod
    def finite_coordinates(cls, value):
        vectors = (value,) if len(value) == 3 and isinstance(value[0], (int, float)) else value
        if any(not math.isfinite(component) for vector in vectors for component in vector):
            raise ValueError("Coordinates must be finite")
        return value

    @model_validator(mode="after")
    def default_arrival(self) -> "POI":
        if not self.arrival_points:
            self.arrival_points = (self.position,)
        if self.bounds and any(a > b for a, b in zip(self.bounds[0], self.bounds[1], strict=True)):
            raise ValueError("POI bounds minimum cannot exceed maximum")
        return self


class POIDocument(NavigationModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    points: tuple[POI, ...] = ()


class NavigationGrid(NavigationModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    version: Annotated[str, Field(min_length=1, max_length=64)]
    coordinate_system: Literal["SpatialForge right-handed Y-up"]
    floor_id: str = "ground"
    floor_y: float = 0.0
    origin: Vector3
    resolution: Annotated[float, Field(gt=0, le=10)]
    width: Annotated[int, Field(gt=0, le=10000)]
    height: Annotated[int, Field(gt=0, le=10000)]
    connectivity: Literal[4, 8] = 4
    cells: tuple[str, ...]
    unit: Literal["meter", "scene_unit"]
    metric_scale_status: Literal["known", "estimated", "arbitrary"]

    @model_validator(mode="after")
    def validate_cells(self) -> "NavigationGrid":
        if len(self.cells) != self.height or any(len(row) != self.width for row in self.cells):
            raise ValueError("Navigation grid dimensions do not match cells")
        if any(character not in ".#" for row in self.cells for character in row):
            raise ValueError("Navigation grid cells must use '.' (walkable) or '#' (blocked)")
        return self


class RoutePreferences(NavigationModel):
    connectivity: Literal[4, 8] | None = None
    clearance: Annotated[float, Field(ge=0, le=5)] = 0.0
    simplify: bool = True
    resolve_nearest: bool = False
    max_snap_distance: Annotated[float, Field(gt=0, le=10)] = 1.0


class RouteRequest(NavigationModel):
    start: Vector3
    destination_poi_id: str | None = None
    destination: Vector3 | None = None
    preferences: RoutePreferences = RoutePreferences()

    @model_validator(mode="after")
    def exactly_one_destination(self) -> "RouteRequest":
        if (self.destination_poi_id is None) == (self.destination is None):
            raise ValueError("Provide exactly one of destination_poi_id or destination")
        for vector in (self.start, self.destination):
            if vector is not None and any(not math.isfinite(component) for component in vector):
                raise ValueError("Coordinates must be finite")
        return self


class RouteDestination(NavigationModel):
    poi_id: str | None = None
    name: str | None = None
    position: Vector3


class RouteResponse(NavigationModel):
    status: Literal["completed"] = "completed"
    waypoints: tuple[Vector3, ...]
    route_length: float
    distance_units: Literal["meter", "scene_unit"]
    navigation_grid_version: str
    destination: RouteDestination
