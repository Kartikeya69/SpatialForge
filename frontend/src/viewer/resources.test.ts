import { BoxGeometry, Group, Mesh, MeshBasicMaterial } from "three";
import { describe, expect, it, vi } from "vitest";
import { disposeObjectResources } from "./resources";

describe("resource cleanup", () => {
  it("disposes geometry and material resources", () => {
    const geometry = new BoxGeometry();
    const material = new MeshBasicMaterial();
    const geometryDispose = vi.spyOn(geometry, "dispose");
    const materialDispose = vi.spyOn(material, "dispose");
    const group = new Group();
    group.add(new Mesh(geometry, material));
    disposeObjectResources(group);
    expect(geometryDispose).toHaveBeenCalledOnce();
    expect(materialDispose).toHaveBeenCalledOnce();
  });
});
