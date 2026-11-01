import { useEffect, useState } from "react";
import { isShowcaseMode, validateViewerPack } from "../api";
import type { PipelineJob, SceneSummary, ViewerPackValidation } from "../types";

export function DashboardView({
  scenes,
  activeJob,
  onOpenScene,
  onStartCapture,
  onNavigateTab,
}: {
  scenes: SceneSummary[];
  activeJob?: { scene_id: string; status: string; current_stage: string; capture_mode?: string | null } | null;
  onOpenScene: (sceneId: string) => void;
  onStartCapture: (mode: "photo_set" | "video" | "single_photo") => void;
  onNavigateTab: (tab: "dashboard" | "create" | "scenes" | "processing" | "settings" | "viewer") => void;
}) {
  const [validations, setValidations] = useState<Record<string, ViewerPackValidation>>({});
  const isShowcase = isShowcaseMode();

  useEffect(() => {
    const controller = new AbortController();
    const recent = scenes.slice(0, 6);
    recent.forEach((scene) => {
      validateViewerPack(scene.scene_id, controller.signal)
        .then((v) => setValidations((cur) => ({ ...cur, [scene.scene_id]: v })))
        .catch(() => {});
    });
    return () => controller.abort();
  }, [scenes]);

  const recentScenes = scenes.slice(0, 6);

  return (
    <div className="view-container dashboard-view" data-testid="dashboard-view">
      {/* Hero Header */}
      <section className="dashboard-hero">
        <div className="dashboard-hero-copy">
          <span className="eyebrow">Spatial Reconstruction Studio</span>
          <h2>Reconstruct Real Spaces into Interactive 3D Digital Twins</h2>
          <p>
            Transform single photos, overlapping photo sets, or video footage into verified 3D geometry
            engineered for Intel integrated graphics and local CPU execution.
          </p>
        </div>
        <div className="dashboard-hero-actions">
          <button
            className="hero-create-btn"
            onClick={() => onNavigateTab("create")}
            title="Launch capture upload workflow"
          >
            + Create New 3D Scene
          </button>
          <div className={`dashboard-system-pill ${isShowcase ? "showcase-pill" : ""}`}>
            <span className={`status-ping ${isShowcase ? "showcase-ping" : ""}`} />
            <div className="pill-text">
              {isShowcase ? (
                <>
                  <strong>Public Showcase · Read-Only</strong>
                  <small>Cloud WebGL Viewer · Static Geometry</small>
                </>
              ) : (
                <>
                  <strong>System Ready · CPU Execution</strong>
                  <small>Intel Integrated Graphics · 16 GB Headroom</small>
                </>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Showcase Information Banner */}
      {isShowcase && (
        <section className="dashboard-active-job-banner showcase-info-banner">
          <div className="banner-visual">
            <span className="banner-glyph">☁</span>
          </div>
          <div className="banner-info">
            <span className="banner-tag">Public Web Showcase</span>
            <strong>Pre-computed 3D Reconstructions Active</strong>
            <small>
              Live photogrammetry and video reconstruction require the local desktop engine with COLMAP 4.2+ and Depth Anything V2.
              Judges can explore genuine reconstructed 3D point clouds and camera trajectories below.
            </small>
          </div>
          <button className="banner-action-btn" onClick={() => onNavigateTab("viewer")}>
            Open 3D Viewer 2.0 →
          </button>
        </section>
      )}

      {/* Active Processing Alert Banner if running */}
      {activeJob && (
        <section className="dashboard-active-job-banner">
          <div className="banner-visual">
            <span className="radar-ping-ring" />
            <span className="banner-glyph">◈</span>
          </div>
          <div className="banner-info">
            <span className="banner-tag">Reconstruction in Progress</span>
            <strong>{activeJob.scene_id}</strong>
            <small>Current stage: {activeJob.current_stage?.replaceAll("_", " ") || "Processing"}</small>
          </div>
          <button className="banner-action-btn" onClick={() => onNavigateTab("processing")}>
            View in Processing Studio →
          </button>
        </section>
      )}

      {/* Section 1: Create New Reconstruction (3 Dedicated Cards) */}
      <section className="dashboard-section">
        <div className="section-header">
          <div>
            <h3>Create a New Reconstruction</h3>
            <p>Select your genuine capture input to launch its specialized reconstruction workflow.</p>
          </div>
        </div>

        <div className="capture-cards-grid">
          {/* Card 1: Photo Set */}
          <article className="workflow-card photo-set-card">
            <div className="card-top">
              <span className="workflow-badge">COLMAP Multi-View</span>
              <span className="workflow-icon">📸</span>
            </div>
            <h4>Photo Set Reconstruction</h4>
            <p>
              Upload overlapping photographs of a room or object. Evaluates camera coverage, SIFT feature
              matches, and solves sparse bundle adjustment.
            </p>
            <ul className="workflow-features">
              <li>✓ Multi-view pairwise overlap evaluation</li>
              <li>✓ SIFT feature matching with CPU bounds</li>
              <li>✓ 3D sparse point cloud & camera poses</li>
            </ul>
            <button className="card-action-btn primary" onClick={() => onStartCapture("photo_set")}>
              Start Photo Set Capture →
            </button>
          </article>

          {/* Card 2: Video */}
          <article className="workflow-card video-card">
            <div className="card-top">
              <span className="workflow-badge">Spatial Motion SfM</span>
              <span className="workflow-icon">🎥</span>
            </div>
            <h4>Video Reconstruction</h4>
            <p>
              Extract and validate keyframes from an MP4 or MOV video. Filters motion blur, assesses trajectory
              continuity, and reconstructs 3D spatial points.
            </p>
            <ul className="workflow-features">
              <li>✓ Automated 2 FPS keyframe extraction</li>
              <li>✓ Motion blur & redundancy filtering</li>
              <li>✓ Validated 3D viewer pack packaging</li>
            </ul>
            <button className="card-action-btn primary" onClick={() => onStartCapture("video")}>
              Start Video Capture →
            </button>
          </article>

          {/* Card 3: Single Photo */}
          <article className="workflow-card single-photo-card">
            <div className="card-top">
              <span className="workflow-badge">Depth Anything V2</span>
              <span className="workflow-icon">🖼️</span>
            </div>
            <h4>Single-Photo AI Reconstruction</h4>
            <p>
              Predict neural monocular relative depth and triangulate an edge-aware 3D textured mesh from a single
              photograph. Fast local CPU inference (~15–20s).
            </p>
            <ul className="workflow-features">
              <li>✓ Aspect-ratio preserving inference (no squishing)</li>
              <li>✓ Bilateral edge-aware step discontinuity filter</li>
              <li>✓ Interactive textured 3D mesh preview</li>
            </ul>
            <button className="card-action-btn primary" onClick={() => onStartCapture("single_photo")}>
              Start Single-Photo Capture →
            </button>
          </article>
        </div>
      </section>

      {/* Section 2: Recent Scenes */}
      <section className="dashboard-section">
        <div className="section-header">
          <div>
            <h3>Recent Digital Twins</h3>
            <p>Validated 3D spatial reconstructions ready for immediate exploration in Viewer 2.0.</p>
          </div>
          <button className="section-link-btn" onClick={() => onNavigateTab("scenes")}>
            View All ({scenes.length}) Scenes →
          </button>
        </div>

        {recentScenes.length === 0 ? (
          <div className="dashboard-empty-card">
            <strong>No reconstructed scenes yet</strong>
            <p>Use one of the capture methods above to create your first genuine 3D spatial digital twin.</p>
          </div>
        ) : (
          <div className="recent-scenes-grid">
            {recentScenes.map((scene) => {
              const val = validations[scene.scene_id];
              const assetTypes = scene.asset_types ?? [];
              const isVideo = (scene.description?.toLowerCase().includes("video") || assetTypes.includes("ply")) && !scene.synthetic_demo && scene.primary_asset_type !== "ply_mesh";
              const isSingle = scene.primary_asset_type === "ply_mesh" || scene.scene_name.toLowerCase().includes("single-photo");
              const typeLabel = isSingle ? "Single-Photo AI" : isVideo ? "Video SfM" : scene.synthetic_demo ? "Demonstration" : "Multi-View";

              return (
                <article key={scene.scene_id} className="recent-scene-card">
                  <div className="scene-card-header">
                    <span className={`scene-type-tag ${isSingle ? "single" : isVideo ? "video" : "multiview"}`}>
                      {typeLabel}
                    </span>
                    <span className="scene-status-tag success">✓ Ready</span>
                  </div>

                  <div className="scene-card-body">
                    <strong className="scene-title">{scene.scene_name}</strong>
                    <code className="scene-id">{scene.scene_id}</code>

                    <div className="scene-metrics-chips">
                      <span className="metric-chip">
                        <i>Points:</i> {val ? val.point_count.toLocaleString() : "…"}
                      </span>
                      {val && val.triangle_count > 0 && (
                        <span className="metric-chip">
                          <i>Triangles:</i> {val.triangle_count.toLocaleString()}
                        </span>
                      )}
                      {val && val.camera_pose_count > 0 && (
                        <span className="metric-chip">
                          <i>Cameras:</i> {val.camera_pose_count}
                        </span>
                      )}
                      {val && (
                        <span className="metric-chip">
                          <i>Span:</i> {val.span.toFixed(1)} u
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="scene-card-footer">
                    <button
                      className="open-viewer-btn"
                      onClick={() => onOpenScene(scene.scene_id)}
                      title="Open and explore this scene in 3D Viewer 2.0"
                    >
                      ◈ Open in Viewer
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
