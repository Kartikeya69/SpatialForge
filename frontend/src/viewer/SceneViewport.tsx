import { Canvas, useThree } from "@react-three/fiber";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { ACESFilmicToneMapping, SRGBColorSpace } from "three";
import type { CameraMode, CameraTelemetry, ColliderDocument, QualityPreset, RenderMetrics, RouteResult, SceneManifest } from "../types";
import { CameraModeRig } from "./CameraModeRig";
import type { ControlMode } from "./FirstPersonController";
import { PerformanceProbe } from "./PerformanceProbe";
import { qualitySettings } from "./quality";
import { SceneAssets } from "./SceneAssets";
import { RouteOverlay } from "./RouteOverlay";

function WebGLContextMonitor({ onLost, onRestored }: { onLost: () => void; onRestored: () => void }) {
  const { gl } = useThree();
  useEffect(() => {
    const canvas = gl.domElement;
    const handleLost = (event: Event) => { event.preventDefault(); onLost(); };
    canvas.addEventListener("webglcontextlost", handleLost);
    canvas.addEventListener("webglcontextrestored", onRestored);
    return () => {
      canvas.removeEventListener("webglcontextlost", handleLost);
      canvas.removeEventListener("webglcontextrestored", onRestored);
    };
  }, [gl, onLost, onRestored]);
  return null;
}

export function SceneViewport({
  manifest,
  colliderDocument,
  movementSpeed,
  mouseSensitivity,
  smoothing,
  cameraMode,
  quality,
  resetToken,
  frameSceneToken = 0,
  teleport,
  showDiagnostics,
  collectMetrics,
  onControlModeChange,
  onTelemetry,
  onMetrics,
  onLoadedGeometryInfo,
  route,
  selectedAssetId,
  wireframe,
}: {
  manifest: SceneManifest;
  colliderDocument: ColliderDocument | null;
  movementSpeed: number;
  mouseSensitivity: number;
  smoothing: boolean;
  cameraMode: CameraMode;
  quality: QualityPreset;
  resetToken: number;
  frameSceneToken?: number;
  teleport: { x: number; z: number; token: number } | null;
  showDiagnostics: boolean;
  collectMetrics: boolean;
  onControlModeChange: (mode: ControlMode) => void;
  onTelemetry: (telemetry: CameraTelemetry) => void;
  onMetrics: (metrics: RenderMetrics) => void;
  onLoadedGeometryInfo?: (info: { pointCount: number; triangleCount: number; format: string }) => void;
  route: RouteResult | null;
  selectedAssetId: string | null;
  wireframe?: boolean;
}) {
  const [contextLost, setContextLost] = useState(false);
  const stableControlHandler = useCallback(onControlModeChange, [onControlModeChange]);
  const stableTelemetryHandler = useCallback(onTelemetry, [onTelemetry]);
  const stableMetricsHandler = useCallback(onMetrics, [onMetrics]);
  const handleContextLost = useCallback(() => setContextLost(true), []);
  const handleContextRestored = useCallback(() => setContextLost(false), []);
  const settings = qualitySettings(quality);

  const span = useMemo(() => {
    const min = manifest.bounding_box?.minimum ?? [-5, -1, -5];
    const max = manifest.bounding_box?.maximum ?? [5, 4, 5];
    return Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2], 10);
  }, [manifest.bounding_box]);

  const cameraFar = useMemo(() => Math.max(2500, span * 30), [span]);
  const fogNear = useMemo(() => Math.max(span * 3.5, 120), [span]);
  const fogFar = useMemo(() => Math.max(span * 10.0, 500), [span]);

  return (
    <div className="viewport" data-testid="scene-viewport">
      <Canvas
        key={manifest.scene_id}
        shadows={settings.shadows}
        dpr={settings.dpr}
        gl={{ antialias: settings.antialias, powerPreference: "high-performance", toneMapping: ACESFilmicToneMapping, outputColorSpace: SRGBColorSpace }}
        camera={{ fov: 68, near: 0.05, far: cameraFar, position: manifest.navigation.spawn_position }}
      >
        <WebGLContextMonitor onLost={handleContextLost} onRestored={handleContextRestored} />
        <color attach="background" args={[manifest.viewer.background]} />
        <fog attach="fog" args={[manifest.viewer.background, fogNear, fogFar]} />
        <ambientLight intensity={manifest.viewer.ambient_light_intensity} />
        <directionalLight
          castShadow
          intensity={manifest.viewer.directional_light_intensity}
          position={[4, 8, -3]}
          shadow-mapSize={[1024, 1024]}
        />
        <Suspense fallback={null}>
          <SceneAssets
            key={manifest.scene_id}
            manifest={manifest}
            showDiagnostics={showDiagnostics}
            pointBudget={settings.pointBudget}
            selectedAssetId={selectedAssetId}
            wireframe={wireframe}
            onGeometryLoaded={onLoadedGeometryInfo}
          />
          {route && <RouteOverlay route={route} />}
        </Suspense>
        <CameraModeRig
          mode={cameraMode}
          manifest={manifest}
          colliderDocument={colliderDocument}
          speed={movementSpeed}
          sensitivity={mouseSensitivity}
          smoothing={smoothing}
          teleport={teleport}
          resetToken={resetToken}
          frameSceneToken={frameSceneToken}
          onControlModeChange={stableControlHandler}
          onTelemetry={stableTelemetryHandler}
        />
        <PerformanceProbe enabled={collectMetrics} onMetrics={stableMetricsHandler} />
      </Canvas>
      {contextLost && <div className="context-loss" role="alert"><strong>Graphics context interrupted</strong><span>SpatialForge is waiting for the browser to restore WebGL.</span></div>}
      <div className="crosshair" aria-hidden="true" />
    </div>
  );
}

export default SceneViewport;
