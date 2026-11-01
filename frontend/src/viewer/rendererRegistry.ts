import type { AssetType, SceneAsset } from "../types";

export type RendererKind = "gltf" | "point-cloud" | "ply-mesh" | "future-splat" | "non-visual";

const rendererKinds: Record<AssetType, RendererKind> = {
  glb: "gltf",
  gltf: "gltf",
  ply: "point-cloud",
  ply_mesh: "ply-mesh",
  gaussian_splat: "future-splat",
  navigation_grid: "non-visual",
  collider_geometry: "non-visual",
  camera_poses: "non-visual",
  poi_metadata: "non-visual",
  texture: "non-visual",
  image: "non-visual",
};

export function rendererKind(asset: SceneAsset): RendererKind {
  return rendererKinds[asset.type];
}
