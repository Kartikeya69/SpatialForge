import type { Vector3Tuple } from "../types";

export function transformPointRowMajor(point: Vector3Tuple, matrix: number[]): Vector3Tuple {
  if (matrix.length !== 16) throw new Error("Scene coordinate transform must contain 16 values");
  const [x, y, z] = point;
  const w = matrix[12] * x + matrix[13] * y + matrix[14] * z + matrix[15];
  if (Math.abs(w) < 1e-12) throw new Error("Coordinate transform produced a point at infinity");
  return [
    (matrix[0] * x + matrix[1] * y + matrix[2] * z + matrix[3]) / w,
    (matrix[4] * x + matrix[5] * y + matrix[6] * z + matrix[7]) / w,
    (matrix[8] * x + matrix[9] * y + matrix[10] * z + matrix[11]) / w,
  ];
}
