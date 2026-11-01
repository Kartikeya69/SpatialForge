import { describe, expect, it } from "vitest";
import { movementDistance, smoothingAlpha } from "./motion";

describe("frame-rate-independent motion", () => {
  it("covers the same distance over equal elapsed time", () => {
    const at60 = Array.from({ length: 60 }, () => movementDistance(3, 1 / 60)).reduce((a, b) => a + b, 0);
    const at30 = Array.from({ length: 30 }, () => movementDistance(3, 1 / 30)).reduce((a, b) => a + b, 0);
    expect(at60).toBeCloseTo(at30, 8);
  });

  it("uses exponential smoothing independent of frame count", () => {
    const oneStep = 1 - smoothingAlpha(1, 8);
    const twoSteps = (1 - smoothingAlpha(0.5, 8)) ** 2;
    expect(oneStep).toBeCloseTo(twoSteps, 8);
  });
});
