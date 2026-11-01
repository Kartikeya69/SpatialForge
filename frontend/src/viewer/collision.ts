import type { Collider, Vector3Tuple } from "../types";

export interface HorizontalPosition {
  x: number;
  z: number;
}

export interface WalkableBounds {
  minimum: Vector3Tuple;
  maximum: Vector3Tuple;
}

function intersects(position: HorizontalPosition, radius: number, collider: Collider): boolean {
  const nearestX = Math.max(collider.minimum[0], Math.min(position.x, collider.maximum[0]));
  const nearestZ = Math.max(collider.minimum[2], Math.min(position.z, collider.maximum[2]));
  const dx = position.x - nearestX;
  const dz = position.z - nearestZ;
  return dx * dx + dz * dz < radius * radius;
}

function clampToBounds(position: HorizontalPosition, radius: number, bounds: WalkableBounds): HorizontalPosition {
  return {
    x: Math.max(bounds.minimum[0] + radius, Math.min(position.x, bounds.maximum[0] - radius)),
    z: Math.max(bounds.minimum[2] + radius, Math.min(position.z, bounds.maximum[2] - radius)),
  };
}

export function resolveMovement(
  current: HorizontalPosition,
  desired: HorizontalPosition,
  radius: number,
  colliders: Collider[],
  bounds: WalkableBounds,
): HorizontalPosition {
  const bounded = clampToBounds(desired, radius, bounds);
  let result = current;
  const xCandidate = { x: bounded.x, z: current.z };
  if (!colliders.some((collider) => intersects(xCandidate, radius, collider))) result = xCandidate;
  const zCandidate = { x: result.x, z: bounded.z };
  if (!colliders.some((collider) => intersects(zCandidate, radius, collider))) result = zCandidate;
  return clampToBounds(result, radius, bounds);
}
