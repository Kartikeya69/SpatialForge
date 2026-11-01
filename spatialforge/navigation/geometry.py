"""Conservative draft navigation extraction from aligned PLY geometry."""

from __future__ import annotations

import json
import math
import struct
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np

from .models import NavigationGrid


class GeometryNavigationError(RuntimeError):
    pass


_PLY_TYPES = {
    "char": ("b", 1), "uchar": ("B", 1), "int8": ("b", 1), "uint8": ("B", 1),
    "short": ("h", 2), "ushort": ("H", 2), "int16": ("h", 2), "uint16": ("H", 2),
    "int": ("i", 4), "uint": ("I", 4), "int32": ("i", 4), "uint32": ("I", 4),
    "float": ("f", 4), "float32": ("f", 4), "double": ("d", 8), "float64": ("d", 8),
}


def load_ply_vertices(path: str | Path) -> np.ndarray:
    source = Path(path).expanduser().resolve()
    if source.suffix.lower() != ".ply" or not source.is_file():
        raise GeometryNavigationError("Geometry bridge currently requires an existing .ply file")
    with source.open("rb") as stream:
        header: list[str] = []
        while True:
            line = stream.readline()
            if not line:
                raise GeometryNavigationError("PLY header is incomplete")
            try:
                text = line.decode("ascii").strip()
            except UnicodeDecodeError as exc:
                raise GeometryNavigationError("PLY header must be ASCII") from exc
            header.append(text)
            if text == "end_header":
                break
        if header[0] != "ply":
            raise GeometryNavigationError("File is not a PLY document")
        format_line = next((line for line in header if line.startswith("format ")), "")
        vertex_line_index = next((index for index, line in enumerate(header) if line.startswith("element vertex ")), -1)
        if vertex_line_index < 0:
            raise GeometryNavigationError("PLY has no vertex element")
        count = int(header[vertex_line_index].split()[2])
        properties: list[tuple[str, str]] = []
        for line in header[vertex_line_index + 1 :]:
            if line.startswith("element ") or line == "end_header":
                break
            parts = line.split()
            if parts[:1] == ["property"]:
                if len(parts) != 3 or parts[1] == "list":
                    raise GeometryNavigationError("Vertex list properties are not supported")
                properties.append((parts[1], parts[2]))
        names = [name for _, name in properties]
        if not {"x", "y", "z"}.issubset(names):
            raise GeometryNavigationError("PLY vertices must contain x, y, and z")
        if format_line == "format ascii 1.0":
            rows = []
            for _ in range(count):
                values = stream.readline().decode("ascii").split()
                if len(values) < len(properties):
                    raise GeometryNavigationError("PLY vertex data is truncated")
                rows.append([float(values[names.index(axis)]) for axis in ("x", "y", "z")])
            return np.asarray(rows, dtype=np.float64)
        if format_line == "format binary_little_endian 1.0":
            try:
                layout = "<" + "".join(_PLY_TYPES[kind][0] for kind, _ in properties)
            except KeyError as exc:
                raise GeometryNavigationError(f"Unsupported PLY property type: {exc.args[0]}") from exc
            record = struct.Struct(layout)
            rows = []
            indexes = [names.index(axis) for axis in ("x", "y", "z")]
            for _ in range(count):
                payload = stream.read(record.size)
                if len(payload) != record.size:
                    raise GeometryNavigationError("PLY vertex data is truncated")
                values = record.unpack(payload)
                rows.append([float(values[index]) for index in indexes])
            return np.asarray(rows, dtype=np.float64)
        raise GeometryNavigationError(f"Unsupported PLY format: {format_line or 'missing'}")


@dataclass(frozen=True)
class GeometryNavigationResult:
    grid: NavigationGrid
    colliders: dict
    report: dict


def _largest_walkable_component(cells: np.ndarray) -> tuple[np.ndarray, int]:
    height, width = cells.shape
    seen = np.zeros_like(cells, dtype=bool)
    largest: list[tuple[int, int]] = []
    components = 0
    for row in range(height):
        for column in range(width):
            if cells[row, column] or seen[row, column]:
                continue
            components += 1
            queue = deque([(column, row)])
            seen[row, column] = True
            component: list[tuple[int, int]] = []
            while queue:
                x, y = queue.popleft()
                component.append((x, y))
                for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
                    next_x, next_y = x + dx, y + dy
                    if 0 <= next_x < width and 0 <= next_y < height and not cells[next_y, next_x] and not seen[next_y, next_x]:
                        seen[next_y, next_x] = True
                        queue.append((next_x, next_y))
            if len(component) > len(largest):
                largest = component
    output = np.ones_like(cells, dtype=bool)
    for column, row in largest:
        output[row, column] = False
    return output, components


def generate_navigation_from_ply(
    path: str | Path,
    *,
    resolution: float = 0.25,
    floor_tolerance: float = 0.08,
    minimum_obstacle_height: float = 0.15,
    maximum_obstacle_height: float = 2.2,
    obstacle_clearance: float = 0.25,
    minimum_points_per_obstacle_cell: int = 2,
    unit: str = "scene_unit",
    metric_scale_status: str = "arbitrary",
) -> GeometryNavigationResult:
    if not 0.05 <= resolution <= 2:
        raise GeometryNavigationError("Resolution must be between 0.05 and 2 scene units")
    points = load_ply_vertices(path)
    if len(points) < 20 or not np.isfinite(points).all():
        raise GeometryNavigationError("At least 20 finite PLY vertices are required")

    y_values = points[:, 1]
    low_limit = float(np.percentile(y_values, 40))
    low_values = y_values[y_values <= low_limit]
    bin_width = max(floor_tolerance, 0.02)
    bins = np.arange(float(low_values.min()) - bin_width, float(low_values.max()) + 2 * bin_width, bin_width)
    histogram, edges = np.histogram(low_values, bins=bins)
    best = int(np.argmax(histogram))
    floor_y = float((edges[best] + edges[best + 1]) / 2)
    floor_mask = np.abs(y_values - floor_y) <= floor_tolerance
    floor_points = points[floor_mask]
    if len(floor_points) < 10:
        raise GeometryNavigationError("No sufficiently supported horizontal floor band was detected")

    x_min, z_min = np.percentile(floor_points[:, [0, 2]], 1, axis=0)
    x_max, z_max = np.percentile(floor_points[:, [0, 2]], 99, axis=0)
    width = max(1, int(math.ceil((x_max - x_min) / resolution)))
    height = max(1, int(math.ceil((z_max - z_min) / resolution)))
    if width * height > 4_000_000:
        raise GeometryNavigationError("Requested grid exceeds four million cells; increase resolution")

    obstacle = points[(y_values >= floor_y + minimum_obstacle_height) & (y_values <= floor_y + maximum_obstacle_height)]
    counts = np.zeros((height, width), dtype=np.uint32)
    columns = np.floor((obstacle[:, 0] - x_min) / resolution).astype(int) if len(obstacle) else np.array([], dtype=int)
    rows = np.floor((obstacle[:, 2] - z_min) / resolution).astype(int) if len(obstacle) else np.array([], dtype=int)
    valid = (columns >= 0) & (columns < width) & (rows >= 0) & (rows < height)
    np.add.at(counts, (rows[valid], columns[valid]), 1)
    blocked = counts >= minimum_points_per_obstacle_cell
    radius = int(math.ceil(obstacle_clearance / resolution))
    if radius:
        original = blocked.copy()
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if math.hypot(dx, dy) * resolution > obstacle_clearance + resolution / 2:
                    continue
                target_rows = slice(max(0, dy), min(height, height + dy))
                target_columns = slice(max(0, dx), min(width, width + dx))
                source_rows = slice(max(0, -dy), min(height, height - dy))
                source_columns = slice(max(0, -dx), min(width, width - dx))
                blocked[target_rows, target_columns] |= original[source_rows, source_columns]
    blocked, component_count = _largest_walkable_component(blocked)

    rows_document = tuple("".join("#" if value else "." for value in row) for row in blocked)
    grid = NavigationGrid(
        version="geometry-draft-1",
        coordinate_system="SpatialForge right-handed Y-up",
        floor_id="ground",
        floor_y=round(floor_y, 6),
        origin=(float(x_min), round(floor_y, 6), float(z_min)),
        resolution=resolution,
        width=width,
        height=height,
        connectivity=8,
        cells=rows_document,
        unit=unit,
        metric_scale_status=metric_scale_status,
    )

    colliders = []
    collider_index = 0
    for row_index, row in enumerate(blocked):
        start = None
        for column_index in range(width + 1):
            value = bool(row[column_index]) if column_index < width else False
            if value and start is None:
                start = column_index
            if not value and start is not None:
                collider_index += 1
                colliders.append({
                    "id": f"generated_obstacle_{collider_index:05d}",
                    "minimum": [float(x_min + start * resolution), floor_y, float(z_min + row_index * resolution)],
                    "maximum": [float(x_min + column_index * resolution), floor_y + maximum_obstacle_height, float(z_min + (row_index + 1) * resolution)],
                })
                start = None
    collider_document = {
        "schema_version": "1.0.0",
        "coordinate_system": "SpatialForge right-handed Y-up",
        "walkable_bounds": {"minimum": [float(x_min), floor_y, float(z_min)], "maximum": [float(x_max), floor_y + maximum_obstacle_height, float(z_max)]},
        "colliders": colliders,
    }
    floor_support = len(floor_points) / len(points)
    report = {
        "schema_version": "1.0.0",
        "status": "needs_manual_review",
        "source": str(Path(path).name),
        "point_count": len(points),
        "floor_elevation": round(floor_y, 6),
        "floor_support_ratio": round(floor_support, 4),
        "floor_confidence": "high" if floor_support >= 0.35 else "medium" if floor_support >= 0.15 else "low",
        "obstacle_point_count": len(obstacle),
        "blocked_cell_count": int(np.count_nonzero(blocked)),
        "walkable_cell_count": int(width * height - np.count_nonzero(blocked)),
        "initial_walkable_components": component_count,
        "assumptions": ["Input geometry is already aligned to SpatialForge Y-up coordinates.", "The dominant low horizontal band represents the floor."],
        "warnings": ["Generated navigation is a draft and is not attached to the scene manifest until manually reviewed."],
    }
    return GeometryNavigationResult(grid, collider_document, report)


def write_navigation_draft(result: GeometryNavigationResult, output_directory: str | Path) -> Path:
    output = Path(output_directory).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    documents = {
        "grid.draft.json": result.grid.model_dump(mode="json"),
        "colliders.draft.json": result.colliders,
        "geometry_analysis.json": result.report,
    }
    for name, document in documents.items():
        path = output / name
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(document, indent=2), encoding="utf-8")
        temporary.replace(path)
    return output
