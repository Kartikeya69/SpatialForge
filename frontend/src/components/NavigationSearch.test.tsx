import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { NavigationSearch } from "./NavigationSearch";
import type { POI } from "../types";

const points: POI[] = [
  { id: "poi_reception", name: "Reception", category: "service", description: "Front desk", aliases: ["check in"], position: [0, 0, 0], arrival_points: [[0, 0, 0]], floor_id: "ground", bounds: null, zone: "entry" },
  { id: "poi_meeting", name: "Meeting Room A", category: "room", description: "Conference room", aliases: ["meeting"], position: [2, 0, 2], arrival_points: [[2, 0, 2]], floor_id: "ground", bounds: null, zone: "meeting" },
];

describe("NavigationSearch", () => {
  it("searches aliases and selects with the keyboard", () => {
    const select = vi.fn();
    render(<NavigationSearch pois={points} loading={false} error={null} activePoiId={null} onSelect={select} onAuthor={vi.fn()} />);
    const input = screen.getByLabelText("Search rooms, objects, or categories");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "meeting" } });
    expect(screen.getByText("Meeting Room A")).toBeInTheDocument();
    expect(screen.queryByText("Reception")).not.toBeInTheDocument();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(select).toHaveBeenCalledWith(points[1]);
  });

  it("shows empty and error states", () => {
    const { rerender } = render(<NavigationSearch pois={[]} loading={false} error={null} activePoiId={null} onSelect={vi.fn()} onAuthor={vi.fn()} />);
    fireEvent.focus(screen.getByLabelText("Search rooms, objects, or categories"));
    expect(screen.getByText("No matching destinations")).toBeInTheDocument();
    rerender(<NavigationSearch pois={[]} loading={false} error="Navigation unavailable" activePoiId={null} onSelect={vi.fn()} onAuthor={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Navigation unavailable");
  });
});
