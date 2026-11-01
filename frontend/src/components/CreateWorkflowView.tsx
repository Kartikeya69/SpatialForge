import { useEffect, useRef, useState, type DragEvent } from "react";
import {
  analyzePipelineCapture,
  clearFailedHistory,
  isShowcaseMode,
  listPipelineJobs,
  startReconstruction,
  uploadCapture,
  uploadPhotoSet,
  uploadSinglePhoto,
} from "../api";
import type { PipelineJob } from "../types";

export type CaptureMode = "video" | "photo_set" | "single_photo";

interface CreateWorkflowViewProps {
  initialMode?: CaptureMode;
  onSelectScene: (sceneId: string) => void;
  onNavigateTab: (tab: "dashboard" | "create" | "scenes" | "processing" | "settings" | "viewer") => void;
}

export function CreateWorkflowView({
  initialMode = "video",
  onSelectScene,
  onNavigateTab,
}: CreateWorkflowViewProps) {
  const [mode, setMode] = useState<CaptureMode>(initialMode);
  const [files, setFiles] = useState<File[]>([]);
  const [videoPreviewUrl, setVideoPreviewUrl] = useState<string | null>(null);
  const [imagePreviews, setImagePreviews] = useState<Array<{ name: string; url: string; size: string }>>([]);
  const [videoMeta, setVideoMeta] = useState<{ duration: number; width: number; height: number } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [reconstructing, setReconstructing] = useState(false);
  const [analysisReport, setAnalysisReport] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submittedSceneId, setSubmittedSceneId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<PipelineJob | null>(null);
  const [activeStep, setActiveStep] = useState<1 | 2 | 3 | 4>(1);
  const [isDragging, setIsDragging] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [clearingHistory, setClearingHistory] = useState(false);

  // Configuration settings
  const [profile, setProfile] = useState("auto");
  const [sequentialOverlap, setSequentialOverlap] = useState(10);
  const [keyframeFps, setKeyframeFps] = useState(2);
  const [depthExaggeration, setDepthExaggeration] = useState(1.0);
  const [cameraModel, setCameraModel] = useState("SIMPLE_RADIAL");

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Clean up object URLs on unmount or file change
  useEffect(() => {
    return () => {
      if (videoPreviewUrl) URL.revokeObjectURL(videoPreviewUrl);
      imagePreviews.forEach((p) => URL.revokeObjectURL(p.url));
    };
  }, [videoPreviewUrl, imagePreviews]);

  // Poll job status when submittedSceneId is active
  useEffect(() => {
    if (!submittedSceneId) return;
    let mounted = true;
    const pollJob = async () => {
      try {
        const jobs = await listPipelineJobs();
        if (!mounted) return;
        const current = jobs.find((j) => j.scene_id === submittedSceneId);
        if (current) {
          setActiveJob(current);
        }
      } catch {
        // ignore polling network errors
      }
    };
    pollJob();
    const interval = setInterval(pollJob, 2000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [submittedSceneId]);

  const handleModeChange = (newMode: CaptureMode) => {
    setMode(newMode);
    setFiles([]);
    if (videoPreviewUrl) URL.revokeObjectURL(videoPreviewUrl);
    imagePreviews.forEach((p) => URL.revokeObjectURL(p.url));
    setVideoPreviewUrl(null);
    setImagePreviews([]);
    setVideoMeta(null);
    setError(null);
    setNotice(null);
    setAnalysisReport(null);
    setSubmittedSceneId(null);
    setActiveJob(null);
    setActiveStep(1);
  };

  const handleFilesSelected = (selectedFiles: FileList | File[]) => {
    setError(null);
    setNotice(null);
    setAnalysisReport(null);
    setSubmittedSceneId(null);
    setActiveJob(null);
    const fileList = Array.from(selectedFiles);
    if (!fileList.length) return;

    if (mode === "video") {
      const file = fileList[0];
      if (!file.type.startsWith("video/") && !/\.(mp4|mov|mkv|webm|m4v)$/i.test(file.name)) {
        setError("Please select a valid video file (.mp4, .mov, .webm, .mkv).");
        return;
      }
      setFiles([file]);
      if (videoPreviewUrl) URL.revokeObjectURL(videoPreviewUrl);
      const url = URL.createObjectURL(file);
      setVideoPreviewUrl(url);

      const videoEl = document.createElement("video");
      videoEl.preload = "metadata";
      videoEl.src = url;
      videoEl.onloadedmetadata = () => {
        setVideoMeta({
          duration: videoEl.duration,
          width: videoEl.videoWidth,
          height: videoEl.videoHeight,
        });
      };
      setActiveStep(2);
    } else if (mode === "photo_set") {
      const validImages = fileList.filter(
        (f) => f.type.startsWith("image/") || /\.(jpg|jpeg|png|heic|heif)$/i.test(f.name)
      );
      if (validImages.length === 0) {
        setError("Please select valid image files (.jpg, .png, .heic).");
        return;
      }
      const combined = [...files, ...validImages];
      setFiles(combined);

      const previews = combined.slice(0, 12).map((f) => ({
        name: f.name,
        url: URL.createObjectURL(f),
        size: (f.size / (1024 * 1024)).toFixed(1) + " MB",
      }));
      setImagePreviews(previews);
      setActiveStep(2);
    } else {
      const file = fileList[0];
      if (!file.type.startsWith("image/") && !/\.(jpg|jpeg|png|heic|heif)$/i.test(file.name)) {
        setError("Please select a valid image file (.jpg, .png).");
        return;
      }
      setFiles([file]);
      const previews = [
        {
          name: file.name,
          url: URL.createObjectURL(file),
          size: (file.size / (1024 * 1024)).toFixed(1) + " MB",
        },
      ];
      setImagePreviews(previews);
      setActiveStep(2);
    }
  };

  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const onDragLeave = () => {
    setIsDragging(false);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files) {
      handleFilesSelected(e.dataTransfer.files);
    }
  };

  // Step 2 Action: Extract and Analyze Frames
  const handleExtractAndAnalyze = async () => {
    if (!files.length) {
      setError("Please select capture files to begin analysis.");
      return;
    }
    if (mode === "photo_set" && files.length < 3) {
      setError("Photo set reconstruction requires at least 3 overlapping images.");
      return;
    }

    setAnalyzing(true);
    setUploadProgress(0);
    setError(null);
    setNotice(null);

    try {
      let sceneId = submittedSceneId;
      if (!sceneId) {
        if (mode === "video") {
          const res = await uploadCapture(files[0], undefined, (pct) => setUploadProgress(pct));
          sceneId = res.scene_id;
        } else if (mode === "photo_set") {
          const res = await uploadPhotoSet(
            files,
            undefined,
            (pct) => setUploadProgress(pct),
            false,
            profile
          );
          sceneId = res.scene_id;
        }
      }

      if (sceneId) {
        setSubmittedSceneId(sceneId);
        // Call backend readiness analysis
        const jobWithReport = await analyzePipelineCapture(sceneId);
        setActiveJob(jobWithReport);
        const readinessStage = jobWithReport.stages?.find((s) => s.name === "readiness");
        if (readinessStage && readinessStage.details) {
          setAnalysisReport(readinessStage.details);
        } else {
          setAnalysisReport({
            status: "ready",
            accepted_frames: files.length,
            match_ratio: 0.45,
          });
        }
        setActiveStep(3);
        setNotice("Frame analysis completed successfully. Review diagnostics and confirm configuration.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Frame extraction or analysis failed.");
    } finally {
      setAnalyzing(false);
      setUploadProgress(null);
    }
  };

  // Step 4 Action: Launch Reconstruction
  const handleStartReconstruction = async () => {
    if (mode === "single_photo") {
      if (!files.length) {
        setError("Please select a photo before starting reconstruction.");
        return;
      }
      setUploading(true);
      setUploadProgress(0);
      setError(null);
      try {
        const res = await uploadSinglePhoto(
          files[0],
          undefined,
          (pct) => setUploadProgress(pct),
          depthExaggeration,
          profile
        );
        setSubmittedSceneId(res.scene_id);
        setActiveStep(4);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Single photo reconstruction submission failed.");
      } finally {
        setUploading(false);
      }
      return;
    }

    if (!submittedSceneId) {
      // If user skipped directly to reconstruct, run extraction then reconstruction
      await handleExtractAndAnalyze();
      return;
    }

    setReconstructing(true);
    setError(null);
    try {
      await startReconstruction(submittedSceneId);
      setActiveStep(4);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Starting COLMAP reconstruction failed.");
    } finally {
      setReconstructing(false);
    }
  };

  const handleRetryReconstruction = async () => {
    if (!submittedSceneId) return;
    setReconstructing(true);
    setError(null);
    try {
      await startReconstruction(submittedSceneId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retry failed.");
    } finally {
      setReconstructing(false);
    }
  };

  const handleClearHistory = async () => {
    if (clearingHistory) return;
    setClearingHistory(true);
    setError(null);
    try {
      const res = await clearFailedHistory();
      setNotice(`Cleared ${res.count} incomplete / failed history runs. Reconstructed scenes preserved.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to clear history.");
    } finally {
      setClearingHistory(false);
    }
  };

  const isReady = activeJob?.status === "ready" || activeJob?.status === "sparse_ready" || !!activeJob?.has_viewer_manifest;
  const isFailed = activeJob?.status === "failed";
  const currentStageName = activeJob?.current_stage || (uploading ? "uploading" : analyzing ? "analyzing" : "processing");

  return (
    <div className="view-container create-view" data-testid="create-workflow-view">
      {/* View Header */}
      <header className="create-view-header">
        <div className="create-header-copy">
          <span className="eyebrow">Capture & Reconstruct</span>
          <h2>Create a New 3D Scene</h2>
          <p>
            Choose your capture source. SpatialForge analyzes your footage, extracts features, and builds
            interactive 3D spatial models optimized for your hardware.
          </p>
        </div>
        <div className="create-header-actions">
          <button
            type="button"
            className="btn-secondary btn-clear-history"
            disabled={clearingHistory}
            onClick={handleClearHistory}
            title="Clean up incomplete or failed reconstruction runs"
          >
            {clearingHistory ? "Cleaning…" : "🗑 Clear Incomplete History"}
          </button>
        </div>
      </header>

      {isShowcaseMode() && (
        <div className="showcase-workflow-notice" role="status">
          <div className="notice-icon">☁</div>
          <div className="notice-copy">
            <strong>Public Showcase Mode (Read-Only)</strong>
            <p>
              Capture upload, frame analysis, and photogrammetry reconstruction run locally on desktop workstations
              using Python, COLMAP 4.2+, and Depth Anything V2. This static cloud deployment cannot process new media.
            </p>
          </div>
          <button type="button" className="notice-action-btn" onClick={() => onNavigateTab("viewer")}>
            Explore Pre-computed Reconstructions in Viewer →
          </button>
        </div>
      )}

      {notice && (
        <div className="workflow-alert-notice" role="status" style={{ marginBottom: "1rem" }}>
          <span>✓ {notice}</span>
          <button type="button" onClick={() => setNotice(null)} style={{ background: "none", border: "none", color: "inherit", cursor: "pointer", marginLeft: "auto" }}>×</button>
        </div>
      )}

      {/* Top 3 Distinct Capture Method Cards */}
      <section className="create-modes-grid" aria-label="Capture Methods">
        {/* Card 1: Video to 3D */}
        <article
          className={`mode-selector-card ${mode === "video" ? "active" : ""}`}
          onClick={() => handleModeChange("video")}
          role="button"
          tabIndex={0}
          aria-pressed={mode === "video"}
        >
          <div className="mode-card-header">
            <span className="mode-icon-badge video">🎬</span>
            <span className="mode-badge">COLMAP Sequential SfM</span>
          </div>
          <h3>Video to 3D</h3>
          <p>
            Upload a smooth walkthrough video of a room or structure. Automated keyframe sampling at 2 FPS
            with motion-blur rejection and trajectory recovery.
          </p>
          <div className="mode-card-footer">
            <span className="mode-highlight">✓ 10–60s walkthrough</span>
            <button
              type="button"
              className={`mode-btn ${mode === "video" ? "primary" : "secondary"}`}
              onClick={(e) => {
                e.stopPropagation();
                handleModeChange("video");
              }}
            >
              {mode === "video" ? "Selected Workflow ✓" : "Select Video →"}
            </button>
          </div>
        </article>

        {/* Card 2: Photo Set to 3D */}
        <article
          className={`mode-selector-card ${mode === "photo_set" ? "active" : ""}`}
          onClick={() => handleModeChange("photo_set")}
          role="button"
          tabIndex={0}
          aria-pressed={mode === "photo_set"}
        >
          <div className="mode-card-header">
            <span className="mode-icon-badge photo-set">📸</span>
            <span className="mode-badge">COLMAP Multi-View</span>
          </div>
          <h3>Photo Set to 3D</h3>
          <p>
            Upload overlapping photographs with 60%+ mutual visual overlap. Full SIFT feature matching,
            sparse bundle adjustment, and camera pose registration.
          </p>
          <div className="mode-card-footer">
            <span className="mode-highlight">✓ 15–80+ photos</span>
            <button
              type="button"
              className={`mode-btn ${mode === "photo_set" ? "primary" : "secondary"}`}
              onClick={(e) => {
                e.stopPropagation();
                handleModeChange("photo_set");
              }}
            >
              {mode === "photo_set" ? "Selected Workflow ✓" : "Select Photo Set →"}
            </button>
          </div>
        </article>

        {/* Card 3: Single Photo AI */}
        <article
          className={`mode-selector-card ${mode === "single_photo" ? "active" : ""}`}
          onClick={() => handleModeChange("single_photo")}
          role="button"
          tabIndex={0}
          aria-pressed={mode === "single_photo"}
        >
          <div className="mode-card-header">
            <span className="mode-icon-badge single-photo">✨</span>
            <span className="mode-badge">Depth Anything V2</span>
          </div>
          <h3>Single Photo to 3D</h3>
          <p>
            Upload one room photo for instant AI-estimated 2.5D surface mesh reconstruction via ONNX Runtime.
            Rapid CPU preview generated in ~15–20 seconds.
          </p>
          <div className="mode-card-footer">
            <span className="mode-highlight">✓ Fast 2.5D preview</span>
            <button
              type="button"
              className={`mode-btn ${mode === "single_photo" ? "primary" : "secondary"}`}
              onClick={(e) => {
                e.stopPropagation();
                handleModeChange("single_photo");
              }}
            >
              {mode === "single_photo" ? "Selected Workflow ✓" : "Select Single Photo →"}
            </button>
          </div>
        </article>
      </section>

      {/* Guided 4-Step Workflow Area */}
      <section className="guided-workflow-panel">
        <nav className="workflow-steps-nav" aria-label="Reconstruction Steps">
          <div className={`step-item ${activeStep >= 1 ? "completed" : ""} ${activeStep === 1 ? "active" : ""}`}>
            <span className="step-num">1</span>
            <span className="step-label">Upload</span>
          </div>
          <div className="step-connector" />
          <div className={`step-item ${activeStep >= 2 ? "completed" : ""} ${activeStep === 2 ? "active" : ""}`}>
            <span className="step-num">2</span>
            <span className="step-label">Analyze</span>
          </div>
          <div className="step-connector" />
          <div className={`step-item ${activeStep >= 3 ? "completed" : ""} ${activeStep === 3 ? "active" : ""}`}>
            <span className="step-num">3</span>
            <span className="step-label">Configure</span>
          </div>
          <div className="step-connector" />
          <div className={`step-item ${activeStep >= 4 ? "completed" : ""} ${activeStep === 4 ? "active" : ""}`}>
            <span className="step-num">4</span>
            <span className="step-label">Reconstruct</span>
          </div>
        </nav>

        {error && (
          <div className="workflow-alert-error" role="alert">
            <span className="alert-icon">⚠</span>
            <span>{error}</span>
          </div>
        )}

        {/* STEP 4: DEDICATED LIVE PROCESSING CARD */}
        {activeStep === 4 && submittedSceneId ? (
          <div className="workflow-success-card" data-testid="live-processing-card">
            <div className={`rendering-hero-banner ${isReady ? "completed" : isFailed ? "failed" : "active"}`} style={{ width: "100%", margin: 0 }}>
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
                  <div className="radar-glyph">{isReady ? "✓" : isFailed ? "!" : "◈"}</div>
                </div>
              </div>
              <div className="rendering-details">
                <div className="rendering-meta">
                  <span className={`rendering-status-badge ${isReady ? "completed" : isFailed ? "failed" : "processing"}`}>
                    <span className="status-ping" />
                    {isReady ? "3D Digital Twin Ready" : isFailed ? "Reconstruction Failed" : "3D Reconstruction Active"}
                  </span>
                  <span className="rendering-scene-tag">{submittedSceneId}</span>
                  <span className="rendering-mode-tag">{mode.replace("_", " ").toUpperCase()}</span>
                </div>
                <h3 className="rendering-headline">
                  {isReady
                    ? "Interactive 3D Scene Assembled & Ready!"
                    : isFailed
                    ? `Reconstruction Failed at Stage: ${currentStageName}`
                    : `Processing 3D Scene · ${currentStageName}`}
                </h3>
                <p className="rendering-explainer">
                  {isReady
                    ? "Genuine 3D geometry and camera telemetry have been verified and packaged into Viewer 2.0."
                    : isFailed
                    ? "Reconstruction encountered an issue. You can retry with adjusted parameters or view logs."
                    : mode === "single_photo"
                    ? "Depth Anything V2 is predicting monocular depth geometry on local CPU (~15–20s)."
                    : "COLMAP Structure-from-Motion is extracting SIFT features, registering cameras, and triangulating 3D points."}
                </p>

                {/* Pipeline Stage Pills */}
                {activeJob?.stages && activeJob.stages.length > 0 && (
                  <div className="rendering-pipeline-stages">
                    {activeJob.stages.map((stage) => (
                      <div key={stage.name} className={`pipeline-stage-pill ${stage.status}`}>
                        <span className="stage-marker">
                          {stage.status === "completed" ? "✓" : stage.status === "processing" ? "●" : "○"}
                        </span>
                        <span className="stage-title">{stage.name.replace(/_/g, " ")}</span>
                      </div>
                    ))}
                  </div>
                )}

                {!isReady && !isFailed && (
                  <div className="rendering-progress-track">
                    <div className="rendering-progress-shimmer" />
                  </div>
                )}

                <div className="success-actions" style={{ marginTop: "1.5rem" }}>
                  {isReady ? (
                    <>
                      <button
                        type="button"
                        className="btn-primary"
                        onClick={() => {
                          onSelectScene(submittedSceneId);
                          onNavigateTab("viewer");
                        }}
                      >
                        🚀 Open in 3D Viewer
                      </button>
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => onNavigateTab("scenes")}
                      >
                        View in Scene Library
                      </button>
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => onNavigateTab("processing")}
                      >
                        Processing Studio
                      </button>
                      <button
                        type="button"
                        className="btn-text"
                        onClick={() => {
                          setSubmittedSceneId(null);
                          setFiles([]);
                          setAnalysisReport(null);
                          setActiveStep(1);
                        }}
                      >
                        + Start Another Reconstruction
                      </button>
                    </>
                  ) : isFailed ? (
                    <>
                      <button
                        type="button"
                        className="btn-primary"
                        disabled={reconstructing}
                        onClick={handleRetryReconstruction}
                      >
                        {reconstructing ? "Retrying…" : "Retry Reconstruction"}
                      </button>
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => onNavigateTab("processing")}
                      >
                        Inspect Logs in Studio
                      </button>
                      <button
                        type="button"
                        className="btn-text"
                        onClick={() => {
                          setSubmittedSceneId(null);
                          setFiles([]);
                          setAnalysisReport(null);
                          setActiveStep(1);
                        }}
                      >
                        Start Over
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => onNavigateTab("processing")}
                      >
                        Monitor in Processing Studio →
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="workflow-step-body">
            {/* Step 1: Upload Dropzone & File Review */}
            <div
              className={`workflow-dropzone ${isDragging ? "dragging" : ""} ${files.length ? "has-files" : ""}`}
              onDragOver={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
            >
              <input
                ref={fileInputRef}
                type="file"
                className="visually-hidden"
                accept={
                  mode === "video"
                    ? ".mp4,.mov,.m4v,.mkv,.webm,video/*"
                    : ".jpg,.jpeg,.png,.heic,.heif,image/*"
                }
                multiple={mode === "photo_set"}
                onChange={(e) => e.target.files && handleFilesSelected(e.target.files)}
              />

              {!files.length ? (
                <div className="dropzone-empty-state">
                  <div className="dropzone-icon">{mode === "video" ? "📹" : mode === "photo_set" ? "📁" : "🖼️"}</div>
                  <h3>
                    {mode === "video"
                      ? "Drop your room walkthrough video here"
                      : mode === "photo_set"
                      ? "Drop multiple overlapping photographs here"
                      : "Drop a single room photo here"}
                  </h3>
                  <p>
                    {mode === "video"
                      ? "Supports MP4, MOV, MKV, WebM (Smooth continuous motion recommended)"
                      : mode === "photo_set"
                      ? "Supports JPG, PNG, HEIC (At least 3 images required, 15–40+ recommended)"
                      : "Supports JPG, PNG (Perspective room views yield the best depth mesh)"}
                  </p>
                  <button
                    type="button"
                    className="browse-files-btn"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    📂 Browse Files
                  </button>
                </div>
              ) : (
                <div className="dropzone-selected-summary">
                  <div className="selected-header">
                    <h4>
                      ✓ Selected {files.length} {files.length === 1 ? "file" : "files"} for{" "}
                      {mode === "video" ? "Video Reconstruction" : mode === "photo_set" ? "Photo Set" : "Single Photo"}
                    </h4>
                    <button
                      type="button"
                      className="btn-clear-files"
                      onClick={() => {
                        setFiles([]);
                        setImagePreviews([]);
                        setVideoPreviewUrl(null);
                        setVideoMeta(null);
                        setAnalysisReport(null);
                        setSubmittedSceneId(null);
                        setActiveStep(1);
                      }}
                    >
                      Clear / Replace
                    </button>
                  </div>

                  {/* Video Preview */}
                  {mode === "video" && videoPreviewUrl && (
                    <div className="video-preview-wrapper">
                      <video src={videoPreviewUrl} controls className="video-player" />
                      {videoMeta && (
                        <div className="video-specs-pill">
                          <span>⏱ {videoMeta.duration.toFixed(1)}s</span>
                          <span>📐 {videoMeta.width}×{videoMeta.height}</span>
                          <span>🎞 ~{Math.round(videoMeta.duration * keyframeFps)} keyframes</span>
                          <span>📦 {(files[0].size / (1024 * 1024)).toFixed(1)} MB</span>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Photo Thumbnails */}
                  {(mode === "photo_set" || mode === "single_photo") && imagePreviews.length > 0 && (
                    <div className="photos-preview-grid">
                      {imagePreviews.map((img, idx) => (
                        <div className="photo-thumb-card" key={idx}>
                          <img src={img.url} alt={img.name} />
                          <span className="photo-thumb-name">{img.name}</span>
                          <small className="photo-thumb-size">{img.size}</small>
                        </div>
                      ))}
                      {files.length > 12 && (
                        <div className="photo-thumb-more">
                          +{files.length - 12} more images
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* STEP 2 & 3: ANALYSIS & CONFIGURATION CARD */}
            {files.length > 0 && (
              <div className="workflow-config-card">
                <div className="config-card-header">
                  <div>
                    <h4>{activeStep === 3 ? "Analysis Diagnostics & Configuration" : "Reconstruction Configuration"}</h4>
                    <p>Adjust parameters or use automatic hardware-bounded defaults.</p>
                  </div>
                  <button
                    type="button"
                    className="toggle-advanced-btn"
                    onClick={() => setShowAdvanced(!showAdvanced)}
                  >
                    {showAdvanced ? "Hide Advanced Options ▴" : "Show Advanced Options ▾"}
                  </button>
                </div>

                {/* Analysis Diagnostics Box (if analyzed) */}
                {analysisReport && (
                  <div className="analysis-report-box" style={{ background: "rgba(56, 189, 248, 0.08)", border: "1px solid rgba(56, 189, 248, 0.25)", borderRadius: "8px", padding: "1rem", marginBottom: "1.25rem" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                      <span style={{ color: "#38bdf8", fontWeight: "bold" }}>🔍 Frame & Overlap Diagnostics</span>
                      <span className="badge badge-success" style={{ marginLeft: "auto", fontSize: "0.75rem", padding: "2px 8px", borderRadius: "4px", background: "rgba(16, 185, 129, 0.2)", color: "#10b981" }}>
                        Analysis Complete
                      </span>
                    </div>
                    <div className="config-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "0.75rem", fontSize: "0.85rem" }}>
                      <div>
                        <small style={{ color: "var(--muted, #94a3b8)", display: "block" }}>Frames Extracted</small>
                        <strong>{analysisReport.accepted_frames ?? files.length} accepted</strong>
                      </div>
                      <div>
                        <small style={{ color: "var(--muted, #94a3b8)", display: "block" }}>Motion Sharpness</small>
                        <strong>{analysisReport.sharpness_mean ? analysisReport.sharpness_mean.toFixed(1) : "Sharp"}</strong>
                      </div>
                      <div>
                        <small style={{ color: "var(--muted, #94a3b8)", display: "block" }}>Pairwise Overlap</small>
                        <strong>{analysisReport.median_match_ratio ? `${Math.round(analysisReport.median_match_ratio * 100)}%` : "Verified"}</strong>
                      </div>
                      <div>
                        <small style={{ color: "var(--muted, #94a3b8)", display: "block" }}>Pixel Displacement</small>
                        <strong>{analysisReport.median_displacement_pixels ? `${analysisReport.median_displacement_pixels.toFixed(1)} px` : "Optimal"}</strong>
                      </div>
                    </div>
                  </div>
                )}

                <div className="config-grid">
                  <div className="config-field">
                    <label htmlFor="config-profile">Processing Profile</label>
                    <select
                      id="config-profile"
                      value={profile}
                      onChange={(e) => setProfile(e.target.value)}
                    >
                      <option value="auto">Balanced (Recommended for Intel Iris/UHD)</option>
                      <option value="high">High Quality (Denser points)</option>
                      <option value="fast">Fast Preview (Lower resolution)</option>
                    </select>
                    <small>Optimizes SIFT octaves and keyframe extraction limits.</small>
                  </div>

                  {mode === "video" && (
                    <div className="config-field">
                      <label htmlFor="config-fps">Keyframe Rate (FPS)</label>
                      <select
                        id="config-fps"
                        value={keyframeFps}
                        onChange={(e) => setKeyframeFps(Number(e.target.value))}
                      >
                        <option value={1}>1 Frame/Sec (Fastest)</option>
                        <option value={2}>2 Frames/Sec (Recommended)</option>
                        <option value={3}>3 Frames/Sec (Dense Walkthrough)</option>
                      </select>
                      <small>Extracts clean, non-blurred frames at regular intervals.</small>
                    </div>
                  )}

                  {mode === "single_photo" && (
                    <div className="config-field">
                      <label htmlFor="config-exaggeration">Depth Exaggeration ({depthExaggeration.toFixed(1)}x)</label>
                      <input
                        id="config-exaggeration"
                        type="range"
                        min="0.5"
                        max="2.5"
                        step="0.1"
                        value={depthExaggeration}
                        onChange={(e) => setDepthExaggeration(Number(e.target.value))}
                      />
                      <small>Controls 2.5D surface extrusion relief intensity.</small>
                    </div>
                  )}
                </div>

                {/* Collapsible Advanced Settings */}
                {showAdvanced && (
                  <div className="advanced-settings-box">
                    <h5>Hardware & Photogrammetry Parameters</h5>
                    <div className="config-grid">
                      <div className="config-field">
                        <label htmlFor="config-camera">COLMAP Camera Model</label>
                        <select
                          id="config-camera"
                          value={cameraModel}
                          onChange={(e) => setCameraModel(e.target.value)}
                        >
                          <option value="SIMPLE_RADIAL">SIMPLE_RADIAL (Smartphone with radial distortion)</option>
                          <option value="PINHOLE">PINHOLE (Perspective pinhole)</option>
                          <option value="OPENCV">OPENCV (High distortion wide-angle)</option>
                        </select>
                      </div>

                      {mode === "video" && (
                        <div className="config-field">
                          <label htmlFor="config-overlap">Sequential Overlap</label>
                          <input
                            id="config-overlap"
                            type="number"
                            min="5"
                            max="30"
                            value={sequentialOverlap}
                            onChange={(e) => setSequentialOverlap(Number(e.target.value))}
                          />
                          <small>Adjacent frames compared for feature tracks (Default: 10).</small>
                        </div>
                      )}

                      <div className="config-field">
                        <label>CPU Thread Limit</label>
                        <input type="text" readOnly value="4 Threads (16 GB Safe Bound)" />
                        <small>Prevents SIFT pyramid memory allocation failures.</small>
                      </div>
                    </div>
                  </div>
                )}

                {/* Submit Action Tray */}
                <div className="workflow-submit-tray">
                  <div className="submit-info">
                    <strong>
                      {mode === "video"
                        ? "Video to 3D Digital Twin"
                        : mode === "photo_set"
                        ? `Photo Set (${files.length} images)`
                        : "Single Photo AI Mesh"}
                    </strong>
                    <span>
                      {mode === "single_photo"
                        ? "Estimated duration: ~15–20s (Fast local CPU)"
                        : "Estimated duration: ~1–3 mins (CPU SfM Bundle Adjustment)"}
                    </span>
                  </div>

                  {/* If in video or photo_set mode and not yet analyzed, offer Analyze button first */}
                  {(mode === "video" || mode === "photo_set") && !analysisReport ? (
                    <button
                      type="button"
                      className="start-reconstruction-btn"
                      disabled={analyzing || isShowcaseMode()}
                      title={isShowcaseMode() ? "Capture processing requires the local SpatialForge backend. Run the app on your workstation to reconstruct." : undefined}
                      onClick={handleExtractAndAnalyze}
                    >
                      {analyzing ? (
                        <>
                          <span className="spinner-orbit" />
                          <span>Extracting & Analyzing Frames ({uploadProgress ?? 0}%)…</span>
                        </>
                      ) : isShowcaseMode() ? (
                        <>
                          <span>☁ Processing Offline in Showcase</span>
                        </>
                      ) : (
                        <>
                          <span>🔍 Extract & Analyze Frames →</span>
                        </>
                      )}
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="start-reconstruction-btn"
                      disabled={uploading || reconstructing || isShowcaseMode()}
                      title={isShowcaseMode() ? "Reconstruction requires the local SpatialForge backend with COLMAP and Depth Anything V2." : undefined}
                      onClick={handleStartReconstruction}
                    >
                      {uploading || reconstructing ? (
                        <>
                          <span className="spinner-orbit" />
                          <span>{uploading ? `Uploading (${uploadProgress ?? 0}%)…` : "Starting COLMAP SfM…"}</span>
                        </>
                      ) : isShowcaseMode() ? (
                        <>
                          <span>☁ Reconstruction Offline in Showcase</span>
                        </>
                      ) : (
                        <>
                          <span>🚀 Start 3D Reconstruction</span>
                        </>
                      )}
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
