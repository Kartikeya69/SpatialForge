import type { SceneManifest } from "./types";

export function validateSceneManifest(value: unknown): SceneManifest {
  if (!value || typeof value !== "object") throw new Error("Scene manifest is not a JSON object");
  const manifest = value as Partial<SceneManifest>;
  if (manifest.schema_version !== "1.0.0") throw new Error(`Unsupported scene schema: ${String(manifest.schema_version)}`);
  if (!manifest.scene_id || !manifest.scene_name) throw new Error("Scene manifest is missing its identity");
  if (!manifest.bounding_box?.minimum || !manifest.bounding_box?.maximum) throw new Error("Scene bounds are missing");
  if (!manifest.navigation?.spawn_position) throw new Error("Navigation spawn position is missing");
  if (!Array.isArray(manifest.assets)) throw new Error("Scene assets must be an array");
  return manifest as SceneManifest;
}
