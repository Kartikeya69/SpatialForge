import type { Material, Object3D } from "three";

export function disposeObjectResources(root: Object3D): void {
  root.traverse((object) => {
    const candidate = object as Object3D & { geometry?: { dispose: () => void }; material?: Material | Material[] };
    candidate.geometry?.dispose();
    const materials = candidate.material ? (Array.isArray(candidate.material) ? candidate.material : [candidate.material]) : [];
    materials.forEach((material) => material.dispose());
  });
}
