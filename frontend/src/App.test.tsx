import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { SceneManifest } from "./types";
import App from "./App";

vi.mock("./viewer/SceneViewport", () => ({
  default: ({ manifest }: { manifest: SceneManifest }) => (
    <div data-testid="scene-viewport">Viewport: {manifest.scene_name}</div>
  ),
}));

function manifest(sceneId: string, sceneName: string): SceneManifest {
  return {
    schema_version: "1.0.0",
    scene_id: sceneId,
    scene_name: sceneName,
    description: `${sceneName} description`,
    synthetic_demo: true,
    processing_status: "demonstration",
    coordinate_system: { handedness: "right", up_axis: "Y", forward_axis: "-Z", source_convention: "test", source_to_scene_matrix_row_major: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] },
    units: { name: "meter", metric_scale_status: "known", meters_per_unit: 1 },
    origin: [0, 0, 0],
    bounding_box: { minimum: [-5, 0, -5], maximum: [5, 3, 5] },
    reconstruction: { backend: "synthetic", backend_version: "1", source: "synthetic", status: "demonstration", metric_scale_calibrated: true },
    assets: [{ id: "colliders", type: "collider_geometry", path: "navigation/colliders.json", role: "navigation", mime_type: "application/json", required: true, visible_by_default: false }],
    camera_metadata: { pose_asset_id: null, pose_convention: "both" },
    navigation: { enabled: true, spawn_position: [0, 1.65, 0], spawn_yaw_degrees: 0, camera_height: 1.65, movement_speed: 2.5, collision_radius: 0.25, collider_asset_id: "colliders", grid_asset_id: null, zones: ["one"] },
    poi_metadata: { asset_id: null, count: 0 },
    viewer: { background: "#000", ambient_light_intensity: 1, directional_light_intensity: 1, point_size: 0.05 },
  };
}

const summaries = [
  { scene_id: "scene_one", scene_name: "Scene One", description: "", processing_status: "demonstration", synthetic_demo: true, asset_types: ["gltf"], manifest_url: "/one" },
  { scene_id: "scene_two", scene_name: "Scene Two", description: "", processing_status: "demonstration", synthetic_demo: true, asset_types: ["gltf"], manifest_url: "/two" },
];

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({} as never);
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/scenes") return new Response(JSON.stringify({ scenes: summaries }), { status: 200 });
    if (url.includes("scene_one/manifest")) return new Response(JSON.stringify(manifest("scene_one", "Scene One")), { status: 200 });
    if (url.includes("scene_two/manifest")) return new Response(JSON.stringify(manifest("scene_two", "Scene Two")), { status: 200 });
    if (url.includes("colliders.json")) return new Response(JSON.stringify({ schema_version: "1.0.0", coordinate_system: "test", walkable_bounds: { minimum: [-5, 0, -5], maximum: [5, 3, 5] }, colliders: [] }), { status: 200 });
    return new Response(JSON.stringify({ detail: "not found" }), { status: 404 });
  }));
});

describe("App", () => {
  it("shows a loading state while scene discovery is pending", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));
    render(<App />);
    expect(screen.getByText("Discovering scene packages")).toBeInTheDocument();
  });

  it("shows a stable real-data empty state without inventing a scene", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ scenes: [] }), { status: 200 })));
    render(<App />);
    expect(await screen.findByText("No digital twins yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import footage" })).toBeInTheDocument();
    expect(screen.queryByTestId("scene-viewport")).not.toBeInTheDocument();
    expect(screen.queryByText(/Synthetic Twin Lab/)).not.toBeInTheDocument();
  });

  it("loads and switches independent scene packages", async () => {
    render(<App />);
    expect(await screen.findByText("Viewport: Scene One")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /active scene/i }));
    fireEvent.click(screen.getByRole("button", { name: /Scene Two/ }));
    expect(await screen.findByText("Viewport: Scene Two")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Scene information" }));
    await waitFor(() => expect(screen.getByText("Scene Two description")).toBeInTheDocument());
  });

  it("switches camera and quality modes through accessible controls", async () => {
    render(<App />);
    await screen.findByText("Viewport: Scene One");
    fireEvent.click(screen.getByRole("button", { name: "Orbit" }));
    expect(screen.getByRole("button", { name: "Orbit" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Viewer settings" }));
    fireEvent.change(screen.getByLabelText("Rendering quality"), { target: { value: "high" } });
    expect(screen.getByLabelText("Rendering quality")).toHaveValue("high");
  });

  it("opens and closes keyboard help without a mouse", async () => {
    render(<App />);
    await screen.findByText("Viewport: Scene One");
    fireEvent.keyDown(window, { key: "?" });
    expect(screen.getByRole("dialog", { name: "Explore SpatialForge" })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Explore SpatialForge" })).not.toBeInTheDocument());
  });

  it("ignores a stale scene response after a newer selection", async () => {
    let resolveSecond!: (response: Response) => void;
    const delayedSecond = new Promise<Response>((resolve) => { resolveSecond = resolve; });
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/v1/scenes") return new Response(JSON.stringify({ scenes: summaries }), { status: 200 });
      if (url.includes("scene_two/manifest")) return delayedSecond;
      if (url.includes("scene_one/manifest")) return new Response(JSON.stringify(manifest("scene_one", "Scene One")), { status: 200 });
      if (url.includes("colliders.json")) return new Response(JSON.stringify({ schema_version: "1.0.0", coordinate_system: "test", walkable_bounds: { minimum: [-5, 0, -5], maximum: [5, 3, 5] }, colliders: [] }), { status: 200 });
      return new Response(null, { status: 404 });
    }));

    render(<App />);
    await screen.findByText("Viewport: Scene One");
    fireEvent.click(screen.getByRole("button", { name: /active scene/i }));
    fireEvent.click(screen.getByRole("button", { name: /Scene Two/ }));
    fireEvent.click(screen.getByRole("button", { name: /active scene/i }));
    fireEvent.click(screen.getByRole("button", { name: /Scene One/ }));
    expect(await screen.findByText("Viewport: Scene One")).toBeInTheDocument();
    resolveSecond(new Response(JSON.stringify(manifest("scene_two", "Scene Two")), { status: 200 }));
    await Promise.resolve();
    expect(screen.queryByText("Viewport: Scene Two")).not.toBeInTheDocument();
  });
});
