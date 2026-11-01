import { Line, useGLTF } from "@react-three/drei";
import { useLoader } from "@react-three/fiber";
import { useEffect, useMemo, useState } from "react";
import { PLYLoader } from "three/examples/jsm/loaders/PLYLoader.js";
import { DoubleSide, Matrix4, TextureLoader } from "three";
import type { BufferGeometry, Mesh } from "three";
import { assetUrl } from "../api";
import type { SceneAsset, SceneManifest, Vector3Tuple } from "../types";
import { rendererKind } from "./rendererRegistry";
import { disposeObjectResources } from "./resources";
import { transformPointRowMajor } from "./coordinates";

function GltfAsset({ sceneId, asset }: { sceneId: string; asset: SceneAsset }) {
  const url = assetUrl(sceneId, asset.path);
  const gltf = useGLTF(url);
  const clonedScene = useMemo(() => {
    const clone = gltf.scene.clone(true);
    clone.traverse((object) => {
      if (!("isMesh" in object) || !object.isMesh) return;
      const mesh = object as Mesh;
      mesh.geometry = mesh.geometry.clone();
      mesh.material = Array.isArray(mesh.material) ? mesh.material.map((material) => material.clone()) : mesh.material.clone();
    });
    return clone;
  }, [gltf.scene]);
  useEffect(() => () => {
    disposeObjectResources(clonedScene);
  }, [clonedScene]);
  return <primitive object={clonedScene} />;
}

function PointCloudAsset({
  sceneId,
  asset,
  pointSize,
  pointBudget,
  span,
  onLoaded,
}: {
  sceneId: string;
  asset: SceneAsset;
  pointSize: number;
  pointBudget: number;
  span: number;
  onLoaded?: (info: { pointCount: number; triangleCount: number; format: string }) => void;
}) {
  const url = assetUrl(sceneId, asset.path);
  const source = useLoader(PLYLoader, url) as BufferGeometry;
  const geometry = useMemo(() => {
    const clone = source.clone();
    const count = source.getAttribute("position")?.count ?? 0;
    clone.setDrawRange(0, Math.min(count, pointBudget));
    if (!clone.boundingBox) clone.computeBoundingBox();
    if (!clone.boundingSphere) clone.computeBoundingSphere();
    return clone;
  }, [pointBudget, source]);

  useEffect(() => {
    const count = source.getAttribute("position")?.count ?? 0;
    onLoaded?.({ pointCount: count, triangleCount: 0, format: "ply" });
  }, [source, onLoaded]);

  useEffect(() => () => { geometry.dispose(); }, [geometry]);
  const hasColors = geometry.hasAttribute("color");

  // Calibrate visible point size so sparse point clouds are never rendered sub-pixel
  const effectiveSize = Math.max(pointSize || 0.35, span / 200, 0.25);

  return (
    <points geometry={geometry}>
      <pointsMaterial
        size={effectiveSize}
        sizeAttenuation
        vertexColors={hasColors}
        color={hasColors ? "#ffffff" : "#38bdf8"}
        fog={false}
      />
    </points>
  );
}

function PlyMeshTextureMaterial({
  textureUrl,
  wireframe,
}: {
  textureUrl: string;
  wireframe?: boolean;
}) {
  const texture = useLoader(TextureLoader, textureUrl);
  return (
    <meshStandardMaterial
      map={texture}
      side={DoubleSide}
      roughness={0.7}
      wireframe={wireframe}
    />
  );
}

function PlyMeshVertexColorMaterial({
  hasColors,
  wireframe,
}: {
  hasColors: boolean;
  wireframe?: boolean;
}) {
  return (
    <meshStandardMaterial
      vertexColors={hasColors}
      side={DoubleSide}
      roughness={0.9}
      wireframe={wireframe}
    />
  );
}

function PlyMeshAsset({
  sceneId,
  asset,
  textureAsset,
  wireframe,
  onLoaded,
}: {
  sceneId: string;
  asset: SceneAsset;
  textureAsset?: SceneAsset | null;
  wireframe?: boolean;
  onLoaded?: (info: { pointCount: number; triangleCount: number; format: string }) => void;
}) {
  const source = useLoader(PLYLoader, assetUrl(sceneId, asset.path)) as BufferGeometry;
  const geometry = useMemo(() => {
    const clone = source.clone();
    if (!clone.hasAttribute("normal")) clone.computeVertexNormals();
    if (!clone.boundingBox) clone.computeBoundingBox();
    if (!clone.boundingSphere) clone.computeBoundingSphere();
    return clone;
  }, [source]);

  useEffect(() => {
    const pCount = source.getAttribute("position")?.count ?? 0;
    const tCount = source.index ? source.index.count / 3 : Math.floor(pCount / 3);
    onLoaded?.({ pointCount: pCount, triangleCount: tCount, format: "ply_mesh" });
  }, [source, onLoaded]);

  useEffect(() => () => geometry.dispose(), [geometry]);

  const textureUrl = textureAsset ? assetUrl(sceneId, textureAsset.path) : null;
  const hasUvs = geometry.hasAttribute("uv");

  return (
    <mesh geometry={geometry}>
      {textureUrl && hasUvs ? (
        <PlyMeshTextureMaterial textureUrl={textureUrl} wireframe={wireframe} />
      ) : (
        <PlyMeshVertexColorMaterial hasColors={geometry.hasAttribute("color")} wireframe={wireframe} />
      )}
    </mesh>
  );
}

function CameraTrajectory({ sceneId, manifest, span }: { sceneId: string; manifest: SceneManifest; span: number }) {
  const [positions, setPositions] = useState<Vector3Tuple[]>([]);
  const poseAsset = manifest.assets.find((asset) => asset.id === manifest.camera_metadata.pose_asset_id);

  useEffect(() => {
    if (!poseAsset) return;
    const controller = new AbortController();
    fetch(assetUrl(sceneId, poseAsset.path), { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Camera trajectory could not be loaded");
        return response.json();
      })
      .then((document: { positions?: Vector3Tuple[]; poses?: Array<{ camera_center_world: Vector3Tuple }> }) => {
        const sourcePositions = document.positions ?? document.poses?.map((pose) => pose.camera_center_world) ?? [];
        setPositions(sourcePositions.map((position) => transformPointRowMajor(position, manifest.coordinate_system.source_to_scene_matrix_row_major)));
      })
      .catch((error: Error) => {
        if (error.name !== "AbortError") setPositions([]);
      });
    return () => controller.abort();
  }, [poseAsset, sceneId]);

  if (positions.length < 2) return null;
  const markerRadius = Math.max(0.18, Math.min(0.8, span / 140));

  return (
    <group>
      <Line points={positions} color="#f59e0b" lineWidth={2.5} dashed dashSize={0.25} gapSize={0.15} />
      {positions.map((position, index) => (
        <mesh position={position} key={`${position.join("-")}-${index}`}>
          <sphereGeometry args={[markerRadius, 10, 10]} />
          <meshBasicMaterial color={index === 0 ? "#10b981" : "#fbbf24"} />
        </mesh>
      ))}
    </group>
  );
}

export function SceneAssets({
  manifest,
  showDiagnostics,
  pointBudget,
  selectedAssetId,
  wireframe,
  onGeometryLoaded,
}: {
  manifest: SceneManifest;
  showDiagnostics: boolean;
  pointBudget: number;
  selectedAssetId: string | null;
  wireframe?: boolean;
  onGeometryLoaded?: (info: { pointCount: number; triangleCount: number; format: string }) => void;
}) {
  const span = useMemo(() => {
    const min = manifest.bounding_box?.minimum ?? [-5, -1, -5];
    const max = manifest.bounding_box?.maximum ?? [5, 4, 5];
    return Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2], 10);
  }, [manifest.bounding_box]);

  const textureAsset = useMemo(
    () => manifest.assets.find((asset) => asset.role === "texture" || asset.id === "single_photo_texture"),
    [manifest.assets]
  );

  const visualAssets = manifest.assets.filter((asset) => {
    const kind = rendererKind(asset);
    if (kind !== "gltf" && kind !== "point-cloud" && kind !== "ply-mesh") return false;
    if (selectedAssetId) return asset.id === selectedAssetId;
    return asset.role === "primary_visual" || (showDiagnostics && asset.role === "diagnostic") || asset.visible_by_default;
  });
  const sourceToScene = useMemo(() => {
    const values = manifest.coordinate_system.source_to_scene_matrix_row_major;
    return new Matrix4().set(
      values[0], values[1], values[2], values[3],
      values[4], values[5], values[6], values[7],
      values[8], values[9], values[10], values[11],
      values[12], values[13], values[14], values[15],
    );
  }, [manifest.coordinate_system.source_to_scene_matrix_row_major]);
  return (
    <>
      <group matrix={sourceToScene} matrixAutoUpdate={false}>
        {visualAssets.map((asset) => {
          const kind = rendererKind(asset);
          const assetKey = `${manifest.scene_id}-${asset.id}`;
          if (kind === "gltf") return <GltfAsset key={assetKey} sceneId={manifest.scene_id} asset={asset} />;
          if (kind === "point-cloud") {
            return (
              <PointCloudAsset
                key={assetKey}
                sceneId={manifest.scene_id}
                asset={asset}
                pointSize={manifest.viewer.point_size}
                pointBudget={pointBudget}
                span={span}
                onLoaded={onGeometryLoaded}
              />
            );
          }
          if (kind === "ply-mesh") {
            return (
              <PlyMeshAsset
                key={assetKey}
                sceneId={manifest.scene_id}
                asset={asset}
                textureAsset={textureAsset}
                wireframe={wireframe}
                onLoaded={onGeometryLoaded}
              />
            );
          }
          return null;
        })}
      </group>
      {(showDiagnostics || manifest.reconstruction?.backend === "colmap") && (
        <CameraTrajectory sceneId={manifest.scene_id} manifest={manifest} span={span} />
      )}
    </>
  );
}
