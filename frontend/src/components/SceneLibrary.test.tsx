import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { SceneSummary } from "../types";
import { SceneLibrary } from "./SceneLibrary";

const scenes: SceneSummary[] = [
  { scene_id: "lab", scene_name: "Twin Lab", description: "Indoor demo", processing_status: "completed", synthetic_demo: true, asset_types: ["gltf"], manifest_url: "/lab" },
  { scene_id: "atrium", scene_name: "Atrium", description: "Point cloud", processing_status: "completed", synthetic_demo: false, asset_types: ["ply"], manifest_url: "/atrium" },
];

describe("SceneLibrary", () => {
  it("searches and selects scenes", () => {
    const onSelect = vi.fn();
    render(<SceneLibrary scenes={scenes} selectedId="lab" onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: /active scene/i }));
    fireEvent.change(screen.getByLabelText("Search scenes"), { target: { value: "point cloud" } });
    expect(screen.queryByText("Twin Lab", { selector: ".scene-card-copy strong" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Atrium/ }));
    expect(onSelect).toHaveBeenCalledWith("atrium");
  });

  it("closes with Escape", () => {
    render(<SceneLibrary scenes={scenes} selectedId="lab" onSelect={() => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: /active scene/i }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
