from pathlib import Path

from spatialforge.navigation.geometry import generate_navigation_from_ply, load_ply_vertices, write_navigation_draft


def _write_test_ply(path: Path) -> None:
    points = []
    for x in range(11):
        for z in range(11):
            points.append((x * 0.2, 0.0, z * 0.2))
    for y in range(1, 9):
        for z in range(3, 8):
            points.extend([(1.0, y * 0.2, z * 0.2), (1.02, y * 0.2, z * 0.2)])
    header = ["ply", "format ascii 1.0", f"element vertex {len(points)}", "property float x", "property float y", "property float z", "end_header"]
    path.write_text("\n".join(header + [f"{x} {y} {z}" for x, y, z in points]) + "\n", encoding="ascii")


def test_geometry_bridge_detects_floor_and_obstacle(tmp_path: Path) -> None:
    source = tmp_path / "room.ply"
    _write_test_ply(source)
    vertices = load_ply_vertices(source)
    assert len(vertices) > 100
    result = generate_navigation_from_ply(source, resolution=0.2, obstacle_clearance=0)
    assert abs(result.grid.floor_y) < 0.1
    assert result.report["status"] == "needs_manual_review"
    assert result.report["blocked_cell_count"] > 0
    output = write_navigation_draft(result, tmp_path / "navigation")
    assert (output / "grid.draft.json").is_file()
    assert (output / "colliders.draft.json").is_file()
