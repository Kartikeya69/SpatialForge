"""Deterministic synthetic indoor scene package for local viewer development."""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path
from typing import Any

IDENTITY_MATRIX = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def _cube_geometry() -> tuple[list[float], list[float], list[int]]:
    faces = [
        ((0, 0, 1), [(-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)]),
        ((0, 0, -1), [(0.5, -0.5, -0.5), (-0.5, -0.5, -0.5), (-0.5, 0.5, -0.5), (0.5, 0.5, -0.5)]),
        ((1, 0, 0), [(0.5, -0.5, 0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (0.5, 0.5, 0.5)]),
        ((-1, 0, 0), [(-0.5, -0.5, -0.5), (-0.5, -0.5, 0.5), (-0.5, 0.5, 0.5), (-0.5, 0.5, -0.5)]),
        ((0, 1, 0), [(-0.5, 0.5, 0.5), (0.5, 0.5, 0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5)]),
        ((0, -1, 0), [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, -0.5, 0.5), (-0.5, -0.5, 0.5)]),
    ]
    positions: list[float] = []
    normals: list[float] = []
    indices: list[int] = []
    for face_index, (normal, vertices) in enumerate(faces):
        for vertex in vertices:
            positions.extend(vertex)
            normals.extend(normal)
        offset = face_index * 4
        indices.extend([offset, offset + 1, offset + 2, offset, offset + 2, offset + 3])
    return positions, normals, indices


def _write_gltf(path: Path, objects: list[dict[str, Any]]) -> None:
    positions, normals, indices = _cube_geometry()
    position_bytes = struct.pack(f"<{len(positions)}f", *positions)
    normal_bytes = struct.pack(f"<{len(normals)}f", *normals)
    index_bytes = struct.pack(f"<{len(indices)}H", *indices)
    buffer = position_bytes + normal_bytes + index_bytes
    colors = {
        "floor": [0.10, 0.16, 0.22, 1],
        "wall": [0.62, 0.69, 0.74, 1],
        "furniture": [0.12, 0.52, 0.48, 1],
        "accent": [0.96, 0.52, 0.22, 1],
    }
    material_names = list(colors)
    document = {
        "asset": {"version": "2.0", "generator": "SpatialForge deterministic demo generator"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(objects)))}],
        "nodes": [
            {
                "name": item["name"],
                "mesh": material_names.index(item["material"]),
                "translation": item["center"],
                "scale": item["size"],
            }
            for item in objects
        ],
        "meshes": [
            {"name": f"unit_cube_{name}", "primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2, "material": index}]}
            for index, name in enumerate(material_names)
        ],
        "materials": [
            {
                "name": name,
                "pbrMetallicRoughness": {
                    "baseColorFactor": color,
                    "metallicFactor": 0.05,
                    "roughnessFactor": 0.82,
                },
            }
            for name, color in colors.items()
        ],
        "buffers": [
            {
                "byteLength": len(buffer),
                "uri": "data:application/octet-stream;base64," + base64.b64encode(buffer).decode("ascii"),
            }
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(position_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": len(position_bytes), "byteLength": len(normal_bytes), "target": 34962},
            {
                "buffer": 0,
                "byteOffset": len(position_bytes) + len(normal_bytes),
                "byteLength": len(index_bytes),
                "target": 34963,
            },
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 24,
                "type": "VEC3",
                "min": [-0.5, -0.5, -0.5],
                "max": [0.5, 0.5, 0.5],
            },
            {"bufferView": 1, "componentType": 5126, "count": 24, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5123, "count": 36, "type": "SCALAR"},
        ],
    }
    path.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")


def _box(name: str, center: list[float], size: list[float], material: str, collision: bool = True) -> dict[str, Any]:
    return {"name": name, "center": center, "size": size, "material": material, "collision": collision}


def _navigation_grid(objects: list[dict[str, Any]]) -> dict[str, Any]:
    resolution = 0.25
    origin = [-5.75, 0, -4.75]
    width, height = 46, 38
    rows: list[str] = []
    floor_obstacles = []
    for item in objects:
        if not item["collision"]:
            continue
        center, size = item["center"], item["size"]
        minimum_y = center[1] - size[1] / 2
        if minimum_y > 0.3:  # Door headers are not floor obstacles.
            continue
        floor_obstacles.append(
            (
                center[0] - size[0] / 2,
                center[0] + size[0] / 2,
                center[2] - size[2] / 2,
                center[2] + size[2] / 2,
            )
        )
    for row in range(height):
        z = origin[2] + (row + 0.5) * resolution
        cells = []
        for column in range(width):
            x = origin[0] + (column + 0.5) * resolution
            cell_x_min, cell_x_max = x - resolution / 2, x + resolution / 2
            cell_z_min, cell_z_max = z - resolution / 2, z + resolution / 2
            blocked = any(
                cell_x_max >= x_min and cell_x_min <= x_max and cell_z_max >= z_min and cell_z_min <= z_max
                for x_min, x_max, z_min, z_max in floor_obstacles
            )
            cells.append("#" if blocked else ".")
        rows.append("".join(cells))
    return {
        "schema_version": "1.0.0",
        "version": "synthetic-grid-1",
        "coordinate_system": "SpatialForge right-handed Y-up",
        "floor_id": "ground",
        "floor_y": 0.04,
        "origin": origin,
        "resolution": resolution,
        "width": width,
        "height": height,
        "connectivity": 8,
        "cells": rows,
        "unit": "meter",
        "metric_scale_status": "known",
    }


def create_demo_scene(dataset_root: str | Path) -> Path:
    scene_id = "scene_synthetic_loft"
    scene = Path(dataset_root).expanduser().resolve() / scene_id
    for directory in ("assets", "metadata", "navigation"):
        (scene / directory).mkdir(parents=True, exist_ok=True)

    objects = [
        _box("floor", [0, -0.05, 0], [12, 0.1, 10], "floor", False),
        _box("wall_back", [0, 1.5, 4.9], [12, 3, 0.2], "wall"),
        _box("wall_left", [-5.9, 1.5, 0], [0.2, 3, 10], "wall"),
        _box("wall_right", [5.9, 1.5, 0], [0.2, 3, 10], "wall"),
        _box("front_left", [-3.375, 1.5, -4.9], [5.25, 3, 0.2], "wall"),
        _box("front_right", [3.375, 1.5, -4.9], [5.25, 3, 0.2], "wall"),
        _box("front_door_header", [0, 2.6, -4.9], [1.5, 0.8, 0.2], "wall"),
        _box("divider_a", [0, 1.5, -2.375], [0.18, 3, 5.25], "wall"),
        _box("divider_b", [0, 1.5, 3.375], [0.18, 3, 3.25], "wall"),
        _box("divider_header", [0, 2.6, 1], [0.18, 0.8, 1.5], "wall"),
        _box("studio_table", [-3.1, 0.45, 0.8], [2.2, 0.9, 1.15], "furniture"),
        _box("studio_console", [-4.7, 0.55, 3.6], [1.4, 1.1, 0.65], "accent"),
        _box("lounge_sofa", [3.3, 0.5, 2.9], [2.6, 1, 1], "accent"),
        _box("lounge_table", [2.7, 0.35, 0.3], [1.5, 0.7, 1.1], "furniture"),
        _box("shelf", [5.1, 1.15, -1.9], [0.8, 2.3, 2.3], "furniture"),
    ]
    _write_gltf(scene / "assets" / "demo-room.gltf", objects)

    colliders = []
    for item in objects:
        if not item["collision"]:
            continue
        center, size = item["center"], item["size"]
        colliders.append(
            {
                "id": item["name"],
                "minimum": [center[index] - size[index] / 2 for index in range(3)],
                "maximum": [center[index] + size[index] / 2 for index in range(3)],
            }
        )
    collider_document = {
        "schema_version": "1.0.0",
        "coordinate_system": "SpatialForge right-handed Y-up",
        "walkable_bounds": {"minimum": [-5.7, 0, -4.7], "maximum": [5.7, 2.8, 4.7]},
        "colliders": colliders,
    }
    (scene / "navigation" / "colliders.json").write_text(
        json.dumps(collider_document, indent=2), encoding="utf-8"
    )

    navigation_grid = _navigation_grid(objects)
    (scene / "navigation" / "grid.json").write_text(
        json.dumps(navigation_grid, indent=2), encoding="utf-8"
    )

    pois = {
        "schema_version": "1.0.0",
        "points": [
            {"id": "poi_reception", "name": "Reception", "category": "service", "description": "Visitor check-in near the main entrance.", "aliases": ["front desk", "check in"], "position": [-3.9, 0.04, -3.5], "arrival_points": [[-3.9, 0.04, -3.5]], "floor_id": "ground", "zone": "entry"},
            {"id": "poi_meeting_a", "name": "Meeting Room A", "category": "room", "description": "Primary collaboration room.", "aliases": ["conference room", "meeting"], "position": [3.6, 0.04, 3.9], "arrival_points": [[1.2, 0.04, 1.1]], "floor_id": "ground", "zone": "meeting"},
            {"id": "poi_restroom", "name": "Restroom", "category": "facility", "description": "Ground-floor accessible restroom.", "aliases": ["washroom", "toilet"], "position": [4.2, 0.04, -3.2], "arrival_points": [[3.7, 0.04, -3.2]], "floor_id": "ground", "zone": "facilities"},
            {"id": "poi_studio_table", "name": "Studio Table", "category": "furniture", "description": "Prototype work table.", "aliases": ["workbench", "desk"], "position": [-3.1, 0.9, 0.8], "arrival_points": [[-1.6, 0.04, 0.8]], "floor_id": "ground", "zone": "studio"},
            {"id": "poi_lounge_sofa", "name": "Lounge Sofa", "category": "furniture", "description": "Collaboration lounge seating.", "aliases": ["couch", "seating"], "position": [3.3, 1.0, 2.9], "arrival_points": [[1.5, 0.04, 2.9]], "floor_id": "ground", "zone": "lounge"},
            {"id": "poi_exit", "name": "Main Exit", "category": "entrance", "description": "Main building entrance and exit.", "aliases": ["door", "entrance"], "position": [0, 1.2, -4.65], "arrival_points": [[0, 0.04, -4.4]], "floor_id": "ground", "zone": "entry"},
        ],
    }
    (scene / "metadata" / "pois.json").write_text(json.dumps(pois, indent=2), encoding="utf-8")
    camera_poses = {
        "schema_version": "1.0.0",
        "synthetic_demo": True,
        "pose_convention": "camera_to_world",
        "positions": [[-4, 1.65, -3.5], [-3, 1.65, -1], [-1, 1.65, 1], [2, 1.65, 1], [4, 1.65, 3]],
    }
    (scene / "metadata" / "camera_poses.json").write_text(
        json.dumps(camera_poses, indent=2), encoding="utf-8"
    )

    points: list[tuple[float, float, float, int, int, int]] = []
    for x_index in range(-12, 13):
        for z_index in range(-10, 11):
            if abs(x_index) == 12 or abs(z_index) == 10:
                points.append((x_index / 2, 0.03, z_index / 2, 74, 222, 188))
    ply_lines = [
        "ply",
        "format ascii 1.0",
        f"element vertex {len(points)}",
        "property float x",
        "property float y",
        "property float z",
        "property uchar red",
        "property uchar green",
        "property uchar blue",
        "end_header",
        *(" ".join(map(str, point)) for point in points),
    ]
    (scene / "assets" / "diagnostic-points.ply").write_text("\n".join(ply_lines) + "\n", encoding="ascii")

    manifest = {
        "schema_version": "1.0.0",
        "scene_id": scene_id,
        "scene_name": "Synthetic Twin Lab",
        "description": "Deterministic multi-zone indoor navigation demo with explicit walkability data. Not a reconstruction.",
        "synthetic_demo": True,
        "processing_status": "demonstration",
        "coordinate_system": {
            "handedness": "right",
            "up_axis": "Y",
            "forward_axis": "-Z",
            "source_convention": "SpatialForge synthetic Y-up",
            "source_to_scene_matrix_row_major": IDENTITY_MATRIX,
        },
        "units": {"name": "meter", "metric_scale_status": "known", "meters_per_unit": 1},
        "origin": [0, 0, 0],
        "bounding_box": {"minimum": [-6, -0.1, -5], "maximum": [6, 3, 5]},
        "reconstruction": {
            "backend": "synthetic_generator",
            "backend_version": "1.0.0",
            "source": "synthetic",
            "status": "demonstration",
            "metric_scale_calibrated": True,
        },
        "assets": [
            {"id": "demo_model", "type": "gltf", "path": "assets/demo-room.gltf", "role": "primary_visual", "mime_type": "model/gltf+json"},
            {"id": "diagnostic_points", "type": "ply", "path": "assets/diagnostic-points.ply", "role": "diagnostic", "mime_type": "application/octet-stream", "visible_by_default": False},
            {"id": "colliders", "type": "collider_geometry", "path": "navigation/colliders.json", "role": "navigation", "mime_type": "application/json", "visible_by_default": False},
            {"id": "navigation_grid", "type": "navigation_grid", "path": "navigation/grid.json", "role": "navigation", "mime_type": "application/json", "visible_by_default": False},
            {"id": "camera_poses", "type": "camera_poses", "path": "metadata/camera_poses.json", "role": "diagnostic", "mime_type": "application/json", "visible_by_default": False},
            {"id": "pois", "type": "poi_metadata", "path": "metadata/pois.json", "role": "metadata", "mime_type": "application/json", "visible_by_default": False},
        ],
        "camera_metadata": {"pose_asset_id": "camera_poses", "pose_convention": "camera_to_world"},
        "navigation": {
            "enabled": True,
            "spawn_position": [-4.5, 1.65, -3.7],
            "spawn_yaw_degrees": -130,
            "camera_height": 1.65,
            "movement_speed": 2.5,
            "collision_radius": 0.28,
            "collider_asset_id": "colliders",
            "grid_asset_id": "navigation_grid",
            "zones": ["entry", "studio", "lounge", "meeting", "facilities"],
        },
        "poi_metadata": {"asset_id": "pois", "count": 6},
        "viewer": {"background": "#06131d", "ambient_light_intensity": 0.85, "directional_light_intensity": 2.1, "point_size": 0.045},
    }
    (scene / "metadata" / "scene_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return scene
