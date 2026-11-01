import { useEffect, useState, type DragEvent } from "react";
import {
  analyzePipelineCapture,
  cancelCapture,
  clearFailedHistory,
  deleteSceneJob,
  isShowcaseMode,
  listPipelineJobs,
  startReconstruction,
  uploadCapture,
  uploadPhotoSet,
  uploadSinglePhoto,
} from "../api";
import type { PipelineJob } from "../types";

type CaptureMode = "photo_set" | "video" | "single_photo";
const label = (value: string) => value.replaceAll("_", " ");

const modeCopy: Record<CaptureMode, { title: string; detail: string; accept: string; multiple: boolean }> = {
  photo_set: { title: "Photo set", detail: "Overlapping photographs for COLMAP", accept: ".jpg,.jpeg,.png,.heic,.heif,image/jpeg,image/png", multiple: true },
  video: { title: "Video", detail: "Extract and validate ordered frames", accept: ".mp4,.mov,.m4v,.mkv,.webm,video/mp4,video/quicktime,video/webm", multiple: false },
  single_photo: { title: "Single photo", detail: "AI-estimated non-metric 2.5D preview", accept: ".jpg,.jpeg,.png,.heic,.heif,image/jpeg,image/png", multiple: false },
};

const modeHighlights: Record<CaptureMode, { badge: string; items: string[] }> = {
  photo_set: {
    badge: "COLMAP Multi-View Photogrammetry",
    items: [
      "Multi-View Overlap Evaluation",
      "SIFT Feature Matching & Verification",
      "Sparse Bundle Adjustment (CPU)",
      "3D Point Cloud & Camera Trajectory",
    ],
  },
  video: {
    badge: "Video Spatial Motion Reconstruction",
    items: [
      "Automated 2 FPS Keyframe Sampling",
      "Motion Blur & Redundancy Filtering",
      "Guided Overlap Analysis & COLMAP Matching",
      "Automated 3D Digital Twin Assembly",
    ],
  },
  single_photo: {
    badge: "AI 2.5D Monocular Depth (Depth Anything V2)",
    items: [
      "Neural Monocular Depth Estimation",
      "Interactive 3D Textured Surface Mesh",
      "Fast Local CPU Generation (~15–20s)",
      "Direct 3D Viewport Exploration",
    ],
  },
};

export function ProcessingDashboard({
  onClose,
  onSelectScene,
  initialMode,
  embedded = false,
}: {
  onClose: () => void;
  onSelectScene?: (sceneId: string) => void;
  initialMode?: CaptureMode;
  embedded?: boolean;
}) {
  const [jobs, setJobs] = useState<PipelineJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [analyzing, setAnalyzing] = useState<string | null>(null);
  const [reconstructing, setReconstructing] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [clearingHistory, setClearingHistory] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [mode, setMode] = useState<CaptureMode>(initialMode || "photo_set");
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<Array<{ file: File; url: string }>>([]);
  const [overrideNoncritical, setOverrideNoncritical] = useState(false);
  const [depthExaggeration, setDepthExaggeration] = useState(1);
  const [profile, setProfile] = useState("auto");
  const [submittedSceneId, setSubmittedSceneId] = useState<string | null>(null);
  const [autoLoadedSceneId, setAutoLoadedSceneId] = useState<string | null>(null);
  const [historySearch, setHistorySearch] = useState("");

  useEffect(() => {
    if (initialMode) setMode(initialMode);
  }, [initialMode]);

  const refresh = (signal?: AbortSignal) => {
    setLoading(true);
    setError("");
    return listPipelineJobs(signal)
      .then(setJobs)
      .catch((reason: Error) => {
        if (reason.name !== "AbortError") setError(reason.message);
      })
      .finally(() => {
        if (!signal?.aborted) setLoading(false);
      });
  };

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const hasActiveJobs = jobs.some(
      (job) =>
        ["queued", "processing", "cancelling"].includes(job.status) ||
        job.stages.some((stage) => stage.status === "processing")
    );
    if (!hasActiveJobs && !submittedSceneId) return;
    const interval = setInterval(() => {
      listPipelineJobs().then(setJobs).catch(() => {});
    }, 1500);
    return () => clearInterval(interval);
  }, [jobs, submittedSceneId]);

  useEffect(() => {
    const next = files.map((file) => ({ file, url: URL.createObjectURL(file) }));
    setPreviews(next);
    return () => next.forEach((preview) => URL.revokeObjectURL(preview.url));
  }, [files]);

  const selectFiles = (incoming: File[]) => {
    setError("");
    setFiles(modeCopy[mode].multiple ? incoming : incoming.slice(0, 1));
  };

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    if (!uploading) selectFiles(Array.from(event.dataTransfer.files));
  };

  const submit = async () => {
    if (files.length === 0) {
      setError("Select genuine input files before starting a job.");
      return;
    }
    setUploading(true);
    setUploadProgress(0);
    setError("");
    try {
      let result: { scene_id: string; status: string };
      if (mode === "photo_set") {
        result = await uploadPhotoSet(files, undefined, setUploadProgress, overrideNoncritical, profile);
      } else if (mode === "video") {
        result = await uploadCapture(files[0], undefined, setUploadProgress);
      } else {
        result = await uploadSinglePhoto(files[0], undefined, setUploadProgress, depthExaggeration, profile);
      }
      setSubmittedSceneId(result.scene_id);
      setFiles([]);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Upload failed");
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  };

  const handleDeleteScene = async (sceneId: string) => {
    if (deletingId) return;
    setDeletingId(sceneId);
    setError("");
    try {
      await deleteSceneJob(sceneId);
      if (submittedSceneId === sceneId) setSubmittedSceneId(null);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Failed to delete scene");
    } finally {
      setDeletingId(null);
    }
  };

  const handleClearHistory = async () => {
    if (clearingHistory) return;
    setClearingHistory(true);
    setError("");
    try {
      await clearFailedHistory();
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Failed to clear history");
    } finally {
      setClearingHistory(false);
    }
  };

  const activeJob = submittedSceneId
    ? jobs.find((job) => job.scene_id === submittedSceneId)
    : jobs.find(
        (job) =>
          ["queued", "processing", "cancelling"].includes(job.status) ||
          job.stages.some((s) => s.status === "processing")
      );

  const displayJob =
    activeJob ||
    (submittedSceneId
      ? {
          scene_id: submittedSceneId,
          status: "queued" as const,
          current_stage: "starting",
          capture_mode: mode,
          has_original_input: true,
          has_viewer_manifest: false,
          error: null,
          stages: [
            { name: "discovery", status: "processing" as const, current_stage: "starting" },
            { name: mode === "single_photo" ? "depth_inference" : "capture", status: "queued" as const, current_stage: "queued" },
            { name: mode === "single_photo" ? "mesh_generation" : "readiness", status: "queued" as const, current_stage: "queued" },
          ],
        }
      : null);

  const isRendering = displayJob && ["queued", "processing", "cancelling"].includes(displayJob.status);
  const isComplete = displayJob && (displayJob.status === "ready" || displayJob.has_viewer_manifest || displayJob.status === "sparse_ready");
  const currentStageObj = displayJob?.stages.find((s) => s.status === "processing") || displayJob?.stages[0];
  const activeStageLabel = currentStageObj ? label(currentStageObj.name) : label(displayJob?.current_stage || "processing");

  useEffect(() => {
    if (!displayJob) return;
    const isReady = displayJob.status === "ready" || displayJob.has_viewer_manifest || displayJob.status === "sparse_ready";
    if (isReady && displayJob.scene_id !== autoLoadedSceneId) {
      setAutoLoadedSceneId(displayJob.scene_id);
      const timer = setTimeout(() => {
        onSelectScene?.(displayJob.scene_id);
        onClose();
      }, 1400);
      return () => clearTimeout(timer);
    }
  }, [displayJob, autoLoadedSceneId, onSelectScene, onClose]);

  const filteredJobs = jobs.filter((job) =>
    historySearch ? job.scene_id.toLowerCase().includes(historySearch.toLowerCase()) || (job.capture_mode ?? "").includes(historySearch) : true
  );

  const dashboardContent = (
    <section className={`processing-dashboard ${embedded ? "embedded-view" : ""}`} role={embedded ? "region" : "dialog"} aria-modal={!embedded} aria-labelledby="processing-title">
        <header>
          <div>
            <span className="eyebrow">Genuine spatial reconstruction</span>
            <h2 id="processing-title">3D Capture & Digital Twin Studio</h2>
          </div>
          <div>
            <button onClick={() => refresh()} aria-label="Refresh jobs" title="Refresh all jobs">↻</button>
            {!embedded && <button onClick={onClose} aria-label="Close processing jobs" title="Close dialog">×</button>}
          </div>
        </header>

        {isShowcaseMode() && (
          <div className="showcase-workflow-notice" role="status" style={{ margin: "16px 20px" }}>
            <div className="notice-icon">☁</div>
            <div className="notice-copy">
              <strong>Processing Studio Offline in Public Showcase</strong>
              <p>
                Live job queuing, frame extraction, and COLMAP bundle adjustment run locally on desktop workstations.
                In this static web showcase, explore the completed reconstructions in the 3D Viewer.
              </p>
            </div>
            <button type="button" className="notice-action-btn" onClick={() => (onSelectScene ? onSelectScene("scene_20261031T160047Z_cd37fab494") : onClose())}>
              Open COLMAP Video Scene in Viewer →
            </button>
          </div>
        )}

        {/* 1. DEDICATED PROCESSING STATUS CARD */}
        {displayJob && (
          <section className={`rendering-hero-banner ${isComplete ? "completed" : "active"}`} aria-label="3D rendering in progress">
            <div className="rendering-visual" aria-hidden="true">
              <div className="radar-grid">
                <div className="radar-sweep" />
                <div className="radar-crosshair-h" />
                <div className="radar-crosshair-v" />
                <div className="radar-ring r1" />
                <div className="radar-ring r2" />
                <div className="radar-ring r3" />
                <div className="radar-scanline" />
                <div className="radar-node n1" />
                <div className="radar-node n2" />
                <div className="radar-node n3" />
                <div className="radar-glyph">{isComplete ? "✓" : "◈"}</div>
              </div>
            </div>
            <div className="rendering-details">
              <div className="rendering-meta">
                <span className={`rendering-status-badge ${isComplete ? "completed" : "processing"}`}>
                  <span className="status-ping" />
                  {isComplete ? "3D Digital Twin Ready" : "3D Rendering in Progress"}
                </span>
                <span className="rendering-scene-tag">{displayJob.scene_id}</span>
                {displayJob.capture_mode && <span className="rendering-mode-tag">{label(displayJob.capture_mode)}</span>}
              </div>
              <h3 className="rendering-headline">
                {isComplete ? "3D Digital Twin Ready for Viewport!" : `Reconstructing 3D Spatial Mesh · ${activeStageLabel}`}
              </h3>
              <p className="rendering-explainer">
                {isComplete
                  ? "Interactive textured 3D model and camera trajectory are assembled. Loading into 3D viewport…"
                  : displayJob.capture_mode === "single_photo"
                  ? "Depth Anything V2 is predicting monocular depth geometry and generating textured 3D mesh. (Running on local CPU ~15–20s)"
                  : displayJob.capture_mode === "photo_set"
                  ? "Analyzing camera positions, view coverage, and feature matching across photographs."
                  : "Extracting frames and validating keyframe motion across the video sequence."}
              </p>

              <div className="rendering-pipeline-stages">
                {displayJob.stages.map((stage) => (
                  <div key={stage.name} className={`pipeline-stage-pill ${stage.status}`}>
                    <span className="stage-marker">
                      {stage.status === "completed" ? "✓" : stage.status === "processing" ? "●" : "○"}
                    </span>
                    <span className="stage-title">{label(stage.name)}</span>
                  </div>
                ))}
              </div>

              {!isComplete && (
                <div className="rendering-progress-track">
                  <div className="rendering-progress-shimmer" />
                </div>
              )}

              {/* Interactive Next-Step Guidance Prompts */}
              {displayJob.has_original_input && !displayJob.stages.some((s) => s.name === "readiness") && (displayJob.capture_mode === "photo_set" || displayJob.capture_mode === "video") && (
                <div className="processing-prompt-box">
                  <div className="prompt-content">
                    <strong>Capture frames extracted!</strong>
                    <span>Would you like to analyze multi-view overlap and camera quality before running COLMAP?</span>
                  </div>
                  <div className="prompt-actions">
                    <button
                      className="prompt-primary-btn"
                      disabled={analyzing === displayJob.scene_id}
                      onClick={async () => {
                        setAnalyzing(displayJob.scene_id);
                        setError("");
                        try {
                          const updated = await analyzePipelineCapture(displayJob.scene_id);
                          setJobs((cur) => cur.map((j) => (j.scene_id === updated.scene_id ? updated : j)));
                        } catch (e) {
                          setError(e instanceof Error ? e.message : "Capture analysis failed");
                        } finally {
                          setAnalyzing(null);
                        }
                      }}
                    >
                      {analyzing === displayJob.scene_id ? "Analyzing Overlap…" : "Yes, Analyze Capture Quality →"}
                    </button>
                    <button
                      className="prompt-secondary-btn"
                      disabled={reconstructing === displayJob.scene_id}
                      onClick={async () => {
                        setReconstructing(displayJob.scene_id);
                        setError("");
                        try {
                          await startReconstruction(displayJob.scene_id);
                          await refresh();
                        } catch (e) {
                          setError(e instanceof Error ? e.message : "Reconstruction failed");
                        } finally {
                          setReconstructing(null);
                        }
                      }}
                    >
                      Skip to Reconstruction
                    </button>
                  </div>
                </div>
              )}

              {["awaiting_reconstruction", "ready_for_reconstruction"].includes(displayJob.status) && (
                <div className="processing-prompt-box reconstruction-ready">
                  <div className="prompt-content">
                    <strong>Capture verified & ready for 3D Reconstruction!</strong>
                    <span>Start COLMAP feature matching, sparse bundle adjustment, and 3D point cloud generation.</span>
                  </div>
                  <div className="prompt-actions">
                    <button
                      className="prompt-primary-btn reconstruct-btn"
                      disabled={reconstructing === displayJob.scene_id}
                      onClick={async () => {
                        setReconstructing(displayJob.scene_id);
                        setError("");
                        try {
                          await startReconstruction(displayJob.scene_id);
                          await refresh();
                        } catch (e) {
                          setError(e instanceof Error ? e.message : "Reconstruction failed");
                        } finally {
                          setReconstructing(null);
                        }
                      }}
                    >
                      {reconstructing === displayJob.scene_id ? "Starting COLMAP CPU Engine…" : "Start 3D COLMAP Reconstruction Now →"}
                    </button>
                  </div>
                </div>
              )}

              {isComplete && (
                <div className="rendering-action-row">
                  <button
                    className="view-3d-button"
                    onClick={() => {
                      onSelectScene?.(displayJob.scene_id);
                      onClose();
                    }}
                  >
                    View 3D Digital Twin Now →
                  </button>
                  <button className="dismiss-button" onClick={() => setSubmittedSceneId(null)}>
                    Dismiss Status
                  </button>
                </div>
              )}
            </div>
          </section>
        )}

        {/* 2. MODE SELECTOR TABS */}
        <div className="capture-modes" role="tablist" aria-label="Capture mode">
          {(Object.keys(modeCopy) as CaptureMode[]).map((candidate) => (
            <button
              key={candidate}
              role="tab"
              aria-selected={mode === candidate}
              className={mode === candidate ? "active" : ""}
              onClick={() => {
                setMode(candidate);
                setFiles([]);
                setError("");
              }}
            >
              <strong>{modeCopy[candidate].title}</strong>
              <span>{modeCopy[candidate].detail}</span>
            </button>
          ))}
        </div>

        {/* 3. DEDICATED BESPOKE MODE CARD FOR EACH PIPELINE */}
        <section className="mode-card" aria-label={`${modeCopy[mode].title} workspace`}>
          {/* Feature Highlights on top of the card */}
          <div className="mode-highlights-bar">
            <span className="highlight-badge">{modeHighlights[mode].badge}</span>
            <div className="highlight-chips">
              {modeHighlights[mode].items.map((item) => (
                <span key={item} className="highlight-chip">
                  <i>⚡</i> {item}
                </span>
              ))}
            </div>
          </div>

          <div className="capture-composer">
            <label className="capture-drop" onDragOver={(event) => event.preventDefault()} onDrop={onDrop}>
              <input
                type="file"
                accept={modeCopy[mode].accept}
                multiple={modeCopy[mode].multiple}
                disabled={uploading}
                onChange={(event) => selectFiles(Array.from(event.target.files ?? []))}
              />
              <strong>{files.length ? `${files.length} file${files.length === 1 ? "" : "s"} selected` : `Drop ${modeCopy[mode].title.toLowerCase()} files here or browse`}</strong>
              <span>
                {mode === "photo_set"
                  ? "Select multiple overlapping photos (JPG, PNG, HEIC). SpatialForge evaluates camera overlap."
                  : mode === "video"
                  ? "Drop an MP4, MOV, MKV, or WebM video. SpatialForge samples 2 FPS keyframes and eliminates blurry shots."
                  : "Upload one photo (JPG, PNG). Depth Anything V2 estimates depth geometry and generates a 3D textured mesh."}
              </span>
            </label>

            {previews.length > 0 && (
              <div className="capture-previews">
                {previews.map(({ file, url }, index) => (
                  <article key={`${file.name}-${file.lastModified}-${index}`}>
                    {mode === "video" ? <div className="file-tile">VIDEO</div> : <img src={url} alt="" />}
                    <div>
                      <strong>{file.name}</strong>
                      <small>{(file.size / 1024 / 1024).toFixed(2)} MB</small>
                    </div>
                    <button
                      aria-label={`Remove ${file.name}`}
                      onClick={() => setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                    >
                      ×
                    </button>
                  </article>
                ))}
              </div>
            )}

            {mode !== "video" && (
              <label className="capture-option">
                <span>
                  <strong>Processing profile</strong>
                  <small>Auto selects a real memory-safe limit; Fast is recommended for this laptop.</small>
                </span>
                <select aria-label="Processing profile" value={profile} onChange={(event) => setProfile(event.target.value)}>
                  <option value="auto">Auto</option>
                  <option value="fast">Fast</option>
                  <option value="balanced">Balanced</option>
                  <option value="quality">Quality</option>
                </select>
              </label>
            )}

            {mode === "photo_set" && (
              <label className="capture-option">
                <input type="checkbox" checked={overrideNoncritical} onChange={(event) => setOverrideNoncritical(event.target.checked)} />
                <span>
                  <strong>Keep quality warnings</strong>
                  <small>Retain blur outliers and redundant-looking views; exact duplicates and invalid images are still rejected.</small>
                </span>
              </label>
            )}

            {mode === "single_photo" && (
              <label className="capture-option">
                <span>
                  <strong>Depth effect</strong>
                  <small>{depthExaggeration.toFixed(2)}× · visual exaggeration only, never metric scale</small>
                </span>
                <input
                  aria-label="Depth effect"
                  type="range"
                  min="0.25"
                  max="3"
                  step="0.05"
                  value={depthExaggeration}
                  onChange={(event) => setDepthExaggeration(Number(event.target.value))}
                />
              </label>
            )}

            <footer>
              <span>
                {mode === "single_photo"
                  ? "AI-estimated and non-metric · Walk navigation remains disabled for uncertain single-view geometry."
                  : mode === "video"
                  ? "Video keyframes will be sampled and validated before reconstruction."
                  : "Overlap and camera coverage are checked during feature extraction."}
              </span>
              <button
                disabled={uploading || files.length === 0 || isShowcaseMode()}
                title={isShowcaseMode() ? "Capture processing runs locally on desktop workstations" : undefined}
                onClick={submit}
              >
                {uploading
                  ? (uploadProgress === null ? "Uploading…" : `Uploading ${uploadProgress}%`)
                  : isShowcaseMode()
                  ? "Offline in Public Showcase"
                  : `Start ${modeCopy[mode].title.toLowerCase()} job`}
              </button>
            </footer>
          </div>
        </section>

        {loading && <div className="jobs-state" role="status">Reading processing manifests…</div>}
        {error && <div className="jobs-state error" role="alert">{error}</div>}

        {/* 4. DEDICATED JOB HISTORY & COMPLETED DIGITAL TWINS CARD */}
        <section className="job-history-section" aria-label="Digital twin job history">
          <header className="history-header">
            <div>
              <h3>Reconstruction History & Digital Twins</h3>
              <span className="history-count-badge">{filteredJobs.length} scenes</span>
            </div>
            <div className="history-controls">
              <input
                type="search"
                className="history-search-input"
                placeholder="Filter scenes by ID or mode…"
                value={historySearch}
                onChange={(e) => setHistorySearch(e.target.value)}
                aria-label="Filter history"
              />
              <button
                className="clear-history-btn"
                disabled={clearingHistory || jobs.length === 0}
                onClick={handleClearHistory}
                title="Remove failed and cancelled runs from history"
              >
                {clearingHistory ? "Clearing…" : "Clear Failed Runs"}
              </button>
            </div>
          </header>

          {!loading && !error && filteredJobs.length === 0 && (
            <div className="jobs-state">No matching digital twins or processing jobs found.</div>
          )}

          <div className="job-list">
            {filteredJobs.map((job) => (
              <article className={`job-card ${job.status}`} key={job.scene_id}>
                <header>
                  <div>
                    <strong>{job.scene_id}</strong>
                    <small>{job.capture_mode ? label(job.capture_mode) : label(job.current_stage)}</small>
                  </div>
                  <div className="job-header-right">
                    <span>{label(job.status)}</span>
                    <button
                      className="delete-scene-btn"
                      disabled={deletingId === job.scene_id}
                      onClick={() => handleDeleteScene(job.scene_id)}
                      title="Permanently delete scene and remove from history"
                      aria-label={`Delete ${job.scene_id}`}
                    >
                      {deletingId === job.scene_id ? "…" : "🗑"}
                    </button>
                  </div>
                </header>

                <ol>
                  {job.stages.map((stage) => (
                    <li key={stage.name} className={stage.status}>
                      <i />
                      <span>{label(stage.name)}</span>
                      <em>{label(stage.current_stage || stage.status)}</em>
                    </li>
                  ))}
                </ol>

                {job.error && <p role="alert">{job.error}</p>}

                <div className="job-card-actions">
                  {(job.status === "ready" || job.has_viewer_manifest) && (
                    <button
                      className="primary-action"
                      onClick={() => {
                        onSelectScene?.(job.scene_id);
                        onClose();
                      }}
                    >
                      View 3D digital twin →
                    </button>
                  )}

                  {["queued", "processing", "cancelling"].includes(job.status) &&
                    ["photo_set", "single_photo"].includes(job.capture_mode ?? "") && (
                      <button
                        disabled={job.status === "cancelling"}
                        onClick={async () => {
                          setError("");
                          try {
                            await cancelCapture(job.scene_id);
                            await refresh();
                          } catch (reason) {
                            setError(reason instanceof Error ? reason.message : "Cancellation failed");
                          }
                        }}
                      >
                        {job.status === "cancelling" ? "Cancelling…" : "Cancel processing"}
                      </button>
                    )}

                  {job.has_original_input &&
                    !job.stages.some((stage) => stage.name === "readiness") &&
                    (job.capture_mode === "photo_set" || job.capture_mode === "video") && (
                      <button
                        disabled={analyzing === job.scene_id}
                        onClick={async () => {
                          setAnalyzing(job.scene_id);
                          setError("");
                          try {
                            const updated = await analyzePipelineCapture(job.scene_id);
                            setJobs((current) =>
                              current.map((candidate) => (candidate.scene_id === updated.scene_id ? updated : candidate))
                            );
                          } catch (reason) {
                            setError(reason instanceof Error ? reason.message : "Capture analysis failed");
                          } finally {
                            setAnalyzing(null);
                          }
                        }}
                      >
                        {analyzing === job.scene_id ? "Analyzing…" : "Analyze capture"}
                      </button>
                    )}

                  {["awaiting_reconstruction", "ready_for_reconstruction"].includes(job.status) && (
                    <button
                      disabled={reconstructing === job.scene_id}
                      onClick={async () => {
                        setReconstructing(job.scene_id);
                        setError("");
                        try {
                          await startReconstruction(job.scene_id);
                          await refresh();
                        } catch (reason) {
                          setError(reason instanceof Error ? reason.message : "Reconstruction could not start");
                        } finally {
                          setReconstructing(null);
                        }
                      }}
                    >
                      {reconstructing === job.scene_id ? "Starting COLMAP…" : "Start COLMAP reconstruction"}
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>
      </section>
  );

  if (embedded) {
    return <div className="processing-embedded-container">{dashboardContent}</div>;
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      {dashboardContent}
    </div>
  );
}
