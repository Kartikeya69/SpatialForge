import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SceneSelector } from "./SceneSelector";

const scenes = [
  { scene_id: "scene_one", scene_name: "One", description: "", processing_status: "completed", synthetic_demo: false, asset_types: [], manifest_url: "/one" },
  { scene_id: "scene_two", scene_name: "Two", description: "", processing_status: "demonstration", synthetic_demo: true, asset_types: [], manifest_url: "/two" },
];

describe("SceneSelector", () => {
  it("switches scenes without hardcoded venue logic", () => {
    const onSelect = vi.fn();
    render(<SceneSelector scenes={scenes} selectedId="scene_one" onSelect={onSelect} />);
    fireEvent.change(screen.getByLabelText("Active scene"), { target: { value: "scene_two" } });
    expect(onSelect).toHaveBeenCalledWith("scene_two");
    expect(screen.getByRole("option", { name: "Two · Demo" })).toBeInTheDocument();
  });
});
