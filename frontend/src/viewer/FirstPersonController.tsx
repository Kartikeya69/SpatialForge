import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import { Euler, MathUtils } from "three";
import type { CameraTelemetry, ColliderDocument, SceneManifest } from "../types";
import { resolveMovement } from "./collision";
import { transitionControlMode } from "./interaction";
import { applyLookDelta } from "./look";
import { movementVector } from "./movement";
import { movementDistance, smoothingAlpha } from "./motion";

export type ControlMode = "idle" | "free" | "dragging" | "locked";

export function FirstPersonController({
  manifest,
  colliderDocument,
  speed,
  sensitivity,
  smoothing,
  active,
  teleport,
  resetToken,
  onControlModeChange,
  onTelemetry,
}: {
  manifest: SceneManifest;
  colliderDocument: ColliderDocument | null;
  speed: number;
  sensitivity: number;
  smoothing: boolean;
  active: boolean;
  teleport: { x: number; z: number; token: number } | null;
  resetToken: number;
  onControlModeChange: (mode: ControlMode) => void;
  onTelemetry: (telemetry: CameraTelemetry) => void;
}) {
  const { camera, gl } = useThree();
  const keys = useRef(new Set<string>());
  const yaw = useRef(MathUtils.degToRad(manifest.navigation.spawn_yaw_degrees));
  const pitch = useRef(0);
  const drag = useRef<{ pointerId: number; x: number; y: number } | null>(null);
  const freeLook = useRef(false);
  const didDrag = useRef(false);
  const velocity = useRef({ x: 0, z: 0 });
  const telemetryAt = useRef(0);

  const updateLook = (deltaX: number, deltaY: number) => {
    const next = applyLookDelta({ yaw: yaw.current, pitch: pitch.current }, deltaX, deltaY, sensitivity);
    yaw.current = next.yaw;
    pitch.current = next.pitch;
  };

  const reset = () => {
    const [x, y, z] = manifest.navigation.spawn_position;
    camera.position.set(x, y, z);
    yaw.current = MathUtils.degToRad(manifest.navigation.spawn_yaw_degrees);
    pitch.current = 0;
    camera.rotation.set(0, yaw.current, 0, "YXZ");
    velocity.current = { x: 0, z: 0 };
  };

  useEffect(() => { if (active) reset(); }, [camera, manifest, resetToken]);

  useEffect(() => {
    if (!active) return;
    const rotation = new Euler().setFromQuaternion(camera.quaternion, "YXZ");
    yaw.current = rotation.y;
    pitch.current = rotation.x;
  }, [active, camera]);

  useEffect(() => {
    if (!active || !teleport) return;
    camera.position.x = teleport.x;
    camera.position.z = teleport.z;
    velocity.current = { x: 0, z: 0 };
  }, [active, camera, teleport]);

  useEffect(() => {
    const canvas = gl.domElement;
    canvas.tabIndex = 0;
    canvas.setAttribute("aria-label", "Interactive 3D scene. Click or drag to look, use WASD to move, or double-click for pointer lock.");

    const onDoubleClick = () => {
      try {
        const request = canvas.requestPointerLock?.();
        if (request instanceof Promise) request.catch(() => onControlModeChange("idle"));
      } catch {
        onControlModeChange("idle");
      }
    };
    const onPointerLock = () => {
      drag.current = null;
      freeLook.current = false;
      onControlModeChange(transitionControlMode("locked", document.pointerLockElement === canvas ? "pointer-lock" : "pointer-unlock"));
    };
    const onMouseMove = (event: MouseEvent) => {
      if (document.pointerLockElement !== canvas) return;
      updateLook(event.movementX, event.movementY);
    };
    const onPointerDown = (event: PointerEvent) => {
      if (!active || event.button !== 0 || document.pointerLockElement === canvas) return;
      canvas.focus({ preventScroll: true });
      didDrag.current = false;
      drag.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
      canvas.setPointerCapture?.(event.pointerId);
      canvas.dataset.dragging = "true";
      onControlModeChange(transitionControlMode("idle", "drag-start"));
    };
    const onPointerMove = (event: PointerEvent) => {
      if (drag.current && drag.current.pointerId === event.pointerId) {
        const deltaX = event.clientX - drag.current.x;
        const deltaY = event.clientY - drag.current.y;
        if (deltaX !== 0 || deltaY !== 0) didDrag.current = true;
        updateLook(deltaX, deltaY);
        drag.current.x = event.clientX;
        drag.current.y = event.clientY;
        return;
      }
      if (freeLook.current && document.pointerLockElement !== canvas) {
        updateLook(event.movementX, event.movementY);
      }
    };
    const finishDrag = (event: PointerEvent) => {
      if (!drag.current || drag.current.pointerId !== event.pointerId) return;
      if (canvas.hasPointerCapture?.(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
      drag.current = null;
      delete canvas.dataset.dragging;
      if (didDrag.current) onControlModeChange(transitionControlMode("dragging", "drag-end"));
    };
    const onClick = () => {
      if (didDrag.current) {
        didDrag.current = false;
        return;
      }
      freeLook.current = !freeLook.current;
      onControlModeChange(transitionControlMode(freeLook.current ? "idle" : "free", "click"));
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (!active) return;
      keys.current.add(event.code);
      if (event.code === "KeyR") reset();
      if (event.code === "Escape" && freeLook.current) {
        freeLook.current = false;
        onControlModeChange(transitionControlMode("free", "escape"));
      }
    };
    const onKeyUp = (event: KeyboardEvent) => keys.current.delete(event.code);
    canvas.addEventListener("dblclick", onDoubleClick);
    canvas.addEventListener("click", onClick);
    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", finishDrag);
    canvas.addEventListener("pointercancel", finishDrag);
    document.addEventListener("pointerlockchange", onPointerLock);
    document.addEventListener("mousemove", onMouseMove);
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      canvas.removeEventListener("dblclick", onDoubleClick);
      canvas.removeEventListener("click", onClick);
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", finishDrag);
      canvas.removeEventListener("pointercancel", finishDrag);
      document.removeEventListener("pointerlockchange", onPointerLock);
      document.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, [active, camera, gl, manifest, onControlModeChange, sensitivity]);

  useEffect(() => {
    if (active) return;
    keys.current.clear();
    freeLook.current = false;
    velocity.current = { x: 0, z: 0 };
    if (document.pointerLockElement === gl.domElement) document.exitPointerLock?.();
    onControlModeChange("idle");
  }, [active, gl, onControlModeChange]);

  useFrame((_, rawDelta) => {
    if (!active) return;
    const delta = Math.min(rawDelta, 0.1);
    camera.rotation.set(pitch.current, yaw.current, 0, "YXZ");
    const direction = movementVector(
      {
        forward: keys.current.has("KeyW") || keys.current.has("ArrowUp"),
        backward: keys.current.has("KeyS") || keys.current.has("ArrowDown"),
        left: keys.current.has("KeyA") || keys.current.has("ArrowLeft"),
        right: keys.current.has("KeyD") || keys.current.has("ArrowRight"),
      },
      yaw.current,
    );
    const sprint = keys.current.has("ShiftLeft") || keys.current.has("ShiftRight") ? 1.7 : 1;
    const targetX = direction.x * speed * sprint;
    const targetZ = direction.z * speed * sprint;
    const alpha = smoothing ? smoothingAlpha(delta, 12) : 1;
    velocity.current.x += (targetX - velocity.current.x) * alpha;
    velocity.current.z += (targetZ - velocity.current.z) * alpha;
    const distance = movementDistance(1, delta);
    const desired = {
      x: camera.position.x + velocity.current.x * distance,
      z: camera.position.z + velocity.current.z * distance,
    };
    if (colliderDocument) {
      const resolved = resolveMovement(
        { x: camera.position.x, z: camera.position.z },
        desired,
        manifest.navigation.collision_radius,
        colliderDocument.colliders,
        colliderDocument.walkable_bounds,
      );
      camera.position.x = resolved.x;
      camera.position.z = resolved.z;
    } else {
      camera.position.x = desired.x;
      camera.position.z = desired.z;
    }
    camera.position.y = manifest.navigation.spawn_position[1];
    const now = performance.now();
    if (now - telemetryAt.current > 150) {
      telemetryAt.current = now;
      onTelemetry({ position: [camera.position.x, camera.position.y, camera.position.z], yaw: yaw.current, mode: "first-person" });
    }
  });
  return null;
}
