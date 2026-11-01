"""Scene-scoped POI storage and routing service."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from pydantic import ValidationError

from spatialforge.scenes import SceneStore

from .grid import NavigationGridError, find_path, grid_to_world, nearest_walkable, path_length, simplify_path, world_to_grid
from .models import NavigationGrid, POI, POIDocument, RouteDestination, RouteRequest, RouteResponse


class NavigationServiceError(RuntimeError):
    pass


class NavigationService:
    _locks: dict[Path, threading.RLock] = {}
    _locks_guard = threading.Lock()

    def __init__(self, scene_store: SceneStore) -> None:
        self.store = scene_store

    def _lock(self, scene_dir: Path) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(scene_dir, threading.RLock())

    def _asset_path(self, scene_id: str, asset_type: str) -> Path:
        manifest = self.store.load_manifest(scene_id)
        asset = next((item for item in manifest.assets if item.type == asset_type), None)
        if asset is None:
            raise NavigationServiceError(f"Scene has no {asset_type} asset")
        return self.store.resolve_asset(scene_id, asset.path).path

    def load_pois(self, scene_id: str) -> POIDocument:
        path = self._asset_path(scene_id, "poi_metadata")
        try:
            return POIDocument.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, ValidationError) as exc:
            raise NavigationServiceError(f"Invalid POI data: {exc}") from exc

    def list_pois(self, scene_id: str, query: str = "", category: str = "") -> list[POI]:
        query = query.strip().casefold()
        category = category.strip().casefold()
        matches = []
        for poi in self.load_pois(scene_id).points:
            haystack = " ".join((poi.name, poi.category, poi.description, *poi.aliases)).casefold()
            if query and query not in haystack:
                continue
            if category and category != poi.category.casefold():
                continue
            matches.append(poi)
        return sorted(matches, key=lambda item: (item.name.casefold(), item.id))

    def get_poi(self, scene_id: str, poi_id: str) -> POI:
        poi = next((item for item in self.load_pois(scene_id).points if item.id == poi_id), None)
        if poi is None:
            raise NavigationServiceError(f"POI not found: {poi_id}")
        return poi

    def _validate_poi(self, scene_id: str, poi: POI) -> None:
        manifest = self.store.load_manifest(scene_id)
        minimum, maximum = manifest.bounding_box.minimum, manifest.bounding_box.maximum
        if any(value < low or value > high for value, low, high in zip(poi.position, minimum, maximum, strict=True)):
            raise NavigationServiceError("POI position is outside scene bounds")
        grid = self.load_grid(scene_id)
        for point in poi.arrival_points:
            cell = world_to_grid(point, grid)
            if not (0 <= cell[0] < grid.width and 0 <= cell[1] < grid.height) or grid.cells[cell[1]][cell[0]] != ".":
                raise NavigationServiceError("POI arrival point must be on a walkable grid cell")

    @staticmethod
    def _atomic_write(path: Path, document: POIDocument) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(prefix="pois-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(document.model_dump_json(indent=2))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, path)
        finally:
            Path(temporary_name).unlink(missing_ok=True)

    def create_poi(self, scene_id: str, poi: POI) -> POI:
        path = self._asset_path(scene_id, "poi_metadata")
        with self._lock(path.parent):
            document = self.load_pois(scene_id)
            if any(item.id == poi.id for item in document.points):
                raise NavigationServiceError(f"Duplicate POI identifier: {poi.id}")
            self._validate_poi(scene_id, poi)
            self._atomic_write(path, POIDocument(points=(*document.points, poi)))
        return poi

    def update_poi(self, scene_id: str, poi_id: str, poi: POI) -> POI:
        if poi.id != poi_id:
            raise NavigationServiceError("POI identifier cannot be changed")
        path = self._asset_path(scene_id, "poi_metadata")
        with self._lock(path.parent):
            document = self.load_pois(scene_id)
            if not any(item.id == poi_id for item in document.points):
                raise NavigationServiceError(f"POI not found: {poi_id}")
            self._validate_poi(scene_id, poi)
            points = tuple(poi if item.id == poi_id else item for item in document.points)
            self._atomic_write(path, POIDocument(points=points))
        return poi

    def delete_poi(self, scene_id: str, poi_id: str) -> None:
        path = self._asset_path(scene_id, "poi_metadata")
        with self._lock(path.parent):
            document = self.load_pois(scene_id)
            points = tuple(item for item in document.points if item.id != poi_id)
            if len(points) == len(document.points):
                raise NavigationServiceError(f"POI not found: {poi_id}")
            self._atomic_write(path, POIDocument(points=points))

    def load_grid(self, scene_id: str) -> NavigationGrid:
        path = self._asset_path(scene_id, "navigation_grid")
        try:
            return NavigationGrid.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, ValidationError) as exc:
            raise NavigationServiceError(f"Invalid navigation grid: {exc}") from exc

    def route(self, scene_id: str, request: RouteRequest) -> RouteResponse:
        grid = self.load_grid(scene_id)
        manifest = self.store.load_manifest(scene_id)
        poi = self.get_poi(scene_id, request.destination_poi_id) if request.destination_poi_id else None
        destination = poi.arrival_points[0] if poi else request.destination
        assert destination is not None
        start_cell, goal_cell = world_to_grid(request.start, grid), world_to_grid(destination, grid)
        connectivity = request.preferences.connectivity or grid.connectivity
        if request.preferences.resolve_nearest:
            resolved_start = nearest_walkable(start_cell, grid, request.preferences.clearance, request.preferences.max_snap_distance)
            resolved_goal = nearest_walkable(goal_cell, grid, request.preferences.clearance, request.preferences.max_snap_distance)
            if resolved_start is None:
                raise NavigationServiceError("No walkable start cell exists within the configured snap distance")
            if resolved_goal is None:
                raise NavigationServiceError("No walkable destination cell exists within the configured snap distance")
            start_cell, goal_cell = resolved_start, resolved_goal
        try:
            cells = find_path(start_cell, goal_cell, grid, connectivity, request.preferences.clearance)
        except NavigationGridError as exc:
            raise NavigationServiceError(str(exc)) from exc
        if request.preferences.simplify:
            cells = simplify_path(cells, grid, request.preferences.clearance)
        waypoints = [grid_to_world(cell, grid) for cell in cells]
        if world_to_grid(request.start, grid) == start_cell:
            waypoints[0] = (request.start[0], grid.floor_y, request.start[2])
        if world_to_grid(destination, grid) == goal_cell:
            waypoints[-1] = (destination[0], grid.floor_y, destination[2])
        units = "meter" if manifest.units.metric_scale_status == "known" else "scene_unit"
        return RouteResponse(
            waypoints=tuple(waypoints),
            route_length=round(path_length(waypoints), 4),
            distance_units=units,
            navigation_grid_version=grid.version,
            destination=RouteDestination(
                poi_id=poi.id if poi else None,
                name=poi.name if poi else None,
                position=destination,
            ),
        )
