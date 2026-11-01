import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import type { RenderMetrics } from "../types";

export function PerformanceProbe({ enabled, onMetrics }: { enabled: boolean; onMetrics: (metrics: RenderMetrics) => void }) {
  const { gl } = useThree();
  const sample = useRef({ startedAt: 0, frames: 0 });
  useEffect(() => { sample.current = { startedAt: 0, frames: 0 }; }, [enabled]);
  useFrame(() => {
    if (!enabled) return;
    const now = performance.now();
    if (!sample.current.startedAt) sample.current.startedAt = now;
    sample.current.frames += 1;
    const elapsed = now - sample.current.startedAt;
    if (elapsed < 800) return;
    const fps = (sample.current.frames * 1000) / elapsed;
    onMetrics({
      fps: Math.round(fps),
      frameTimeMs: Number((1000 / Math.max(fps, 0.001)).toFixed(1)),
      drawCalls: gl.info.render.calls,
      triangles: gl.info.render.triangles,
      points: gl.info.render.points,
      geometries: gl.info.memory.geometries,
      textures: gl.info.memory.textures,
    });
    sample.current = { startedAt: now, frames: 0 };
  });
  return null;
}
