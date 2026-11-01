import { OrbitControls } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { Euler, MathUtils, Quaternion, Vector3 } from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import type { CameraMode, CameraTelemetry, ColliderDocument, SceneManifest } from "../types";
import { FirstPersonController, type ControlMode } from "./FirstPersonController";

interface Snapshot { position: Vector3; quaternion: Quaternion }

export function CameraModeRig({ mode, manifest, colliderDocument, speed, sensitivity, smoothing, resetToken, frameSceneToken = 0, teleport, onControlModeChange, onTelemetry }: {
  mode: CameraMode;
  manifest: SceneManifest;
  colliderDocument: ColliderDocument | null;
  speed: number;
  sensitivity: number;
  smoothing: boolean;
  resetToken: number;
  frameSceneToken?: number;
  teleport: { x: number; z: number; token: number } | null;
  onControlModeChange: (mode: ControlMode) => void;
  onTelemetry: (telemetry: CameraTelemetry) => void;
}) {
  const { camera, gl } = useThree();
  const controls = useRef<OrbitControlsImpl>(null);
  const previousMode = useRef<CameraMode>(mode);
  const snapshots = useRef(new Map<CameraMode, Snapshot>());
  const telemetryAt = useRef(0);
  const min = manifest.bounding_box?.minimum ?? [-5, -1, -5];
  const max = manifest.bounding_box?.maximum ?? [5, 4, 5];
  const center = new Vector3(
    (min[0] + max[0]) / 2,
    (min[1] + max[1]) / 2,
    (min[2] + max[2]) / 2,
  );
  const span = Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2]);

  const is25D = Boolean(manifest.viewer?.is_2_5d);
  const sourceCamPos = useMemo(() => {
    const p = manifest.viewer?.source_camera_position;
    return p ? new Vector3(p[0], p[1], p[2]) : new Vector3(0, 0, 0);
  }, [manifest.viewer?.source_camera_position]);

  const sourceCamTarget = useMemo(() => {
    const l = manifest.viewer?.source_camera_look_at;
    return l ? new Vector3(l[0], l[1], l[2]) : new Vector3(center.x, center.y, center.z);
  }, [manifest.viewer?.source_camera_look_at, center.x, center.y, center.z]);

  const activeTarget = is25D ? sourceCamTarget : center;

  const applyDefault = (targetMode: CameraMode) => {
    if (is25D) {
      camera.position.copy(sourceCamPos);
      if ("fov" in camera && manifest.viewer?.source_camera_fov) {
        (camera as any).fov = manifest.viewer.source_camera_fov;
      }
      camera.up.set(0, 1, 0);
      camera.lookAt(sourceCamTarget);
      camera.updateProjectionMatrix();
      return;
    }
    if (targetMode === "first-person" && manifest.navigation?.enabled) {
      camera.position.fromArray(manifest.navigation.spawn_position);
      camera.rotation.set(0, MathUtils.degToRad(manifest.navigation.spawn_yaw_degrees), 0, "YXZ");
    } else if (targetMode === "orbit" || targetMode === "first-person") {
      camera.position.set(center.x + span * 0.75, center.y + span * 0.45, center.z + span * 0.75);
      camera.lookAt(center);
    } else {
      camera.position.set(center.x, manifest.bounding_box.maximum[1] + span * 1.05, center.z + 0.001);
      camera.up.set(0, 0, -1);
      camera.lookAt(center);
    }
    camera.updateProjectionMatrix();
  };

  useEffect(() => {
    snapshots.current.clear();
    applyDefault(mode);
    controls.current?.target.copy(activeTarget);
    controls.current?.update();
  }, [manifest.scene_id]);

  useEffect(() => {
    const previous = previousMode.current;
    if (previous !== mode) snapshots.current.set(previous, { position: camera.position.clone(), quaternion: camera.quaternion.clone() });
    camera.up.set(0, 1, 0);
    const saved = snapshots.current.get(mode);
    if (saved) { camera.position.copy(saved.position); camera.quaternion.copy(saved.quaternion); }
    else applyDefault(mode);
    controls.current?.target.copy(activeTarget);
    controls.current?.update();
    previousMode.current = mode;
  }, [mode]);

  useEffect(() => {
    snapshots.current.delete(mode);
    applyDefault(mode);
    controls.current?.target.copy(activeTarget);
    controls.current?.update();
  }, [resetToken]);

  useEffect(() => {
    if (frameSceneToken > 0) {
      applyDefault(mode);
      controls.current?.target.copy(activeTarget);
      controls.current?.update();
    }
  }, [frameSceneToken]);

  useFrame(() => {
    if (mode === "first-person") return;
    const now = performance.now();
    if (now - telemetryAt.current < 150) return;
    telemetryAt.current = now;
    const rotation = new Euler().setFromQuaternion(camera.quaternion, "YXZ");
    onTelemetry({
      position: [camera.position.x, camera.position.y, camera.position.z],
      yaw: rotation.y,
      mode,
      near: camera.near,
      far: camera.far,
      fov: "fov" in camera ? (camera as any).fov : 68,
      webglStatus: "Active (Rendering)",
      webglRenderer: gl.capabilities.isWebGL2 ? "WebGL 2.0" : "WebGL 1.0",
      visibleObjects: gl.info.render.calls,
    });
  });

  return (
    <>
      <FirstPersonController
        manifest={manifest}
        colliderDocument={colliderDocument}
        speed={speed}
        sensitivity={sensitivity}
        smoothing={smoothing}
        active={mode === "first-person"}
        teleport={teleport}
        resetToken={resetToken}
        onControlModeChange={onControlModeChange}
        onTelemetry={onTelemetry}
      />
      {mode !== "first-person" && (
        <OrbitControls
          key={`${manifest.scene_id}-${mode}`}
          ref={controls}
          makeDefault
          enableDamping
          dampingFactor={0.09}
          target={activeTarget}
          enablePan={true}
          minDistance={0.05}
          maxDistance={is25D ? Math.max(50, span * 3) : Math.max(500, span * 10)}
          minAzimuthAngle={is25D ? -MathUtils.degToRad(35) : -Infinity}
          maxAzimuthAngle={is25D ? MathUtils.degToRad(35) : Infinity}
          minPolarAngle={is25D ? Math.PI / 2 - MathUtils.degToRad(30) : (mode === "overview" ? 0 : 0.01)}
          maxPolarAngle={is25D ? Math.PI / 2 + MathUtils.degToRad(30) : (mode === "overview" ? 0.38 : Math.PI - 0.01)}
        />
      )}
    </>
  );
}
