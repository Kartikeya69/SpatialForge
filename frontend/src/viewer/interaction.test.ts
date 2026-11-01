import { describe, expect, it } from "vitest";
import { transitionControlMode } from "./interaction";

describe("control mode lifecycle", () => {
  it("supports click, escape, drag, and pointer lock transitions", () => {
    expect(transitionControlMode("idle", "click")).toBe("free");
    expect(transitionControlMode("free", "escape")).toBe("idle");
    expect(transitionControlMode("idle", "drag-start")).toBe("dragging");
    expect(transitionControlMode("dragging", "drag-end")).toBe("idle");
    expect(transitionControlMode("idle", "pointer-lock")).toBe("locked");
    expect(transitionControlMode("locked", "pointer-unlock")).toBe("idle");
  });
});
