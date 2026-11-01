import { describe, expect, it } from "vitest";
import { movementVector } from "./movement";

describe("movementVector", () => {
  it("moves forward along negative Z at zero yaw", () => {
    const vector = movementVector({ forward: true, backward: false, left: false, right: false }, 0);
    expect(vector.x).toBeCloseTo(0);
    expect(vector.z).toBe(-1);
  });

  it("normalizes diagonal movement", () => {
    const vector = movementVector({ forward: true, backward: false, left: false, right: true }, 0);
    expect(Math.hypot(vector.x, vector.z)).toBeCloseTo(1);
    expect(vector.x).toBeGreaterThan(0);
    expect(vector.z).toBeLessThan(0);
  });
});
