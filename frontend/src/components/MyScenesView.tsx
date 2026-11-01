import { useEffect, useState } from "react";
import { deleteSceneJob, exportSceneUrl, renameScene, validateViewerPack } from "../api";
import type { SceneSummary, ViewerPackValidation } from "../types";

export function MyScenesView({
  scenes,
  selectedId,
  onOpenScene,
  onRefreshScenes,
  onImportPackage,
  importingPackage,
}: {
  scenes: SceneSummary[];
  selectedId: string;
  onOpenScene: (sceneId: string) => void;
  onRefreshScenes: () => void;
  onImportPackage: (file: File) => Promise<void>;
  importingPackage: boolean;
}) {
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState<"all" | "single_photo" | "video" | "photo_set">("all");
  const [validations, setValidations] = useState<Record<string, ViewerPackValidation>>({});
  const [renamingScene, setRenamingScene] = useState<SceneSummary | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [deletingScene, setDeletingScene] = useState<SceneSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    scenes.forEach((scene) => {
      validateViewerPack(scene.scene_id, controller.signal)
        .then((v) => setValidations((cur) => ({ ...cur, [scene.scene_id]: v })))
        .catch(() => {});
    });
    return () => controller.abort();
  }, [scenes]);

  const filteredScenes = scenes.filter((scene) => {
    const isSingle = scene.primary_asset_type === "ply_mesh" || scene.scene_name.toLowerCase().includes("single-photo");
    const isVideo = (scene.description?.toLowerCase().includes("video") || scene.asset_types.includes("ply")) && !scene.synthetic_demo && !isSingle;
    const isPhotoSet = !isSingle && !isVideo;

    if (filterType === "single_photo" && !isSingle) return false;
    if (filterType === "video" && !isVideo) return false;
    if (filterType === "photo_set" && !isPhotoSet) return false;

    if (search.trim()) {
      const q = search.trim().toLowerCase();
      return (
        scene.scene_name.toLowerCase().includes(q) ||
        scene.scene_id.toLowerCase().includes(q) ||
        scene.description.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const handleStartRename = (scene: SceneSummary) => {
    setRenamingScene(scene);
    setRenameValue(scene.scene_name);
    setActionError("");
  };

  const handleSaveRename = async () => {
    if (!renamingScene || !renameValue.trim()) return;
    setRenaming(true);
    setActionError("");
    try {
      await renameScene(renamingScene.scene_id, renameValue.trim());
      setRenamingScene(null);
      onRefreshScenes();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to rename scene");
    } finally {
      setRenaming(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deletingScene) return;
    setDeleting(true);
    setActionError("");
    try {
      await deleteSceneJob(deletingScene.scene_id);
      setDeletingScene(null);
      onRefreshScenes();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to delete scene");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="view-container my-scenes-view" data-testid="my-scenes-view">
      {/* Header & Controls */}
      <header className="my-scenes-header">
        <div>
          <span className="eyebrow">Scene Library</span>
          <h2>My Spatial Digital Twins</h2>
          <p>Explore, manage, export, and rename your reconstructed 3D environments.</p>
        </div>

        <div className="my-scenes-actions">
          <label className={`import-btn ${importingPackage ? "busy" : ""}`}>
            {importingPackage ? "Validating package…" : "+ Import .sfscene"}
            <input
              type="file"
              accept=".sfscene,application/zip"
              disabled={importingPackage}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  onImportPackage(file);
                  e.target.value = "";
                }
              }}
            />
          </label>
        </div>
      </header>

      {actionError && (
        <div className="action-error-banner" role="alert">
          <span>⚠ {actionError}</span>
          <button onClick={() => setActionError("")}>×</button>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="scenes-filter-bar">
        <div className="search-box">
          <span className="search-glyph">⌕</span>
          <input
            type="text"
            placeholder="Search by scene name, ID, or keywords…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && <button className="clear-search" onClick={() => setSearch("")}>×</button>}
        </div>

        <div className="filter-chips">
          {(["all", "single_photo", "video", "photo_set"] as const).map((type) => (
            <button
              key={type}
              className={`filter-chip ${filterType === type ? "active" : ""}`}
              onClick={() => setFilterType(type)}
            >
              {type === "all" ? "All Scenes" : type === "single_photo" ? "Single Photo AI" : type === "video" ? "Video SfM" : "Photo Set"}
            </button>
          ))}
        </div>
      </div>

      {/* Scene Grid */}
      {filteredScenes.length === 0 ? (
        <div className="scenes-empty-state">
          <span className="empty-glyph">▦</span>
          <strong>No scenes match your criteria</strong>
          <p>Try clearing your search query or import a SpatialForge scene package.</p>
        </div>
      ) : (
        <div className="scenes-cards-grid">
          {filteredScenes.map((scene) => {
            const val = validations[scene.scene_id];
            const isSingle = scene.primary_asset_type === "ply_mesh" || scene.scene_name.toLowerCase().includes("single-photo");
            const isVideo = (scene.description?.toLowerCase().includes("video") || scene.asset_types.includes("ply")) && !scene.synthetic_demo && !isSingle;
            const typeLabel = isSingle ? "Single-Photo AI" : isVideo ? "Video SfM" : scene.synthetic_demo ? "Demonstration" : "Multi-View";
            const isCurrent = scene.scene_id === selectedId;

            return (
              <article key={scene.scene_id} className={`scene-management-card ${isCurrent ? "active-scene" : ""}`}>
                <div className="card-top-row">
                  <span className={`type-badge ${isSingle ? "single" : isVideo ? "video" : "multiview"}`}>
                    {typeLabel}
                  </span>
                  <span className="status-badge success">✓ Ready</span>
                </div>

                <div className="card-title-block">
                  <h3 className="scene-display-name">{scene.scene_name}</h3>
                  <code className="scene-display-id">{scene.scene_id}</code>
                  {scene.created_at && (
                    <small className="scene-timestamp">
                      Created: {new Date(scene.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
                    </small>
                  )}
                </div>

                {/* Metrics row */}
                <div className="card-metrics-grid">
                  <div className="metric-cell">
                    <span className="label">Points</span>
                    <span className="value">{val ? val.point_count.toLocaleString() : "…"}</span>
                  </div>
                  <div className="metric-cell">
                    <span className="label">Triangles</span>
                    <span className="value">{val && val.triangle_count > 0 ? val.triangle_count.toLocaleString() : "—"}</span>
                  </div>
                  <div className="metric-cell">
                    <span className="label">Cameras</span>
                    <span className="value">{val && val.camera_pose_count > 0 ? val.camera_pose_count : "1 (Mono)"}</span>
                  </div>
                  <div className="metric-cell">
                    <span className="label">Span</span>
                    <span className="value">{val ? `${val.span.toFixed(1)} u` : "—"}</span>
                  </div>
                </div>

                {/* Primary Action Button */}
                <div className="card-primary-action">
                  <button
                    className="open-in-viewer-button"
                    onClick={() => onOpenScene(scene.scene_id)}
                    title="Open this digital twin in 3D Viewer 2.0"
                  >
                    ◈ Open in Viewer
                  </button>
                </div>

                {/* Management Action Bar */}
                <div className="card-management-toolbar">
                  <button
                    className="mgmt-btn"
                    onClick={() => handleStartRename(scene)}
                    title="Rename this scene"
                  >
                    ✎ Rename
                  </button>
                  <a
                    className="mgmt-btn export-link"
                    href={exportSceneUrl(scene.scene_id)}
                    download={`${scene.scene_id}.sfscene`}
                    title="Download standalone .sfscene package"
                  >
                    ⤓ Export
                  </a>
                  <button
                    className="mgmt-btn danger"
                    onClick={() => setDeletingScene(scene)}
                    title="Delete this scene"
                  >
                    🗑 Delete
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {/* Rename Dialog Modal */}
      {renamingScene && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) setRenamingScene(null); }}>
          <div className="dialog-box" role="dialog" aria-modal="true" aria-labelledby="rename-title">
            <h3 id="rename-title">Rename Digital Twin</h3>
            <p>Update the user-friendly display name for <code>{renamingScene.scene_id}</code>.</p>
            <input
              type="text"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              placeholder="Enter new scene name"
              autoFocus
            />
            <div className="dialog-actions">
              <button className="btn-cancel" onClick={() => setRenamingScene(null)} disabled={renaming}>
                Cancel
              </button>
              <button className="btn-confirm" onClick={handleSaveRename} disabled={renaming || !renameValue.trim()}>
                {renaming ? "Saving…" : "Save Name"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deletingScene && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) setDeletingScene(null); }}>
          <div className="dialog-box danger-box" role="dialog" aria-modal="true" aria-labelledby="delete-title">
            <h3 id="delete-title">Delete Reconstructed Scene</h3>
            <p>
              Are you sure you want to permanently delete <strong>{deletingScene.scene_name}</strong> (<code>{deletingScene.scene_id}</code>)?
            </p>
            <small style={{ color: "#f87171", display: "block", marginBottom: "1rem" }}>
              This will remove all generated 3D meshes, point clouds, and manifests from disk. Uploaded source footage in other directories is preserved.
            </small>
            <div className="dialog-actions">
              <button className="btn-cancel" onClick={() => setDeletingScene(null)} disabled={deleting}>
                Cancel
              </button>
              <button className="btn-danger" onClick={handleConfirmDelete} disabled={deleting}>
                {deleting ? "Deleting…" : "Permanently Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
