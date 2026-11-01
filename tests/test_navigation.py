from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import spatialforge.api.main as api
from spatialforge.navigation import NavigationService, POI, RouteRequest
from spatialforge.navigation.grid import NavigationGridError, find_path, grid_to_world, nearest_walkable, simplify_path, world_to_grid
from spatialforge.navigation.models import NavigationGrid, RoutePreferences
from spatialforge.scenes import SceneStore
from spatialforge.scenes.demo import create_demo_scene


@pytest.fixture
def navigation_service(tmp_path: Path) -> NavigationService:
    create_demo_scene(tmp_path)
    return NavigationService(SceneStore(tmp_path))


def test_grid_world_round_trip(navigation_service: NavigationService) -> None:
    grid = navigation_service.load_grid("scene_synthetic_loft")
    cell = world_to_grid((-3.9, 1.65, -3.5), grid)
    world = grid_to_world(cell, grid)
    assert world_to_grid(world, grid) == cell
    assert abs(world[0] + 3.9) <= grid.resolution


def test_route_avoids_obstacles_and_is_deterministic(navigation_service: NavigationService) -> None:
    request = RouteRequest(
        start=(-4.5, 1.65, -3.7),
        destination_poi_id="poi_meeting_a",
        preferences=RoutePreferences(connectivity=8, clearance=0.28),
    )
    first = navigation_service.route("scene_synthetic_loft", request)
    second = navigation_service.route("scene_synthetic_loft", request)
    grid = navigation_service.load_grid("scene_synthetic_loft")
    assert first.waypoints == second.waypoints
    assert first.route_length > 0
    assert all(grid.cells[row][column] == "." for column, row in (world_to_grid(point, grid) for point in first.waypoints))
    assert first.distance_units == "meter"


def test_blocked_start_and_destination_are_rejected(navigation_service: NavigationService) -> None:
    grid = navigation_service.load_grid("scene_synthetic_loft")
    with pytest.raises(NavigationGridError, match="Start"):
        find_path(world_to_grid((-3.1, 0, 0.8), grid), world_to_grid((-4, 0, -3), grid), grid, 4, 0)
    with pytest.raises(NavigationGridError, match="Destination"):
        find_path(world_to_grid((-4, 0, -3), grid), world_to_grid((-3.1, 0, 0.8), grid), grid, 4, 0)


def test_diagonal_corner_cutting_is_prevented() -> None:
    grid = NavigationGrid(
        version="corner", coordinate_system="SpatialForge right-handed Y-up", origin=(0, 0, 0),
        resolution=1, width=2, height=2, connectivity=8, cells=(".#", "#."
        ), unit="scene_unit", metric_scale_status="arbitrary"
    )
    with pytest.raises(NavigationGridError, match="No path"):
        find_path((0, 0), (1, 1), grid, 8, 0)


def test_clearance_can_make_corridor_unavailable() -> None:
    grid = NavigationGrid(
        version="clearance", coordinate_system="SpatialForge right-handed Y-up", origin=(0, 0, 0),
        resolution=1, width=3, height=3, connectivity=4, cells=("###", "...", "###"),
        unit="scene_unit", metric_scale_status="arbitrary"
    )
    assert len(find_path((0, 1), (2, 1), grid, 4, 0)) == 3
    with pytest.raises(NavigationGridError):
        find_path((0, 1), (2, 1), grid, 4, 0.6)


def test_nearest_cell_resolution_is_bounded_and_deterministic() -> None:
    grid = NavigationGrid(
        version="snap", coordinate_system="SpatialForge right-handed Y-up", origin=(0, 0, 0),
        resolution=1, width=5, height=3, connectivity=4, cells=("#####", "#...#", "#####"),
        unit="scene_unit", metric_scale_status="arbitrary"
    )
    assert nearest_walkable((0, 1), grid, 0, 1.1) == (1, 1)
    assert nearest_walkable((0, 0), grid, 0, 0.9) is None


def test_path_smoothing_preserves_obstacle_boundaries() -> None:
    grid = NavigationGrid(
        version="smooth", coordinate_system="SpatialForge right-handed Y-up", origin=(0, 0, 0),
        resolution=1, width=5, height=5, connectivity=8, cells=(".....", "..#..", "..#..", "..#..", "....."),
        unit="scene_unit", metric_scale_status="arbitrary"
    )
    path = find_path((0, 2), (4, 2), grid, 8, 0)
    smoothed = simplify_path(path, grid, 0)
    assert len(smoothed) < len(path)
    assert len(smoothed) > 2  # A direct segment would cross the wall.


def test_poi_crud_search_alias_and_atomic_concurrency(navigation_service: NavigationService) -> None:
    scene_id = "scene_synthetic_loft"
    poi = POI(id="poi_print_lab", name="Print Lab", category="room", aliases=("3d printer",), position=(-4, 0.04, -3), arrival_points=((-4, 0.04, -3),))
    navigation_service.create_poi(scene_id, poi)
    assert navigation_service.list_pois(scene_id, "3d printer")[0].id == poi.id
    updated = poi.model_copy(update={"name": "Fabrication Lab"})
    navigation_service.update_poi(scene_id, poi.id, updated)
    assert navigation_service.get_poi(scene_id, poi.id).name == "Fabrication Lab"

    def add(index: int) -> None:
        navigation_service.create_poi(scene_id, POI(id=f"poi_concurrent_{index}", name=f"Desk {index}", position=(-4 + index * 0.1, 0.04, -3), arrival_points=((-4 + index * 0.1, 0.04, -3),)))

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(add, range(4)))
    assert len([point for point in navigation_service.list_pois(scene_id) if point.id.startswith("poi_concurrent")]) == 4
    navigation_service.delete_poi(scene_id, poi.id)
    with pytest.raises(Exception, match="not found"):
        navigation_service.get_poi(scene_id, poi.id)


def test_invalid_poi_coordinate_and_duplicate(navigation_service: NavigationService) -> None:
    scene_id = "scene_synthetic_loft"
    with pytest.raises(Exception, match="outside scene bounds"):
        navigation_service.create_poi(scene_id, POI(id="poi_far", name="Far", position=(999, 0, 999)))
    existing = navigation_service.get_poi(scene_id, "poi_reception")
    with pytest.raises(Exception, match="Duplicate"):
        navigation_service.create_poi(scene_id, existing)


def test_navigation_api_end_to_end(tmp_path: Path, monkeypatch) -> None:
    create_demo_scene(tmp_path)
    monkeypatch.setattr(api, "DATASET_ROOT", tmp_path)
    client = TestClient(api.app)
    search = client.get("/api/v1/scenes/scene_synthetic_loft/pois?q=conference")
    assert search.status_code == 200
    assert search.json()["points"][0]["id"] == "poi_meeting_a"
    response = client.post("/api/v1/scenes/scene_synthetic_loft/routes", json={"start": [-4.5, 1.65, -3.7], "destination_poi_id": "poi_meeting_a", "preferences": {"connectivity": 8, "clearance": 0.28, "simplify": True}})
    assert response.status_code == 200
    assert len(response.json()["waypoints"]) >= 2
    assert response.json()["route_length"] > 0


def test_non_metric_scene_reports_scene_units(navigation_service: NavigationService) -> None:
    path = navigation_service.store.manifest_path("scene_synthetic_loft")
    import json
    document = json.loads(path.read_text(encoding="utf-8"))
    document["units"] = {"name": "scene_unit", "metric_scale_status": "arbitrary", "meters_per_unit": None}
    path.write_text(json.dumps(document), encoding="utf-8")
    result = navigation_service.route("scene_synthetic_loft", RouteRequest(start=(-4.5, 0, -3.7), destination_poi_id="poi_reception"))
    assert result.distance_units == "scene_unit"
