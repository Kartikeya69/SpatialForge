import { act, render, screen } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { SceneManifest } from "../types";
import { SceneViewport } from "./SceneViewport";

const lifecycle = vi.hoisted(() => ({ mounts: 0, unmounts: 0, canvas: document.createElement("canvas") }));

vi.mock("@react-three/fiber", () => ({
  Canvas: ({ children }: { children: ReactNode }) => {
    useEffect(() => {
      lifecycle.mounts += 1;
      return () => { lifecycle.unmounts += 1; };
    }, []);
    return <div data-testid="r3f-canvas">{children}</div>;
  },
  useThree: () => ({ gl: { domElement: lifecycle.canvas } }),
}));
vi.mock("./CameraModeRig", () => ({ CameraModeRig: () => null }));
vi.mock("./PerformanceProbe", () => ({ PerformanceProbe: () => null }));
vi.mock("./SceneAssets", () => ({ SceneAssets: () => null }));
vi.mock("./RouteOverlay", () => ({ RouteOverlay: () => null }));

const manifest = {
  scene_id: "scene_real",
  scene_name: "Imported room",
  navigation: { spawn_position: [0, 1.65, 0] },
  viewer: { background: "#000", ambient_light_intensity: 1, directional_light_intensity: 1 },
} as unknown as SceneManifest;

const props = {
  manifest,
  colliderDocument: null,
  movementSpeed: 2.5,
  mouseSensitivity: 0.0022,
  smoothing: true,
  cameraMode: "first-person" as const,
  resetToken: 0,
  teleport: null,
  showDiagnostics: false,
  collectMetrics: false,
  onControlModeChange: vi.fn(),
  onTelemetry: vi.fn(),
  onMetrics: vi.fn(),
  route: null,
  selectedAssetId: null,
};

describe("SceneViewport lifecycle", () => {
  it("does not recreate the WebGL canvas when quality changes", () => {
    lifecycle.mounts = 0;
    lifecycle.unmounts = 0;
    const view = render(<SceneViewport {...props} quality="balanced" />);
    view.rerender(<SceneViewport {...props} quality="high" />);
    expect(lifecycle.mounts).toBe(1);
    expect(lifecycle.unmounts).toBe(0);
  });

  it("reports WebGL context loss and clears the warning after restoration", async () => {
    render(<SceneViewport {...props} quality="balanced" />);
    await act(async () => lifecycle.canvas.dispatchEvent(new Event("webglcontextlost", { cancelable: true })));
    expect(screen.getByText("Graphics context interrupted")).toBeInTheDocument();
    await act(async () => lifecycle.canvas.dispatchEvent(new Event("webglcontextrestored")));
    expect(screen.queryByText("Graphics context interrupted")).not.toBeInTheDocument();
  });
});
