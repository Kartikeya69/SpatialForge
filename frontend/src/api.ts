import type { ColliderDocument, NavigationGrid, PipelineJob, POI, RouteResult, SceneManifest, SceneSummary, UnifiedQualityReport, Vector3Tuple, ViewerPackValidation } from "./types";

async function requestJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail ?? `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function sendJson<T>(url: string, method: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { method, signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail ?? `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export type AppRuntimeMode = "full" | "showcase";

function detectInitialMode(): AppRuntimeMode {
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1") {
      const explicitMode = (import.meta.env.VITE_APP_MODE as string | undefined)?.toLowerCase();
      return explicitMode === "showcase" ? "showcase" : "full";
    }
  }

  const envMode = (import.meta.env.VITE_APP_MODE as string | undefined)?.toLowerCase();
  if (envMode === "full") return "full";
  return "showcase";
}

let activeMode: AppRuntimeMode = detectInitialMode();

export function getAppMode(): AppRuntimeMode {
  return activeMode;
}

export function isShowcaseMode(): boolean {
  return activeMode === "showcase";
}

export function isFullMode(): boolean {
  return activeMode === "full";
}

export function setAppMode(mode: AppRuntimeMode): void {
  activeMode = mode;
}

export function isStandalone(): boolean {
  return isShowcaseMode();
}

export function setStandaloneMode(enabled: boolean): void {
  activeMode = enabled ? "showcase" : "full";
}

function ensureFullModeAllowed(operation: string): void {
  if (isShowcaseMode()) {
    throw new Error(`${operation} is not available in Public Showcase mode. Run SpatialForge locally to process new captures.`);
  }
}

export async function listScenes(signal?: AbortSignal): Promise<SceneSummary[]> {
  if (isShowcaseMode()) {
    const showcase = await requestJson<{ scenes: SceneSummary[] }>("/showcase/scenes.json", signal);
    return showcase.scenes;
  }
  const result = await requestJson<{ scenes: SceneSummary[] }>("/api/v1/scenes", signal);
  return result.scenes;
}

export async function loadManifest(sceneId: string, signal?: AbortSignal): Promise<SceneManifest> {
  if (isShowcaseMode()) {
    return requestJson(`/showcase/${encodeURIComponent(sceneId)}/metadata/scene_manifest.json`, signal);
  }
  return requestJson(`/api/v1/scenes/${encodeURIComponent(sceneId)}/manifest`, signal);
}

export function assetUrl(sceneId: string, path: string): string {
  const encodedPath = path.split("/").map(encodeURIComponent).join("/");
  if (isShowcaseMode()) {
    return `/showcase/${encodeURIComponent(sceneId)}/${encodedPath}`;
  }
  return `/api/v1/scenes/${encodeURIComponent(sceneId)}/assets/${encodedPath}`;
}

export function loadColliders(
  sceneId: string,
  manifest: SceneManifest,
  signal?: AbortSignal,
): Promise<ColliderDocument | null> {
  const assetId = manifest.navigation.collider_asset_id;
  if (!assetId) return Promise.resolve(null);
  const asset = manifest.assets.find((candidate) => candidate.id === assetId);
  if (!asset) return Promise.reject(new Error("Scene collider asset is not declared"));
  return requestJson(assetUrl(sceneId, asset.path), signal);
}

export function loadNavigationGrid(sceneId: string, manifest: SceneManifest, signal?: AbortSignal): Promise<NavigationGrid | null> {
  const assetId = manifest.navigation.grid_asset_id;
  if (!assetId) return Promise.resolve(null);
  const asset = manifest.assets.find((candidate) => candidate.id === assetId);
  if (!asset) return Promise.reject(new Error("Scene navigation grid asset is not declared"));
  return requestJson(assetUrl(sceneId, asset.path), signal);
}

export async function searchPois(sceneId: string, query = "", signal?: AbortSignal): Promise<POI[]> {
  if (isShowcaseMode()) {
    const raw = await requestJson<POI[] | { points?: POI[] }>(`/showcase/${encodeURIComponent(sceneId)}/metadata/pois.json`, signal).catch(() => []);
    const list = Array.isArray(raw) ? raw : raw.points ?? [];
    return query ? list.filter((p) => p.name.toLowerCase().includes(query.toLowerCase())) : list;
  }
  const result = await requestJson<{ points: POI[] }>(`/api/v1/scenes/${encodeURIComponent(sceneId)}/pois?q=${encodeURIComponent(query)}`, signal);
  return result.points;
}

export function createRoute(sceneId: string, start: Vector3Tuple, destinationPoiId: string, signal?: AbortSignal): Promise<RouteResult> {
  return sendJson(`/api/v1/scenes/${encodeURIComponent(sceneId)}/routes`, "POST", {
    start,
    destination_poi_id: destinationPoiId,
    preferences: { connectivity: 8, clearance: 0.28, simplify: true, resolve_nearest: true, max_snap_distance: 1.0 },
  }, signal);
}

export function createPoi(sceneId: string, poi: POI, signal?: AbortSignal): Promise<POI> {
  ensureFullModeAllowed("Creating points of interest");
  return sendJson(`/api/v1/scenes/${encodeURIComponent(sceneId)}/pois`, "POST", poi, signal);
}

export async function listPipelineJobs(signal?: AbortSignal): Promise<PipelineJob[]> {
  if (isShowcaseMode()) return [];
  const result = await requestJson<{ jobs: PipelineJob[] }>("/api/v1/pipeline/jobs", signal);
  return result.jobs;
}

export async function analyzePipelineCapture(sceneId: string, signal?: AbortSignal): Promise<PipelineJob> {
  ensureFullModeAllowed("Capture analysis");
  const result = await sendJson<{ job: PipelineJob }>(`/api/v1/pipeline/jobs/${encodeURIComponent(sceneId)}/analyze-capture`, "POST", {}, signal);
  return result.job;
}

export async function startReconstruction(sceneId: string, signal?: AbortSignal): Promise<void> {
  ensureFullModeAllowed("Starting 3D reconstruction");
  await sendJson(`/api/v1/scenes/${encodeURIComponent(sceneId)}/reconstruct`, "POST", {}, signal);
}

export async function cancelCapture(sceneId: string, signal?: AbortSignal): Promise<void> {
  ensureFullModeAllowed("Cancelling capture");
  await sendJson(`/api/v1/captures/${encodeURIComponent(sceneId)}/cancel`, "POST", {}, signal);
}

function uploadForm<T>(url: string, body: FormData, signal?: AbortSignal, onProgress?: (percent: number | null) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", url);
    request.responseType = "json";
    request.upload.onprogress = (event) => onProgress?.(event.lengthComputable ? Math.round((event.loaded / event.total) * 100) : null);
    request.onerror = () => reject(new Error("Upload failed because the backend could not be reached"));
    request.onabort = () => reject(new DOMException("Upload aborted", "AbortError"));
    request.onload = () => {
      const payload = request.response ?? {};
      if (request.status < 200 || request.status >= 300) {
        reject(new Error(payload.detail ?? `Upload failed with status ${request.status}`));
        return;
      }
      onProgress?.(100);
      resolve(payload as T);
    };
    const abort = () => request.abort();
    signal?.addEventListener("abort", abort, { once: true });
    request.onloadend = () => signal?.removeEventListener("abort", abort);
    request.send(body);
  });
}

export async function uploadCapture(file: File, signal?: AbortSignal, onProgress?: (percent: number | null) => void): Promise<{ scene_id: string; status: string }> {
  ensureFullModeAllowed("Video capture upload");
  const body = new FormData();
  body.append("video", file, file.name);
  return uploadForm("/api/v1/captures", body, signal, onProgress);
}

export function uploadPhotoSet(files: File[], signal?: AbortSignal, onProgress?: (percent: number | null) => void, overrideNoncritical = false, profile = "auto"): Promise<{ scene_id: string; status: string }> {
  ensureFullModeAllowed("Photo set upload");
  const body = new FormData();
  files.forEach((file) => body.append("photos", file, file.name));
  body.append("override_noncritical", String(overrideNoncritical));
  body.append("profile", profile);
  return uploadForm("/api/v1/captures/photos", body, signal, onProgress);
}

export function uploadSinglePhoto(file: File, signal?: AbortSignal, onProgress?: (percent: number | null) => void, depthExaggeration = 1, profile = "auto"): Promise<{ scene_id: string; status: string }> {
  ensureFullModeAllowed("Single photo upload");
  const body = new FormData();
  body.append("image", file, file.name);
  body.append("depth_exaggeration", String(depthExaggeration));
  body.append("profile", profile);
  return uploadForm("/api/v1/captures/single", body, signal, onProgress);
}

export async function importScenePackage(file: File, signal?: AbortSignal): Promise<SceneSummary> {
  ensureFullModeAllowed("Scene package import");
  const body = new FormData();
  body.append("scene_package", file, file.name);
  const response = await fetch("/api/v1/scenes/import", { method: "POST", body, signal });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail ?? `Scene import failed with status ${response.status}`);
  }
  return response.json() as Promise<SceneSummary>;
}

export async function deleteSceneJob(sceneId: string, signal?: AbortSignal): Promise<void> {
  ensureFullModeAllowed("Scene deletion");
  const response = await fetch(`/api/v1/scenes/${encodeURIComponent(sceneId)}`, { method: "DELETE", signal });
  if (!response.ok && response.status !== 404) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail ?? `Failed to delete scene: ${response.status}`);
  }
}

export async function clearFailedHistory(signal?: AbortSignal): Promise<{ deleted: string[]; count: number }> {
  ensureFullModeAllowed("Clearing job history");
  const response = await fetch("/api/v1/pipeline/jobs/clear-history", { method: "POST", signal });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(payload.detail ?? `Failed to clear history: ${response.status}`);
  }
  return response.json() as Promise<{ deleted: string[]; count: number }>;
}

export async function validateViewerPack(sceneId: string, signal?: AbortSignal): Promise<ViewerPackValidation> {
  if (isShowcaseMode()) {
    const isLoft = sceneId === "scene_synthetic_loft";
    return {
      is_valid: true,
      scene_id: sceneId,
      scene_type: isLoft ? "synthetic_twin" : "colmap_sfm",
      visual_asset_path: isLoft ? "assets/demo-room.gltf" : "reconstruction/colmap/exports/sparse.ply",
      geometry_format: isLoft ? "gltf" : "ply",
      point_count: isLoft ? 640 : 939,
      triangle_count: isLoft ? 120 : 0,
      bounding_box_min: isLoft ? [-8.0, 0.0, -6.0] : [-21.8, -11.8, -5.5],
      bounding_box_max: isLoft ? [8.0, 3.2, 6.0] : [35.2, 13.7, 49.2],
      span: isLoft ? 16.0 : 57.0,
      center: isLoft ? [0.0, 1.6, 0.0] : [6.7, 1.0, 21.8],
      camera_pose_count: isLoft ? 4 : 19,
      errors: [],
      warnings: [],
    };
  }
  return requestJson<ViewerPackValidation>(`/api/v1/scenes/${encodeURIComponent(sceneId)}/validate-viewer-pack`, signal);
}

export async function renameScene(sceneId: string, sceneName: string, signal?: AbortSignal): Promise<SceneSummary> {
  ensureFullModeAllowed("Renaming scene");
  return sendJson<SceneSummary>(`/api/v1/scenes/${encodeURIComponent(sceneId)}/rename`, "PATCH", { scene_name: sceneName }, signal);
}

export function exportSceneUrl(sceneId: string): string {
  return `/api/v1/scenes/${encodeURIComponent(sceneId)}/export`;
}

export async function loadQualityReport(sceneId: string, signal?: AbortSignal): Promise<UnifiedQualityReport | null> {
  if (isShowcaseMode()) return null;
  return requestJson<UnifiedQualityReport>(`/api/v1/scenes/${encodeURIComponent(sceneId)}/quality-report`, signal);
}

export interface SystemDiagnostics {
  platform: {
    system: string;
    release: string;
    machine: string;
    processor: string;
    execution_mode: string;
  };
  memory: {
    total_mb: number;
    available_mb: number;
    load_percent: number;
  };
  models: {
    depth_anything_v2: {
      name: string;
      path: string;
      available: boolean;
      size_mb: number;
      runtime: string;
    };
  };
  colmap: {
    configured_path: string;
    available: boolean;
    mode: string;
  };
  storage: {
    dataset_root: string;
    total_scenes: number;
    total_size_mb: number;
  };
  concurrency: {
    worker_count: number;
    reconstruction_workers: number;
  };
}

export async function loadSystemDiagnostics(signal?: AbortSignal): Promise<SystemDiagnostics> {
  if (isShowcaseMode()) {
    return {
      platform: {
        system: "Cloud Web Client",
        release: "Static Showcase",
        machine: "WebGL 2.0",
        processor: "Client Device",
        execution_mode: "Standalone 3D Showcase (Serverless)",
      },
      memory: { total_mb: 8192, available_mb: 4096, load_percent: 50 },
      models: {
        depth_anything_v2: {
          name: "Depth Anything V2 Small ONNX",
          path: "Pre-computed 2.5D",
          available: true,
          size_mb: 94.5,
          runtime: "CPUExecutionProvider (Exported)",
        },
      },
      colmap: {
        configured_path: "COLMAP 4.2.0 CPU",
        available: true,
        mode: "CPU Sparse Bundle Adjustment (Exported)",
      },
      storage: {
        dataset_root: "showcase",
        total_scenes: 2,
        total_size_mb: 0.07,
      },
      concurrency: {
        worker_count: 0,
        reconstruction_workers: 0,
      },
    };
  }
  return requestJson<SystemDiagnostics>("/api/v1/system/diagnostics", signal);
}

export async function clearCompletedJobs(signal?: AbortSignal): Promise<{ cleared: string[]; count: number }> {
  ensureFullModeAllowed("Clearing completed jobs");
  return sendJson<{ cleared: string[]; count: number }>("/api/v1/pipeline/jobs/clear-completed-jobs", "POST", {}, signal);
}
