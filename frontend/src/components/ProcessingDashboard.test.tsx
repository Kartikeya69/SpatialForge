import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProcessingDashboard } from "./ProcessingDashboard";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ jobs: [{
    scene_id: "scene_room", status: "sparse_ready", current_stage: "sparse_reconstruction",
    stages: [{ name: "capture", status: "completed", details: { accepted_frames: 80 } }, { name: "sparse_reconstruction", status: "completed", details: { registered_images: 72 } }],
    error: null, has_original_input: true, has_viewer_manifest: false,
  }] }), { status: 200 })));
});

describe("ProcessingDashboard", () => {
  it("shows real stage names without percentage progress", async () => {
    render(<ProcessingDashboard onClose={vi.fn()} />);
    expect(await screen.findByText("scene_room")).toBeInTheDocument();
    expect(screen.getByText("sparse ready")).toBeInTheDocument();
    expect(screen.getByText("capture")).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("offers photo-set, video, and explicitly limited single-photo modes", async () => {
    render(<ProcessingDashboard onClose={vi.fn()} />);
    await screen.findByText("scene_room");
    expect(screen.getByRole("tab", { name: /Photo set/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /Video/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Single photo/ }));
    expect(screen.getByRole("combobox", { name: /Processing profile/ })).toHaveValue("auto");
    expect(screen.getByText(/Walk navigation remains disabled/)).toBeInTheDocument();
    expect(screen.getByText(/AI-estimated and non-metric/)).toBeInTheDocument();
  });

  it("renders the 3D rendering hero animation banner when a job is processing", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ jobs: [{
      scene_id: "scene_active", status: "processing", current_stage: "depth_inference",
      capture_mode: "single_photo",
      stages: [
        { name: "discovery", status: "completed" },
        { name: "depth_inference", status: "processing", current_stage: "inferring" },
      ],
      error: null, has_original_input: true, has_viewer_manifest: false,
    }] }), { status: 200 })));

    render(<ProcessingDashboard onClose={vi.fn()} />);
    expect(await screen.findByText(/3D Rendering in Progress/i)).toBeInTheDocument();
    expect(screen.getAllByText(/scene_active/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Reconstructing 3D Spatial Mesh/i)).toBeInTheDocument();
  });
});
