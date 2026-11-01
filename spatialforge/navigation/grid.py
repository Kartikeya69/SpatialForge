"""Deterministic A* routing and SpatialForge world/grid conversions."""

from __future__ import annotations

import heapq
import math
from collections import deque

from .models import NavigationGrid, Vector3

GridCell = tuple[int, int]  # column (X), row (Z)


class NavigationGridError(ValueError):
    pass


def world_to_grid(position: Vector3, grid: NavigationGrid) -> GridCell:
    column = math.floor((position[0] - grid.origin[0]) / grid.resolution)
    row = math.floor((position[2] - grid.origin[2]) / grid.resolution)
    return column, row


def grid_to_world(cell: GridCell, grid: NavigationGrid) -> Vector3:
    column, row = cell
    return (
        grid.origin[0] + (column + 0.5) * grid.resolution,
        grid.floor_y,
        grid.origin[2] + (row + 0.5) * grid.resolution,
    )


def in_bounds(cell: GridCell, grid: NavigationGrid) -> bool:
    return 0 <= cell[0] < grid.width and 0 <= cell[1] < grid.height


def is_walkable(cell: GridCell, grid: NavigationGrid, clearance: float = 0.0) -> bool:
    if not in_bounds(cell, grid) or grid.cells[cell[1]][cell[0]] != ".":
        return False
    radius = math.ceil(clearance / grid.resolution + 0.5)
    if radius == 0:
        return True
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            distance_to_cell = math.hypot(max(abs(dx) - 0.5, 0), max(abs(dy) - 0.5, 0)) * grid.resolution
            if distance_to_cell > clearance + 1e-9:
                continue
            nearby = (cell[0] + dx, cell[1] + dy)
            if not in_bounds(nearby, grid) or grid.cells[nearby[1]][nearby[0]] == "#":
                return False
    return True


def _neighbors(cell: GridCell, grid: NavigationGrid, connectivity: int, clearance: float):
    directions = [(0, -1), (-1, 0), (1, 0), (0, 1)]
    if connectivity == 8:
        directions += [(-1, -1), (1, -1), (-1, 1), (1, 1)]
    for dx, dy in directions:
        candidate = (cell[0] + dx, cell[1] + dy)
        if not is_walkable(candidate, grid, clearance):
            continue
        if dx and dy:
            if not is_walkable((cell[0] + dx, cell[1]), grid, clearance) or not is_walkable(
                (cell[0], cell[1] + dy), grid, clearance
            ):
                continue
            cost = math.sqrt(2)
        else:
            cost = 1.0
        yield candidate, cost


def _heuristic(a: GridCell, b: GridCell, connectivity: int) -> float:
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy) if connectivity == 8 else dx + dy


def connected(start: GridCell, goal: GridCell, grid: NavigationGrid, connectivity: int, clearance: float) -> bool:
    queue = deque([start])
    seen = {start}
    while queue:
        current = queue.popleft()
        if current == goal:
            return True
        for neighbor, _ in _neighbors(current, grid, connectivity, clearance):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return False


def find_path(start: GridCell, goal: GridCell, grid: NavigationGrid, connectivity: int, clearance: float) -> list[GridCell]:
    if not is_walkable(start, grid, clearance):
        raise NavigationGridError("Start position is outside the walkable navigation area")
    if not is_walkable(goal, grid, clearance):
        raise NavigationGridError("Destination is outside the walkable navigation area")
    if not connected(start, goal, grid, connectivity, clearance):
        raise NavigationGridError("No path connects the start and destination")

    frontier: list[tuple[float, float, GridCell]] = [(0, 0, start)]
    came_from: dict[GridCell, GridCell | None] = {start: None}
    cost_so_far = {start: 0.0}
    while frontier:
        _, cost, current = heapq.heappop(frontier)
        if current == goal:
            break
        if cost > cost_so_far[current] + 1e-9:
            continue
        for neighbor, move_cost in _neighbors(current, grid, connectivity, clearance):
            candidate_cost = cost + move_cost
            if candidate_cost + 1e-9 < cost_so_far.get(neighbor, math.inf):
                cost_so_far[neighbor] = candidate_cost
                came_from[neighbor] = current
                priority = candidate_cost + _heuristic(neighbor, goal, connectivity)
                heapq.heappush(frontier, (priority, candidate_cost, neighbor))

    path = [goal]
    while path[-1] != start:
        path.append(came_from[path[-1]])  # type: ignore[arg-type]
    path.reverse()
    return path


def nearest_walkable(cell: GridCell, grid: NavigationGrid, clearance: float, max_distance: float) -> GridCell | None:
    if is_walkable(cell, grid, clearance):
        return cell
    radius = math.ceil(max_distance / grid.resolution)
    candidates: list[tuple[float, int, int, GridCell]] = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            distance = math.hypot(dx, dy) * grid.resolution
            if distance <= max_distance + 1e-9:
                candidate = (cell[0] + dx, cell[1] + dy)
                if is_walkable(candidate, grid, clearance):
                    candidates.append((distance, candidate[1], candidate[0], candidate))
    return min(candidates)[-1] if candidates else None


def _line_is_clear(start: GridCell, goal: GridCell, grid: NavigationGrid, clearance: float) -> bool:
    dx, dy = goal[0] - start[0], goal[1] - start[1]
    steps = max(abs(dx), abs(dy)) * 2 + 1
    visited: list[GridCell] = []
    for index in range(steps + 1):
        amount = index / max(1, steps)
        cell = (round(start[0] + dx * amount), round(start[1] + dy * amount))
        if visited and cell == visited[-1]:
            continue
        if not is_walkable(cell, grid, clearance):
            return False
        if visited:
            previous = visited[-1]
            move_x, move_y = cell[0] - previous[0], cell[1] - previous[1]
            if move_x and move_y and (
                not is_walkable((previous[0] + move_x, previous[1]), grid, clearance)
                or not is_walkable((previous[0], previous[1] + move_y), grid, clearance)
            ):
                return False
        visited.append(cell)
    return True


def simplify_path(path: list[GridCell], grid: NavigationGrid, clearance: float) -> list[GridCell]:
    if len(path) <= 2:
        return path
    simplified = [path[0]]
    anchor = 0
    while anchor < len(path) - 1:
        candidate = len(path) - 1
        while candidate > anchor + 1 and not _line_is_clear(path[anchor], path[candidate], grid, clearance):
            candidate -= 1
        simplified.append(path[candidate])
        anchor = candidate
    return simplified


def path_length(points: list[Vector3]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))
