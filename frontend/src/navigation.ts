import type { RouteResult, Vector3Tuple } from "./types";

function planarDistance(a: Vector3Tuple, b: Vector3Tuple): number {
  return Math.hypot(a[0] - b[0], a[2] - b[2]);
}

export function distanceToRoute(position: Vector3Tuple, waypoints: Vector3Tuple[]): number {
  if (!waypoints.length) return Number.POSITIVE_INFINITY;
  if (waypoints.length === 1) return planarDistance(position, waypoints[0]);
  let closest = Number.POSITIVE_INFINITY;
  for (let index = 0; index < waypoints.length - 1; index += 1) {
    const a = waypoints[index];
    const b = waypoints[index + 1];
    const dx = b[0] - a[0];
    const dz = b[2] - a[2];
    const lengthSquared = dx * dx + dz * dz;
    const projection = lengthSquared ? Math.max(0, Math.min(1, ((position[0] - a[0]) * dx + (position[2] - a[2]) * dz) / lengthSquared)) : 0;
    closest = Math.min(closest, Math.hypot(position[0] - (a[0] + projection * dx), position[2] - (a[2] + projection * dz)));
  }
  return closest;
}

export function routeProgress(position: Vector3Tuple, route: RouteResult): number {
  if (route.waypoints.length < 2) return hasArrived(position, route) ? 1 : 0;
  let total = 0;
  let traversed = 0;
  let closestDistance = Number.POSITIVE_INFINITY;
  let closestAlong = 0;
  for (let index = 0; index < route.waypoints.length - 1; index += 1) {
    const a = route.waypoints[index];
    const b = route.waypoints[index + 1];
    const dx = b[0] - a[0];
    const dz = b[2] - a[2];
    const segmentLength = Math.hypot(dx, dz);
    const projection = segmentLength ? Math.max(0, Math.min(1, ((position[0] - a[0]) * dx + (position[2] - a[2]) * dz) / (segmentLength * segmentLength))) : 0;
    const distance = Math.hypot(position[0] - (a[0] + projection * dx), position[2] - (a[2] + projection * dz));
    if (distance < closestDistance) { closestDistance = distance; closestAlong = traversed + projection * segmentLength; }
    traversed += segmentLength;
    total += segmentLength;
  }
  return total ? Math.max(0, Math.min(1, closestAlong / total)) : 0;
}

export function hasArrived(position: Vector3Tuple, route: RouteResult, radius = 0.55): boolean {
  return planarDistance(position, route.destination.position) <= radius;
}

export function shouldRecomputeRoute(position: Vector3Tuple, route: RouteResult, lastComputedAt: number, now: number, deviation = 0.8, throttleMs = 2000): boolean {
  return now - lastComputedAt >= throttleMs && distanceToRoute(position, route.waypoints) > deviation;
}
