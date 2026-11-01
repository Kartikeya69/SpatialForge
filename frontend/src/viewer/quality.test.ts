import { describe, expect, it } from "vitest";
import { qualitySettings } from "./quality";

describe("qualitySettings", () => {
  it("keeps integrated-GPU defaults bounded", () => {
    expect(qualitySettings("balanced").dpr[1]).toBe(1.5);
    expect(qualitySettings("low").antialias).toBe(false);
    expect(qualitySettings("high").shadows).toBe(true);
  });
});
