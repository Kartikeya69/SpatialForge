import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CreateWorkflowView } from "./CreateWorkflowView";

class MockXMLHttpRequest {
  upload = { onprogress: null as any };
  status = 200;
  response = { scene_id: "scene_test_123", status: "queued" };
  onload = null as any;
  onloadend = null as any;
  open() {}
  send() {
    queueMicrotask(() => {
      this.onload?.();
      this.onloadend?.();
    });
  }
  abort() {}
}

beforeEach(() => {
  vi.stubGlobal("XMLHttpRequest", MockXMLHttpRequest);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL | Request) => {
      const u = typeof url === "string" ? url : "url" in url ? url.url : url.toString();
      if (u.includes("analyze-capture")) {
        return new Response(
          JSON.stringify({
            job: {
              scene_id: "scene_test_123",
              status: "awaiting_reconstruction",
              current_stage: "readiness",
              stages: [
                { name: "frame_extraction", status: "completed" },
                {
                  name: "readiness",
                  status: "completed",
                  details: {
                    accepted_frames: 24,
                    sharpness_mean: 185.4,
                    median_match_ratio: 0.48,
                    median_displacement_pixels: 14.2,
                  },
                },
              ],
            },
          }),
          { status: 200 }
        );
      }
      if (u.includes("clear-history")) {
        return new Response(JSON.stringify({ deleted: ["scene_old_1"], count: 1 }), { status: 200 });
      }
      if (u.includes("pipeline/jobs")) {
        return new Response(
          JSON.stringify([
            {
              scene_id: "scene_test_123",
              status: "ready",
              current_stage: "viewer_package",
              stages: [
                { name: "frame_extraction", status: "completed" },
                { name: "sparse_reconstruction", status: "completed" },
                { name: "viewer_package", status: "completed" },
              ],
            },
          ]),
          { status: 200 }
        );
      }
      return new Response(JSON.stringify({ scene_id: "scene_test_123", status: "queued" }), { status: 200 });
    })
  );
});

describe("CreateWorkflowView", () => {
  it("renders the 3 distinct capture cards with clear actions", () => {
    render(<CreateWorkflowView onSelectScene={vi.fn()} onNavigateTab={vi.fn()} />);
    expect(screen.getByRole("heading", { name: /Create a New 3D Scene/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Video to 3D/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Photo Set to 3D/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Single Photo to 3D/i })).toBeInTheDocument();
  });

  it("switches capture mode and displays dedicated dropzone instructions", () => {
    render(<CreateWorkflowView onSelectScene={vi.fn()} onNavigateTab={vi.fn()} />);

    // Default mode is video
    expect(screen.getByText(/Drop your room walkthrough video here/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Browse Files/i })).toBeInTheDocument();

    // Switch to Photo Set
    fireEvent.click(screen.getByRole("button", { name: /Photo Set to 3D/i }));
    expect(screen.getByText(/Drop multiple overlapping photographs here/i)).toBeInTheDocument();

    // Switch to Single Photo
    fireEvent.click(screen.getByRole("button", { name: /Single Photo to 3D/i }));
    expect(screen.getByText(/Drop a single room photo here/i)).toBeInTheDocument();
  });

  it("reveals advanced configuration options on toggle", () => {
    render(<CreateWorkflowView onSelectScene={vi.fn()} onNavigateTab={vi.fn()} />);

    // Select a mock video file to reveal configuration panel
    const file = new File(["dummy-video-content"], "room_walkthrough.mp4", { type: "video/mp4" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(input, "files", { value: [file] });
    fireEvent.change(input);

    expect(screen.getByText(/Reconstruction Configuration/i)).toBeInTheDocument();
    expect(screen.queryByText(/Hardware & Photogrammetry Parameters/i)).not.toBeInTheDocument();

    // Toggle advanced options
    fireEvent.click(screen.getByRole("button", { name: /Show Advanced Options/i }));
    expect(screen.getByText(/Hardware & Photogrammetry Parameters/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/COLMAP Camera Model/i)).toBeInTheDocument();
  });

  it("handles extract and analyze workflow and displays diagnostics before reconstruction", async () => {
    render(<CreateWorkflowView onSelectScene={vi.fn()} onNavigateTab={vi.fn()} />);

    const file = new File(["dummy-video-content"], "room_walkthrough.mp4", { type: "video/mp4" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(input, "files", { value: [file] });
    fireEvent.change(input);

    // Initial button is Extract & Analyze Frames
    const analyzeBtn = screen.getByRole("button", { name: /Extract & Analyze Frames/i });
    expect(analyzeBtn).toBeInTheDocument();

    fireEvent.click(analyzeBtn);

    await waitFor(() => {
      expect(screen.getByText(/Frame & Overlap Diagnostics/i)).toBeInTheDocument();
      expect(screen.getByText(/24 accepted/i)).toBeInTheDocument();
      expect(screen.getByText(/48%/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Start 3D Reconstruction/i })).toBeInTheDocument();
    });
  });

  it("triggers clear incomplete history action", async () => {
    render(<CreateWorkflowView onSelectScene={vi.fn()} onNavigateTab={vi.fn()} />);

    const clearBtn = screen.getByRole("button", { name: /Clear Incomplete History/i });
    fireEvent.click(clearBtn);

    await waitFor(() => {
      expect(screen.getByText(/Cleared 1 incomplete \/ failed history runs/i)).toBeInTheDocument();
    });
  });
});
