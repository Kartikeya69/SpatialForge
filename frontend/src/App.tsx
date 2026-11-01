import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPoi, createRoute, importScenePackage, listPipelineJobs, listScenes, loadColliders, loadManifest, loadNavigationGrid, searchPois } from "./api";
import { DiagnosticsPanel } from "./components/DiagnosticsPanel";
import { ViewerErrorBoundary, supportsWebGL } from "./components/ErrorBoundary";
import { HelpDialog } from "./components/HelpDialog";
import { Minimap } from "./components/Minimap";
import { SceneDetails } from "./components/SceneDetails";
import { SceneLibrary } from "./components/SceneLibrary";
import { NavigationSearch } from "./components/NavigationSearch";
import { PoiAuthorDialog } from "./components/PoiAuthorDialog";
import { RouteStatus } from "./components/RouteStatus";
import { ProcessingDashboard } from "./components/ProcessingDashboard";
import { CreateWorkflowView } from "./components/CreateWorkflowView";
import { DashboardView } from "./components/DashboardView";
import { MyScenesView } from "./components/MyScenesView";
import { SettingsView } from "./components/SettingsView";
import { validateSceneManifest } from "./manifest";
import { hasArrived, routeProgress, shouldRecomputeRoute } from "./navigation";
import type { CameraMode, CameraTelemetry, ColliderDocument, NavigationGrid, POI, QualityPreset, RenderMetrics, RouteResult, SceneManifest, SceneSummary } from "./types";
import type { ControlMode } from "./viewer/FirstPersonController";

const SceneViewport = lazy(() => import("./viewer/SceneViewport"));
const EMPTY_METRICS: RenderMetrics = { fps: null, frameTimeMs: null, drawCalls: null, triangles: null, points: null };
type AppTab = "dashboard" | "create" | "scenes" | "processing" | "settings" | "viewer";

export default function App() {
  const [activeTab, setActiveTab] = useState<AppTab>("viewer");
  const [captureWorkflowMode, setCaptureWorkflowMode] = useState<"photo_set" | "video" | "single_photo">("photo_set");
  const [scenes, setScenes] = useState<SceneSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [manifest, setManifest] = useState<SceneManifest | null>(null);
  const [colliders, setColliders] = useState<ColliderDocument | null>(null);
  const [navigationGrid, setNavigationGrid] = useState<NavigationGrid | null>(null);
  const [pois, setPois] = useState<POI[]>([]);
  const [poiError, setPoiError] = useState<string | null>(null);
  const [loadingPois, setLoadingPois] = useState(false);
  const [destination, setDestination] = useState<POI | null>(null);
  const [route, setRoute] = useState<RouteResult | null>(null);
  const [routeState, setRouteState] = useState<"routing" | "active" | "arrived" | "error">("active");
  const [showPoiAuthor, setShowPoiAuthor] = useState(false);
  const [showProcessing, setShowProcessing] = useState(false);
  const [loadingScenes, setLoadingScenes] = useState(true);
  const [importingPackage, setImportingPackage] = useState(false);
  const [loadingScene, setLoadingScene] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [showTrajectory, setShowTrajectory] = useState(false);
  const [wireframe, setWireframe] = useState(false);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [movementSpeed, setMovementSpeed] = useState(2.5);
  const [mouseSensitivity, setMouseSensitivity] = useState(0.0022);
  const [smoothing, setSmoothing] = useState(true);
  const [quality, setQuality] = useState<QualityPreset>("balanced");
  const [cameraMode, setCameraMode] = useState<CameraMode>("first-person");
  const [resetToken, setResetToken] = useState(0);
  const [frameSceneToken, setFrameSceneToken] = useState(0);
  const [geometryInfo, setGeometryInfo] = useState<{ pointCount: number; triangleCount: number; format: string } | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [discoveryToken, setDiscoveryToken] = useState(0);
  const [teleport, setTeleport] = useState<{ x: number; z: number; token: number } | null>(null);
  const [controlMode, setControlMode] = useState<ControlMode>("idle");
  const [telemetry, setTelemetry] = useState<CameraTelemetry | null>(null);
  const [metrics, setMetrics] = useState<RenderMetrics>(EMPTY_METRICS);
  const [webglAvailable] = useState(supportsWebGL);
  const [activePipelineJob, setActivePipelineJob] = useState<{ scene_id: string; current_stage: string; capture_mode?: string | null } | null>(null);
  const requestSequence = useRef(0);
  const routeComputedAt = useRef(0);
  const routeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    let mounted = true;
    const poll = async () => {
      try {
        const jobs = await listPipelineJobs();
        if (!mounted) return;
        const running = jobs.find((j) =>
          ["queued", "processing", "cancelling"].includes(j.status) ||
          j.stages.some((s) => s.status === "processing")
        );
        if (running) {
          setActivePipelineJob({
            scene_id: running.scene_id,
            current_stage: running.current_stage || "processing",
            capture_mode: running.capture_mode,
          });
        } else {
          setActivePipelineJob((prev) => {
            if (prev) {
              setDiscoveryToken((v) => v + 1);
              setSelectedId(prev.scene_id);
            }
            return null;
          });
        }
      } catch {
        // ignore polling errors
      }
    };
    poll();
    const interval = setInterval(poll, 2000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoadingScenes(true);
    listScenes(controller.signal)
      .then((availableScenes) => {
        setError(null);
        setScenes(availableScenes);
        setSelectedId((current) => {
          if (!current) return availableScenes[0]?.scene_id || "";
          if (availableScenes.some((scene) => scene.scene_id === current)) return current;
          // Never silently fall back to availableScenes[0] when an explicit scene is selected
          return current;
        });
      })
      .catch((reason: Error) => { if (reason.name !== "AbortError") setError(reason.message); })
      .finally(() => { if (!controller.signal.aborted) setLoadingScenes(false); });
    return () => controller.abort();
  }, [discoveryToken]);

  useEffect(() => {
    if (!selectedId) return;
    const requestId = ++requestSequence.current;
    const controller = new AbortController();
    setLoadingScene(true);
    setError(null);
    setManifest(null);
    setColliders(null);
    setNavigationGrid(null);
    setPois([]);
    setDestination(null);
    setRoute(null);
    setTelemetry(null);
    setMetrics(EMPTY_METRICS);
    setGeometryInfo(null);
    setSelectedAssetId(null);
    setShowDetails(false);
    setCameraMode("orbit");
    loadManifest(selectedId, controller.signal)
      .then(async (document) => {
        const nextManifest = validateSceneManifest(document);
        const [colliderDocument, gridDocument] = await Promise.all([
          loadColliders(selectedId, nextManifest, controller.signal),
          loadNavigationGrid(selectedId, nextManifest, controller.signal),
        ]);
        if (requestSequence.current !== requestId) return;
        setManifest(nextManifest);
        setColliders(colliderDocument);
        setNavigationGrid(gridDocument);
        setMovementSpeed(nextManifest.navigation.movement_speed);
        setCameraMode(nextManifest.viewer?.is_2_5d ? "orbit" : nextManifest.navigation.enabled ? "first-person" : "orbit");
        const preferred = nextManifest.assets.find((asset) => asset.role === "primary_visual" && ["glb", "gltf", "ply", "ply_mesh"].includes(asset.type));
        setSelectedAssetId(preferred?.id ?? null);
      })
      .catch((reason: Error) => {
        if (reason.name !== "AbortError" && requestSequence.current === requestId) setError(reason.message);
      })
      .finally(() => { if (requestSequence.current === requestId) setLoadingScene(false); });
    return () => controller.abort();
  }, [selectedId, retryToken]);

  useEffect(() => {
    if (!manifest || !manifest.navigation?.enabled) {
      setPois([]);
      return;
    }
    const controller = new AbortController();
    setLoadingPois(true); setPoiError(null);
    searchPois(manifest.scene_id, "", controller.signal)
      .then(setPois)
      .catch((reason: Error) => { if (reason.name !== "AbortError") setPoiError(reason.message); })
      .finally(() => { if (!controller.signal.aborted) setLoadingPois(false); });
    return () => controller.abort();
  }, [manifest]);

  const requestRoute = useCallback((poi: POI, position = telemetry?.position ?? manifest?.navigation.spawn_position) => {
    if (!manifest || !position || !navigationGrid) { setPoiError("This scene does not provide routable navigation data."); return; }
    routeRequest.current?.abort();
    const controller = new AbortController();
    routeRequest.current = controller;
    setDestination(poi); setRouteState("routing"); setPoiError(null);
    createRoute(manifest.scene_id, position, poi.id, controller.signal)
      .then((result) => { setRoute(result); setRouteState("active"); routeComputedAt.current = performance.now(); })
      .catch((reason: Error) => { if (reason.name !== "AbortError") { setRoute(null); setRouteState("error"); setPoiError(reason.message); } });
  }, [manifest, navigationGrid, telemetry?.position]);

  useEffect(() => {
    if (!telemetry || !route || !destination || routeState !== "active") return;
    if (hasArrived(telemetry.position, route)) { setRouteState("arrived"); return; }
    const now = performance.now();
    if (shouldRecomputeRoute(telemetry.position, route, routeComputedAt.current, now)) requestRoute(destination, telemetry.position);
  }, [telemetry, route, destination, routeState, requestRoute]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof Element && target.matches("input, select, textarea, button")) return;
      if (event.key === "?") setShowHelp(true);
      if (event.key === "Escape") { setShowSettings(false); setShowDetails(false); setShowDiagnostics(false); setShowProcessing(false); }
      if (event.code === "KeyR") setResetToken((value) => value + 1);
      if (event.code === "KeyF") setFrameSceneToken((value) => value + 1);
      if (event.code === "Digit1") setCameraMode("first-person");
      if (event.code === "Digit2") setCameraMode("orbit");
      if (event.code === "Digit3") setCameraMode("overview");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const onTelemetry = useCallback((next: CameraTelemetry) => setTelemetry(next), []);
  const onMetrics = useCallback((next: RenderMetrics) => setMetrics(next), []);
  const unsupported = useMemo(() => manifest?.assets.filter((asset) => asset.type === "gaussian_splat") ?? [], [manifest]);
  const representations = useMemo(() => manifest?.assets.filter((asset) => ["glb", "gltf", "ply", "ply_mesh"].includes(asset.type)) ?? [], [manifest]);
  const compassDegrees = telemetry ? ((-telemetry.yaw * 180) / Math.PI + 360) % 360 : 0;
  const progress = telemetry && route ? routeProgress(telemetry.position, route) : 0;
  const cancelRoute = () => { routeRequest.current?.abort(); setDestination(null); setRoute(null); setRouteState("active"); setPoiError(null); };

  const openSceneInViewer = (sceneId: string) => {
    setSelectedId(sceneId);
    setActiveTab("viewer");
    setFrameSceneToken((v) => v + 1);
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="topbar-left">
          <div className="brand" onClick={() => setActiveTab("dashboard")} style={{ cursor: "pointer" }}>
            <div className="brand-mark" aria-hidden="true"><span /></div>
            <div className="brand-copy">
              <strong>SpatialForge</strong>
              <span>3D Reconstruction Studio</span>
            </div>
          </div>

          <nav className="main-nav-tabs" aria-label="Main Navigation">
            <button
              className={`nav-tab-btn ${activeTab === "dashboard" ? "active" : ""}`}
              onClick={() => setActiveTab("dashboard")}
              aria-label="Dashboard"
            >
              <span className="tab-glyph">⊞</span> Dashboard
            </button>
            <button
              className={`nav-tab-btn nav-tab-create ${activeTab === "create" ? "active" : ""}`}
              onClick={() => setActiveTab("create")}
              aria-label="Create Reconstruction"
            >
              <span className="tab-glyph">+</span> Create
            </button>
            <button
              className={`nav-tab-btn ${activeTab === "processing" ? "active" : ""}`}
              onClick={() => setActiveTab("processing")}
              aria-label="Processing Studio"
            >
              <span className="tab-glyph">◫</span> Processing
              {activePipelineJob && <span className="nav-pulse-dot" />}
            </button>
            <button
              className={`nav-tab-btn ${activeTab === "scenes" ? "active" : ""}`}
              onClick={() => setActiveTab("scenes")}
              aria-label="My Scenes"
            >
              <span className="tab-glyph">▤</span> My Scenes
            </button>
            <button
              className={`nav-tab-btn ${activeTab === "settings" ? "active" : ""}`}
              onClick={() => setActiveTab("settings")}
              aria-label="Settings"
            >
              <span className="tab-glyph">⚙</span> Settings
            </button>
            <button
              className={`nav-tab-btn ${activeTab === "viewer" ? "active" : ""}`}
              onClick={() => setActiveTab("viewer")}
              aria-label="3D Viewer"
            >
              <span className="tab-glyph">◈</span> 3D Viewer
            </button>
          </nav>
        </div>

        <div className="topbar-right">
          {scenes.length > 0 && <SceneLibrary scenes={scenes} selectedId={selectedId} onSelect={openSceneInViewer} />}
          {activePipelineJob && (
            <button
              className="topbar-rendering-pill"
              onClick={() => setActiveTab("processing")}
              title="Click to view 3D rendering progress"
              aria-label="3D rendering in progress"
            >
              <span className="pill-pulse-dot" />
              <span>
                <strong>3D Rendering</strong>
                <small>{activePipelineJob.current_stage.replaceAll("_", " ")}</small>
              </span>
            </button>
          )}
          <div className={`system-state ${error ? "error" : ""}`}>
            <span className="status-dot" />
            <span>{error ? "Connection issue" : loadingScenes || loadingScene ? "Loading" : scenes.length === 0 ? "No scenes" : controlMode === "idle" ? "Ready" : "Exploring"}</span>
          </div>
        </div>
      </header>

      <section className="workspace">
        {activeTab === "dashboard" && (
          <DashboardView
            scenes={scenes}
            activeJob={
              activePipelineJob
                ? {
                    scene_id: activePipelineJob.scene_id,
                    status: "processing",
                    current_stage: activePipelineJob.current_stage,
                    capture_mode: activePipelineJob.capture_mode,
                  }
                : null
            }
            onOpenScene={openSceneInViewer}
            onStartCapture={(mode) => {
              setCaptureWorkflowMode(mode);
              setActiveTab("create");
            }}
            onNavigateTab={setActiveTab}
          />
        )}

        {activeTab === "create" && (
          <CreateWorkflowView
            initialMode={captureWorkflowMode}
            onSelectScene={(sceneId) => {
              openSceneInViewer(sceneId);
              setDiscoveryToken((v) => v + 1);
            }}
            onNavigateTab={setActiveTab}
          />
        )}

        {activeTab === "scenes" && (
          <MyScenesView
            scenes={scenes}
            selectedId={selectedId}
            onOpenScene={openSceneInViewer}
            onRefreshScenes={() => setDiscoveryToken((v) => v + 1)}
            onImportPackage={async (file) => {
              setImportingPackage(true);
              setError(null);
              try {
                const imported = await importScenePackage(file);
                setDiscoveryToken((v) => v + 1);
                setSelectedId(imported.scene_id);
                setActiveTab("viewer");
              } catch (reason) {
                setError(reason instanceof Error ? reason.message : "Scene package import failed");
              } finally {
                setImportingPackage(false);
              }
            }}
            importingPackage={importingPackage}
          />
        )}

        {activeTab === "processing" && (
          <ProcessingDashboard
            embedded={true}
            initialMode={captureWorkflowMode}
            onClose={() => setActiveTab("viewer")}
            onSelectScene={(sceneId) => {
              openSceneInViewer(sceneId);
              setDiscoveryToken((v) => v + 1);
            }}
          />
        )}

        {activeTab === "settings" && (
          <SettingsView onRefreshScenes={() => setDiscoveryToken((v) => v + 1)} />
        )}

        {activeTab === "viewer" && (
          <div className="viewer-column">
          <div className="viewport-frame">
            {manifest && (
              <div className="scene-title-card">
                <span className="eyebrow">{manifest.synthetic_demo ? "Demonstration" : "Digital twin"}</span>
                <strong>{manifest.scene_name}</strong>
                <small>{cameraMode.replace("-", " ")} mode · {manifest.units.metric_scale_status} scale</small>
              </div>
            )}

            {manifest && telemetry && (
              <div className="compass" aria-label={`Heading ${Math.round(compassDegrees)} degrees`}>
                <span>N</span><i style={{ transform: `rotate(${compassDegrees}deg)` }} />
              </div>
            )}

            {manifest && (
              <NavigationSearch pois={pois} loading={loadingPois} error={poiError} activePoiId={destination?.id ?? null} onSelect={requestRoute} onAuthor={() => setShowPoiAuthor(true)} />
            )}

            <RouteStatus route={route} destination={destination} progress={progress} status={routeState} onCancel={cancelRoute} />

            {(loadingScenes || loadingScene) && (
              <div className="state-layer" role="status">
                <div className="loader-orbit"><span /><span /></div>
                <strong>{loadingScenes ? "Discovering scene packages" : "Preparing digital twin"}</strong>
                <small>{loadingScenes ? "Reading available scene metadata" : "Loading geometry and navigation data"}</small>
              </div>
            )}

            {error && !loadingScene && (
              <div className="state-layer error-state" role="alert">
                <div className="error-icon">!</div>
                <strong>{selectedId ? "Scene unavailable" : "SpatialForge could not reach the scene service"}</strong>
                <p>{error}</p>
                <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", flexWrap: "wrap", justifyContent: "center" }}>
                  <button onClick={() => selectedId ? setRetryToken((value) => value + 1) : setDiscoveryToken((value) => value + 1)}>Try again</button>
                  {selectedId && (
                    <>
                      <button className="btn-secondary" onClick={() => setActiveTab("processing")}>Check Processing Jobs</button>
                      {scenes.length > 0 && scenes.some((s) => s.scene_id !== selectedId) && (
                        <button className="btn-secondary" onClick={() => setSelectedId(scenes[0]?.scene_id || "")}>Load Available Scene</button>
                      )}
                    </>
                  )}
                </div>
              </div>
            )}

            {!loadingScenes && !error && scenes.length === 0 && (
              <div className="state-layer empty-state" role="status">
                <div className="empty-mark" aria-hidden="true"><span /></div>
                <span className="eyebrow">Real data required</span>
                <strong>No digital twins yet</strong>
                <p>Import smartphone footage to begin capture processing, or open a validated SpatialForge scene package produced by the reconstruction laptop.</p>
                <div className="empty-actions">
                  <button onClick={() => setShowProcessing(true)}>Import footage</button>
                  <label className={importingPackage ? "busy" : ""}>{importingPackage ? "Validating package…" : "Import .sfscene"}<input type="file" accept=".sfscene,application/zip" disabled={importingPackage} onChange={async (event) => {
                    const file = event.target.files?.[0];
                    if (!file) return;
                    setImportingPackage(true); setError(null);
                    try {
                      const imported = await importScenePackage(file);
                      setDiscoveryToken((value) => value + 1);
                      setSelectedId(imported.scene_id);
                    } catch (reason) {
                      setError(reason instanceof Error ? reason.message : "Scene package import failed");
                    } finally {
                      setImportingPackage(false);
                      event.target.value = "";
                    }
                  }} /></label>
                </div>
                <small>Demonstration fixtures are isolated from production discovery.</small>
              </div>
            )}

            {!webglAvailable && !error && (
              <div className="state-layer error-state" role="alert"><div className="error-icon">!</div><strong>WebGL is unavailable</strong><p>Enable hardware acceleration or use a browser with WebGL support.</p></div>
            )}

            {manifest && webglAvailable && !error && (
              <ViewerErrorBoundary resetKey={`${manifest.scene_id}-${retryToken}`} onRetry={() => setRetryToken((value) => value + 1)}>
                <Suspense fallback={<div className="state-layer" role="status"><div className="loader-orbit"><span /><span /></div><strong>Starting 3D renderer</strong><small>Loading the optimized viewer bundle</small></div>}>
                  <SceneViewport
                    key={manifest.scene_id}
                    manifest={manifest}
                    colliderDocument={colliders}
                    movementSpeed={movementSpeed}
                    mouseSensitivity={mouseSensitivity}
                    smoothing={smoothing}
                    cameraMode={cameraMode}
                    quality={quality}
                    resetToken={resetToken}
                    frameSceneToken={frameSceneToken}
                    teleport={teleport}
                    showDiagnostics={showTrajectory}
                    collectMetrics={showDiagnostics}
                    onControlModeChange={setControlMode}
                    onTelemetry={onTelemetry}
                    onMetrics={onMetrics}
                    onLoadedGeometryInfo={setGeometryInfo}
                    route={route}
                    selectedAssetId={selectedAssetId}
                    wireframe={wireframe}
                  />
                </Suspense>
              </ViewerErrorBoundary>
            )}

            {manifest && cameraMode === "first-person" && controlMode !== "locked" && !error && (
              <div className="enter-hint">
                <span className="mouse-glyph" aria-hidden="true" />
                {controlMode === "dragging" ? "Looking around" : controlMode === "free" ? "Mouse look active · Esc to release" : "Click or drag to look"}
              </div>
            )}

            {manifest && !colliders && cameraMode === "first-person" && (
              <div className="collision-notice" role="status">Collision geometry unavailable</div>
            )}
            {unsupported.length > 0 && <div className="format-notice" role="status">Gaussian splat asset not shown by this renderer</div>}

            {manifest && colliders && telemetry && (
              <Minimap manifest={manifest} colliders={colliders} telemetry={telemetry} route={route} pois={pois} onSelectPoi={requestRoute} onReposition={(x, z) => { setCameraMode("first-person"); setTeleport({ x, z, token: Date.now() }); }} />
            )}

            {manifest && showSettings && (
              <section className="settings-popover" aria-label="Viewer settings">
                <header><span className="eyebrow">Viewer settings</span><button onClick={() => setShowSettings(false)} aria-label="Close settings">×</button></header>
                <label><span>Walk speed <output>{movementSpeed.toFixed(1)}×</output></span><input type="range" min="0.8" max="6" step="0.1" value={movementSpeed} onChange={(event) => setMovementSpeed(Number(event.target.value))} /></label>
                <label><span>Look sensitivity <output>{(mouseSensitivity / 0.0022).toFixed(1)}×</output></span><input type="range" min="0.0008" max="0.005" step="0.0001" value={mouseSensitivity} onChange={(event) => setMouseSensitivity(Number(event.target.value))} /></label>
                <label className="select-setting"><span>Rendering quality</span><select aria-label="Rendering quality" value={quality} onChange={(event) => setQuality(event.target.value as QualityPreset)}><option value="low">Low</option><option value="balanced">Balanced</option><option value="high">High</option></select></label>
                {representations.length > 1 && <label className="select-setting"><span>Scene representation</span><select aria-label="Scene representation" value={selectedAssetId ?? ""} onChange={(event) => setSelectedAssetId(event.target.value)}>{representations.map((asset) => <option value={asset.id} key={asset.id}>{asset.id.replaceAll("_", " ")} · {asset.type.toUpperCase()}</option>)}</select></label>}
                <label className="toggle-setting"><input type="checkbox" checked={smoothing} onChange={(event) => setSmoothing(event.target.checked)} /><span>Movement smoothing</span></label>
              </section>
            )}

            {manifest && (
              <nav className="bottom-toolbar" aria-label="Viewer tools">
                <div className="mode-switcher" aria-label="Camera mode">
                  {(["first-person", "orbit", "overview"] as CameraMode[]).map((mode) => (
                    <button key={mode} disabled={mode === "first-person" && !manifest.navigation.enabled} className={cameraMode === mode ? "active" : ""} aria-pressed={cameraMode === mode} onClick={() => setCameraMode(mode)} title={mode === "first-person" && !manifest.navigation.enabled ? "Walk mode requires validated navigation geometry" : `${mode.replace("-", " ")} camera`}>
                      <span aria-hidden="true">{mode === "first-person" ? "◉" : mode === "orbit" ? "◎" : "▦"}</span>{mode === "first-person" ? "Walk" : mode === "orbit" ? "Orbit" : "Overview"}
                    </button>
                  ))}
                </div>
                <i />
                <button onClick={() => setFrameSceneToken((value) => value + 1)} title="Frame Scene (Fit to view, F)" aria-label="Frame Scene">⛶</button>
                <button onClick={() => setResetToken((value) => value + 1)} title="Reset camera (R)" aria-label="Reset camera">↺</button>
                <button className={showSettings ? "active" : ""} onClick={() => setShowSettings((value) => !value)} title="Viewer settings" aria-label="Viewer settings">⚙</button>
                <button className={showTrajectory ? "active" : ""} onClick={() => setShowTrajectory((value) => !value)} title="Toggle camera trajectory" aria-label="Toggle camera trajectory">⌁</button>
                <button className={showDiagnostics ? "active" : ""} onClick={() => setShowDiagnostics((value) => !value)} title="Reconstruction & performance diagnostics" aria-label="Reconstruction & performance diagnostics">▥</button>
                <button onClick={() => setShowProcessing(true)} title="Processing jobs" aria-label="Processing jobs">◫</button>
                <button onClick={() => setShowDetails(true)} title="Scene information" aria-label="Scene information">ⓘ</button>
                <button onClick={() => setShowHelp(true)} title="Keyboard shortcuts (?)" aria-label="Keyboard shortcuts">?</button>
              </nav>
            )}
          </div>
        </div>
        )}

        {manifest && showDetails && <SceneDetails manifest={manifest} onClose={() => setShowDetails(false)} />}
        {manifest && showDiagnostics && (
          <DiagnosticsPanel
            metrics={metrics}
            telemetry={telemetry}
            manifest={manifest}
            quality={quality}
            geometryInfo={geometryInfo}
            wireframe={wireframe}
            onToggleWireframe={() => setWireframe((v) => !v)}
            onFrameScene={() => setFrameSceneToken((value) => value + 1)}
            onClose={() => setShowDiagnostics(false)}
          />
        )}
        {showHelp && <HelpDialog onClose={() => setShowHelp(false)} />}
        {showProcessing && (
          <ProcessingDashboard
            onClose={() => {
              setShowProcessing(false);
              setDiscoveryToken((value) => value + 1);
            }}
            onSelectScene={(sceneId) => {
              setSelectedId(sceneId);
              setDiscoveryToken((value) => value + 1);
              setShowProcessing(false);
            }}
          />
        )}
        {showPoiAuthor && telemetry && manifest && <PoiAuthorDialog position={telemetry.position} onClose={() => setShowPoiAuthor(false)} onSave={async (name, category, aliases) => {
          const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 36) || "place";
          const point: POI = { id: `poi_${slug}-${Date.now().toString(36)}`, name, category, description: "User-authored point of interest.", aliases, position: telemetry.position, arrival_points: [telemetry.position], floor_id: navigationGrid?.floor_id ?? "ground", bounds: null, zone: null };
          const saved = await createPoi(manifest.scene_id, point);
          setPois((current) => [...current, saved].sort((a, b) => a.name.localeCompare(b.name)));
        }} />}
      </section>
    </main>
  );
}
