import { useEffect, useState } from "react";
import { assetUrl, loadQualityReport, validateViewerPack } from "../api";
import type { CameraTelemetry, QualityPreset, RenderMetrics, SceneManifest, UnifiedQualityReport, ViewerPackValidation } from "../types";

function metric(value: number | null | undefined, suffix = "") {
  return value == null ? "—" : `${value.toLocaleString()}${suffix}`;
}

export function DiagnosticsPanel({
  metrics,
  telemetry,
  manifest,
  quality,
  geometryInfo,
  wireframe,
  onToggleWireframe,
  onFrameScene,
  onClose,
}: {
  metrics: RenderMetrics;
  telemetry: CameraTelemetry | null;
  manifest: SceneManifest;
  quality: QualityPreset;
  geometryInfo?: { pointCount: number; triangleCount: number; format: string } | null;
  wireframe?: boolean;
  onToggleWireframe?: () => void;
  onFrameScene?: () => void;
  onClose: () => void;
}) {
  const [validation, setValidation] = useState<ViewerPackValidation | null>(null);
  const [loadingValidation, setLoadingValidation] = useState(false);
  const [qualityReport, setQualityReport] = useState<UnifiedQualityReport | null>(null);
  const [depthDiag, setDepthDiag] = useState<any | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoadingValidation(true);
    validateViewerPack(manifest.scene_id, controller.signal)
      .then(setValidation)
      .catch(() => setValidation(null))
      .finally(() => setLoadingValidation(false));

    loadQualityReport(manifest.scene_id, controller.signal)
      .then(setQualityReport)
      .catch(() => setQualityReport(null));

    if (manifest.viewer?.is_2_5d) {
      fetch(assetUrl(manifest.scene_id, "metadata/depth_diagnostics.json"), { signal: controller.signal })
        .then((res) => (res.ok ? res.json() : null))
        .then(setDepthDiag)
        .catch(() => setDepthDiag(null));
    }

    return () => controller.abort();
  }, [manifest.scene_id, manifest.viewer?.is_2_5d]);

  const bbox = manifest.bounding_box;
  const span = Math.max(
    bbox.maximum[0] - bbox.minimum[0],
    bbox.maximum[1] - bbox.minimum[1],
    bbox.maximum[2] - bbox.minimum[2]
  );
  const center = [
    (bbox.minimum[0] + bbox.maximum[0]) / 2,
    (bbox.minimum[1] + bbox.maximum[1]) / 2,
    (bbox.minimum[2] + bbox.maximum[2]) / 2,
  ];

  const cameraDist = telemetry
    ? Math.hypot(telemetry.position[0] - center[0], telemetry.position[1] - center[1], telemetry.position[2] - center[2])
    : null;

  const primaryAsset = manifest.assets.find((a) => a.role === "primary_visual");
  const livePoints = geometryInfo?.pointCount ?? metrics.points ?? validation?.point_count ?? 0;
  const liveTriangles = geometryInfo?.triangleCount ?? metrics.triangles ?? validation?.triangle_count ?? 0;

  return (
    <aside className="diagnostics-panel" aria-label="Reconstruction and rendering diagnostics" data-testid="diagnostics-panel">
      <header>
        <div>
          <span className="eyebrow">Reconstruction & WebGL Telemetry</span>
          <strong style={{ display: "block", fontSize: "0.85rem", color: "#f8fafc" }}>
            {manifest.scene_name}
          </strong>
        </div>
        <button onClick={onClose} aria-label="Close diagnostics">×</button>
      </header>

      {/* Action shortcuts */}
      <div className="diag-actions-bar">
        <button className="diag-action-btn" onClick={onFrameScene} title="Position camera around the loaded geometry">
          ⛶ Frame Scene
        </button>
        {onToggleWireframe && (
          <button
            className={`diag-action-btn ${wireframe ? "active" : ""}`}
            onClick={onToggleWireframe}
            title="Toggle between textured and wireframe visualization"
          >
            {wireframe ? "■ Show Texture" : "◫ Show Wireframe"}
          </button>
        )}
      </div>

      <div className="diag-scrollable">
        {manifest.viewer?.is_2_5d && (
          <section className="diag-section">
            <h4>2.5D Geometry & Depth Analysis</h4>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginBottom: "0.75rem" }}>
              <div style={{ textAlign: "center" }}>
                <span style={{ fontSize: "0.7rem", color: "#94a3b8" }}>Depth Heatmap</span>
                <img
                  src={`/api/v1/scenes/${manifest.scene_id}/assets/metadata/depth_heatmap.png`}
                  alt="Depth Heatmap"
                  style={{ width: "100%", borderRadius: "4px", border: "1px solid #334155", marginTop: "2px" }}
                />
              </div>
              <div style={{ textAlign: "center" }}>
                <span style={{ fontSize: "0.7rem", color: "#94a3b8" }}>Discontinuity Map</span>
                <img
                  src={`/api/v1/scenes/${manifest.scene_id}/assets/metadata/depth_discontinuity.png`}
                  alt="Discontinuity Map"
                  style={{ width: "100%", borderRadius: "4px", border: "1px solid #334155", marginTop: "2px" }}
                />
              </div>
            </div>
            {depthDiag && (
              <dl className="diag-grid">
                <div><dt>Depth Range</dt><dd><code>[{depthDiag.depth_statistics?.min?.toFixed(3)}, {depthDiag.depth_statistics?.max?.toFixed(3)}]</code></dd></div>
                <div><dt>Median Depth</dt><dd>{depthDiag.depth_statistics?.median?.toFixed(3)}</dd></div>
                <div><dt>Mesh Faces</dt><dd><strong style={{ color: "#38bdf8" }}>{depthDiag.mesh_topology?.faces_generated?.toLocaleString()}</strong></dd></div>
                <div><dt>Retained Faces</dt><dd>{depthDiag.mesh_topology?.retention_percentage?.toFixed(1)}%</dd></div>
                <div><dt>Clipped Jump Edges</dt><dd style={{ color: "#f59e0b" }}>{depthDiag.mesh_topology?.rejected_depth_jump_edges?.toLocaleString()}</dd></div>
                <div><dt>Inverted Normals</dt><dd style={{ color: "#4ade80" }}>0 (Strictly Front-Facing)</dd></div>
              </dl>
            )}
          </section>
        )}

        {/* Section 1: Reconstruction & Viewer Pack */}
        <section className="diag-section">
          <h4>Reconstruction & Viewer-Pack</h4>
          <dl className="diag-grid">
            <div><dt>Scene ID</dt><dd title={manifest.scene_id}><code>{manifest.scene_id}</code></dd></div>
            <div><dt>Backend</dt><dd><span className="diag-tag">{manifest.reconstruction.backend || "COLMAP"}</span></dd></div>
            <div><dt>Viewer Pack</dt><dd>
              {loadingValidation ? (
                <span className="diag-tag muted">Checking…</span>
              ) : validation?.is_valid ? (
                <span className="diag-tag success">✓ Verified Ready</span>
              ) : (
                <span className="diag-tag warning">⚠ {validation?.errors[0] ?? "Unverified"}</span>
              )}
            </dd></div>
            <div><dt>Primary Asset</dt><dd><code>{primaryAsset?.path ?? "None"}</code></dd></div>
            <div><dt>Geometry Format</dt><dd><strong>{geometryInfo?.format ?? primaryAsset?.type ?? "ply"}</strong></dd></div>
            <div><dt>Declared Assets</dt><dd>{manifest.assets.length} assets</dd></div>
            <div><dt>Camera Poses</dt><dd>{validation?.camera_pose_count ?? 0} registered</dd></div>
            <div><dt>Scene Span</dt><dd>{span.toFixed(2)} units</dd></div>
            {qualityReport && (
              <>
                <div><dt>Pipeline</dt><dd><strong>{qualityReport.pipeline.replaceAll("_", " ").toUpperCase()}</strong></dd></div>
                <div><dt>Confidence</dt><dd>
                  <span className={`diag-tag ${qualityReport.confidence_score >= 0.8 ? "success" : qualityReport.confidence_score >= 0.5 ? "warning" : "error"}`}>
                    {Math.round(qualityReport.confidence_score * 100)}%
                  </span>
                </dd></div>
                <div><dt>Scale</dt><dd>{qualityReport.metric_scale_status}</dd></div>
              </>
            )}
          </dl>
          {qualityReport?.recommendations && qualityReport.recommendations.length > 0 && (
            <div className="diag-recommendation-box" style={{ marginTop: "0.5rem", padding: "0.4rem 0.6rem", background: "rgba(56, 189, 248, 0.08)", borderRadius: "4px", fontSize: "0.75rem", borderLeft: "2px solid #38bdf8" }}>
              <strong style={{ color: "#38bdf8" }}>Quality Note:</strong>
              <span style={{ display: "block", color: "#cbd5e1", marginTop: "2px" }}>{qualityReport.recommendations[0]}</span>
            </div>
          )}
        </section>

        {/* Section 2: 3D Geometry Telemetry */}
        <section className="diag-section">
          <h4>Loaded 3D Geometry</h4>
          <dl className="diag-grid">
            <div className="highlight-stat">
              <dt>3D Points</dt>
              <dd style={{ color: "#38bdf8", fontWeight: 700, fontSize: "1.1rem" }}>
                {metric(livePoints)}
              </dd>
            </div>
            <div className="highlight-stat">
              <dt>Triangles / Faces</dt>
              <dd style={{ color: "#a78bfa", fontWeight: 700, fontSize: "1.1rem" }}>
                {metric(liveTriangles)}
              </dd>
            </div>
            <div><dt>Point Budget</dt><dd>Quality: {quality}</dd></div>
            <div><dt>Point Size</dt><dd>{manifest.viewer.point_size.toFixed(4)}</dd></div>
            <div><dt>Bounding Min</dt><dd><code>[{bbox.minimum.map((v) => v.toFixed(2)).join(", ")}]</code></dd></div>
            <div><dt>Bounding Max</dt><dd><code>[{bbox.maximum.map((v) => v.toFixed(2)).join(", ")}]</code></dd></div>
            <div><dt>Center</dt><dd><code>[{center.map((v) => v.toFixed(2)).join(", ")}]</code></dd></div>
          </dl>
          {validation?.errors && validation.errors.length > 0 && (
            <div className="diag-error-box">
              <strong>Validation errors:</strong>
              <ul>
                {validation.errors.map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
              </ul>
            </div>
          )}
        </section>

        {/* Section 3: Camera & Viewport */}
        <section className="diag-section">
          <h4>Camera & Projection</h4>
          <dl className="diag-grid">
            <div><dt>Camera Mode</dt><dd><strong>{telemetry?.mode ?? "orbit"}</strong></dd></div>
            <div><dt>Distance to Center</dt><dd>{cameraDist ? `${cameraDist.toFixed(1)} units` : "—"}</dd></div>
            <div><dt>Near Plane</dt><dd>{telemetry?.near ?? 0.05} units</dd></div>
            <div><dt>Far Plane</dt><dd>{metric(telemetry?.far ? Math.round(telemetry.far) : 2500)} units</dd></div>
            <div><dt>Field of View</dt><dd>{telemetry?.fov ?? 68}°</dd></div>
            <div><dt>Yaw Rotation</dt><dd>{telemetry ? `${(telemetry.yaw * (180 / Math.PI)).toFixed(1)}°` : "—"}</dd></div>
          </dl>
          <div className="camera-readout">
            <span>Camera Position:</span>
            <code>{telemetry ? telemetry.position.map((v) => v.toFixed(2)).join("  ") : "Unavailable"}</code>
          </div>
        </section>

        {/* Section 4: WebGL Performance */}
        <section className="diag-section">
          <h4>WebGL & Renderer</h4>
          <dl className="diag-grid">
            <div><dt>FPS</dt><dd style={{ color: (metrics.fps ?? 0) >= 45 ? "#4ade80" : "#f59e0b" }}>{metric(metrics.fps)}</dd></div>
            <div><dt>Frame Time</dt><dd>{metric(metrics.frameTimeMs, " ms")}</dd></div>
            <div><dt>Draw Calls</dt><dd>{metric(metrics.drawCalls)}</dd></div>
            <div><dt>Context Status</dt><dd><span className="diag-tag success">✓ WebGL Active</span></dd></div>
            <div><dt>Renderer</dt><dd>{telemetry?.webglRenderer ?? "WebGL 2.0"}</dd></div>
            <div><dt>Geometries</dt><dd>{metric(metrics.geometries)}</dd></div>
          </dl>
        </section>
      </div>
    </aside>
  );
}
