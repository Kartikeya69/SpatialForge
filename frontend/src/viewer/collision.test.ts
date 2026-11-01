import { describe, expect, it } from "vitest";
import { resolveMovement } from "./collision";

const bounds = { minimum: [-5, 0, -5] as [number, number, number], maximum: [5, 3, 5] as [number, number, number] };
const wall = { id: "wall", minimum: [-0.1, 0, -2] as [number, number, number], maximum: [0.1, 3, 2] as [number, number, number] };

describe("resolveMovement", () => {
  it("prevents walking through collider geometry", () => {
    const result = resolveMovement({ x: -0.5, z: 0 }, { x: 0, z: 0 }, 0.25, [wall], bounds);
    expect(result).toEqual({ x: -0.5, z: 0 });
  });

  it("slides along walls and clamps to walkable bounds", () => {
    const slid = resolveMovement({ x: -0.5, z: 0 }, { x: 0, z: 1 }, 0.25, [wall], bounds);
    expect(slid).toEqual({ x: -0.5, z: 1 });
    const clamped = resolveMovement({ x: 4, z: 4 }, { x: 20, z: 20 }, 0.25, [], bounds);
    expect(clamped).toEqual({ x: 4.75, z: 4.75 });
  });
});
