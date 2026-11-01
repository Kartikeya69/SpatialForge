import { describe, expect, it } from "vitest";
import { transformPointRowMajor } from "./coordinates";

describe("scene coordinate transforms", () => {
  it("applies row-major rotation, scale, and translation", () => {
    const matrix = [0, 0, 2, 3, 0, 2, 0, 1, -2, 0, 0, -4, 0, 0, 0, 1];
    expect(transformPointRowMajor([0.25, 0.5, 0.75], matrix)).toEqual([4.5, 2, -4.5]);
  });

  it("rejects malformed transforms", () => {
    expect(() => transformPointRowMajor([0, 0, 0], [1])).toThrow(/16/);
  });
});
