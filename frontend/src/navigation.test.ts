import { describe, expect, it } from "vitest";
import { distanceToRoute, hasArrived, routeProgress, shouldRecomputeRoute } from "./navigation";
import type { RouteResult } from "./types";

const route: RouteResult = {
  status: "completed",
  waypoints: [[0, 0, 0], [0, 0, 5], [5, 0, 5]],
  route_length: 10,
  distance_units: "meter",
  navigation_grid_version: "test",
  destination: { poi_id: "poi_target", name: "Target", position: [5, 0, 5] },
};

describe("navigation state", () => {
  it("measures deviation from the actual polyline", () => {
    expect(distanceToRoute([0.2, 1.65, 2], route.waypoints)).toBeCloseTo(0.2);
    expect(distanceToRoute([3, 1.65, 3], route.waypoints)).toBeCloseTo(2);
  });

  it("tracks bounded progress and arrival", () => {
    expect(routeProgress([0, 1.65, 0], route)).toBe(0);
    expect(routeProgress([0, 1.65, 5], route)).toBeCloseTo(0.5);
    expect(routeProgress([5, 1.65, 5], route)).toBe(1);
    expect(hasArrived([5.3, 1.65, 5.2], route)).toBe(true);
    expect(hasArrived([4, 1.65, 5], route)).toBe(false);
  });

  it("throttles recomputation and requires meaningful deviation", () => {
    expect(shouldRecomputeRoute([3, 0, 3], route, 0, 2500)).toBe(true);
    expect(shouldRecomputeRoute([3, 0, 3], route, 1000, 2500)).toBe(false);
    expect(shouldRecomputeRoute([0.1, 0, 3], route, 0, 2500)).toBe(false);
  });
});
