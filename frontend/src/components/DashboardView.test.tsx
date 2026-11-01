import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { DashboardView } from "./DashboardView";
import * as api from "../api";
import type { SceneSummary } from "../types";

describe("DashboardView regression and functionality tests", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    api.setAppMode("full");
  });

  it("renders empty state without crashing when scenes array is empty", () => {
    render(
      <DashboardView
        scenes={[]}
        onOpenScene={vi.fn()}
        onStartCapture={vi.fn()}
        onNavigateTab={vi.fn()}
      />
    );
    expect(screen.getByText("No reconstructed scenes yet")).toBeInTheDocument();
  });

  it("reproduces and prevents crash when scenes have undefined asset_types (original crash bug)", () => {
    // This previously threw "Cannot read properties of undefined (reading 'includes')"
    const scenesWithMissingFields = [
      {
        scene_id: "scene_crash_test",
        scene_name: "Minimal Scene",
        description: "Scene without asset_types array",
        processing_status: "completed",
        synthetic_demo: false,
        // asset_types omitted intentionally
        manifest_url: "/manifest",
      } as unknown as SceneSummary,
    ];

    expect(() => {
      render(
        <DashboardView
          scenes={scenesWithMissingFields}
          onOpenScene={vi.fn()}
          onStartCapture={vi.fn()}
          onNavigateTab={vi.fn()}
        />
      );
    }).not.toThrow();

    expect(screen.getByText("Minimal Scene")).toBeInTheDocument();
  });

  it("renders recent scenes and triggers open in viewer", () => {
    const onOpenScene = vi.fn();
    const testScenes: SceneSummary[] = [
      {
        scene_id: "scene_001",
        scene_name: "Living Room Video",
        description: "Reconstructed video",
        processing_status: "completed",
        synthetic_demo: false,
        asset_types: ["ply"],
        primary_asset_type: "ply",
        manifest_url: "/manifest",
      },
    ];

    render(
      <DashboardView
        scenes={testScenes}
        onOpenScene={onOpenScene}
        onStartCapture={vi.fn()}
        onNavigateTab={vi.fn()}
      />
    );

    expect(screen.getByText("Living Room Video")).toBeInTheDocument();
    const openBtn = screen.getByText("◈ Open in Viewer");
    fireEvent.click(openBtn);
    expect(onOpenScene).toHaveBeenCalledWith("scene_001");
  });

  it("triggers capture navigation when clicking workflow cards", () => {
    const onStartCapture = vi.fn();
    render(
      <DashboardView
        scenes={[]}
        onOpenScene={vi.fn()}
        onStartCapture={onStartCapture}
        onNavigateTab={vi.fn()}
      />
    );

    fireEvent.click(screen.getByText("Start Video Capture →"));
    expect(onStartCapture).toHaveBeenCalledWith("video");

    fireEvent.click(screen.getByText("Start Photo Set Capture →"));
    expect(onStartCapture).toHaveBeenCalledWith("photo_set");

    fireEvent.click(screen.getByText("Start Single-Photo Capture →"));
    expect(onStartCapture).toHaveBeenCalledWith("single_photo");
  });

  it("displays public showcase banner when in showcase mode", () => {
    api.setAppMode("showcase");
    render(
      <DashboardView
        scenes={[]}
        onOpenScene={vi.fn()}
        onStartCapture={vi.fn()}
        onNavigateTab={vi.fn()}
      />
    );

    expect(screen.getByText("Public Web Showcase")).toBeInTheDocument();
    expect(screen.getByText("Public Showcase · Read-Only")).toBeInTheDocument();
  });
});
