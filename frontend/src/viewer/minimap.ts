import type { ColliderDocument } from "../types";
import type { HorizontalPosition, WalkableBounds } from "./collision";

export interface MapPoint { x: number; y: number }

export function worldToMap(position: HorizontalPosition, bounds: WalkableBounds, width: number, height: number): MapPoint {
  const spanX = Math.max(0.0001, bounds.maximum[0] - bounds.minimum[0]);
  const spanZ = Math.max(0.0001, bounds.maximum[2] - bounds.minimum[2]);
  return {
    x: ((position.x - bounds.minimum[0]) / spanX) * width,
    y: height - ((position.z - bounds.minimum[2]) / spanZ) * height,
  };
}

export function mapToWorld(point: MapPoint, bounds: WalkableBounds, width: number, height: number): HorizontalPosition {
  const spanX = bounds.maximum[0] - bounds.minimum[0];
  const spanZ = bounds.maximum[2] - bounds.minimum[2];
  return {
    x: bounds.minimum[0] + (point.x / width) * spanX,
    z: bounds.minimum[2] + ((height - point.y) / height) * spanZ,
  };
}

export function isWalkableTarget(position: HorizontalPosition, document: ColliderDocument, radius: number): boolean {
  const { minimum, maximum } = document.walkable_bounds;
  if (position.x < minimum[0] + radius || position.x > maximum[0] - radius) return false;
  if (position.z < minimum[2] + radius || position.z > maximum[2] - radius) return false;
  return !document.colliders.some((collider) => {
    const nearestX = Math.max(collider.minimum[0], Math.min(position.x, collider.maximum[0]));
    const nearestZ = Math.max(collider.minimum[2], Math.min(position.z, collider.maximum[2]));
    return (position.x - nearestX) ** 2 + (position.z - nearestZ) ** 2 < radius ** 2;
  });
}
