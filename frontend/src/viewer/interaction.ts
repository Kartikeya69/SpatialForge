import type { ControlMode } from "./FirstPersonController";

export type InteractionEvent = "click" | "drag-start" | "drag-end" | "pointer-lock" | "pointer-unlock" | "escape";

export function transitionControlMode(mode: ControlMode, event: InteractionEvent): ControlMode {
  if (event === "pointer-lock") return "locked";
  if (event === "pointer-unlock" || event === "escape") return "idle";
  if (event === "drag-start") return "dragging";
  if (event === "drag-end") return "idle";
  if (event === "click") return mode === "free" ? "idle" : "free";
  return mode;
}
