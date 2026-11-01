import { describe, expect, it } from "vitest";
import type { ColliderDocument } from "../types";
import { isWalkableTarget, mapToWorld, worldToMap } from "./minimap";

const document: ColliderDocument = {
  schema_version: "1.0.0",
  coordinate_system: "test",
  walkable_bounds: { minimum: [-5, 0, -4], maximum: [5, 3, 4] },
  colliders: [{ id: "box", minimum: [-1, 0, -1], maximum: [1, 2, 1] }],
};

describe("minimap coordinates", () => {
  it("round-trips world and map coordinates", () => {
    const map = worldToMap({ x: 2, z: -3 }, document.walkable_bounds, 200, 100);
    expect(mapToWorld(map, document.walkable_bounds, 200, 100)).toEqual({ x: 2, z: -3 });
  });

  it("rejects obstacle and out-of-bounds targets", () => {
    expect(isWalkableTarget({ x: 0, z: 0 }, document, 0.2)).toBe(false);
    expect(isWalkableTarget({ x: 4, z: 3 }, document, 0.2)).toBe(true);
    expect(isWalkableTarget({ x: 5, z: 0 }, document, 0.2)).toBe(false);
  });
});
