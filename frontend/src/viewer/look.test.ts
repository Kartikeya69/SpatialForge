import { MathUtils } from "three";
import { describe, expect, it } from "vitest";
import { applyLookDelta } from "./look";

describe("applyLookDelta", () => {
  it("turns camera angles from mouse or pointer movement", () => {
    expect(applyLookDelta({ yaw: 1, pitch: 0.5 }, 100, -50, 0.01)).toEqual({
      yaw: 0,
      pitch: 1,
    });
  });

  it("clamps vertical look to avoid flipping", () => {
    const result = applyLookDelta({ yaw: 0, pitch: 0 }, 0, -10_000);
    expect(result.pitch).toBeCloseTo(MathUtils.degToRad(86));
  });
});
