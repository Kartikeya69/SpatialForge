# SpatialForge — System Architecture

This document describes the end-to-end architecture, component relationships, data flow, and runtime boundaries of **SpatialForge**, an indoor 3D reconstruction and browser-based spatial exploration platform built for **Techfest Round 1: 3D Reconstruction & Roaming**.

---

## 1. High-Level Architecture Diagram

```mermaid
flowchart TD
    subgraph Client["Frontend Client (React 18 + Vite + Three.js)"]
        UI["Capture & Workflow UI\n(CreateWorkflowView)"]
        Dash["Processing Dashboard\n(ProcessingDashboard)"]
        SceneLib["Scene Library & Selection\n(MyScenesView / SceneLibrary)"]
        Viewer["3D WebGL Viewport\n(Three.js / React Three Fiber)"]
        Diag["Telemetry & Diagnostics Panel\n(DiagnosticsPanel)"]
    end

    subgraph API["Backend API Gateway (FastAPI + Uvicorn)"]
        UploadEP["/api/v1/capture/upload\n(Chunked Streaming Upload)"]
        JobsEP["/api/v1/pipeline/jobs\n(Async Job Tracking & Cancel)"]
        ScenesEP["/api/v1/scenes\n(Manifest & Asset Delivery)"]
        HealthEP["/api/v1/health\n(System & Hardware Telemetry)"]
    end

    subgraph Engine["Processing & Reconstruction Engine"]
        Ingest["Media Ingestion & Demux\n(OpenCV VideoCapture / ExifTool)"]
        Analysis["Quality & Keyframe Analysis\n(Laplacian Blur & Histogram De-dup)"]
        Worker["Reconstruction Worker\n(Multi-Threaded Async Execution)"]
        
        subgraph Backends["Reconstruction Backends"]
            COLMAP["Structure-from-Motion (COLMAP)\n- SIFT Feature Extraction\n- Sequential / Vocab Matcher\n- Global Bundle Adjustment"]
            DepthAny["Monocular Depth (Depth Anything V2)\n- ONNX Runtime CPU Provider\n- Bilateral Depth Filtering\n- Discontinuity Topology Bounding"]
        end
    end

    subgraph Storage["Scene Asset & Metadata Repository (datasets/)"]
        RawMedia["input/\n(Source MP4, JPG, PNG)"]
        Keyframes["images/\n(Sharp Selected Frames)"]
        Assets["assets/\n(sparse.ply, mesh.ply, texture.jpg)"]
        Metadata["metadata/\n(scene_manifest.json, camera_poses.json,\ndepth_diagnostics.json, colliders.json)"]
    end

    %% Flow connections
    UI -->|1. Upload Video / Photos| UploadEP
    UploadEP -->|Save Stream| RawMedia
    UploadEP -->|Enqueue Job| Worker
    Worker -->|2. Extract Frames| Ingest
    Ingest -->|Raw Frames| Analysis
    Analysis -->|3. Filtered Keyframes| Keyframes
    Analysis -->|Select Mode| Worker

    Worker -->|Multi-View SfM| COLMAP
    Worker -->|Single-Image 2.5D| DepthAny

    COLMAP -->|4. Sparse Points & Poses| Assets
    DepthAny -->|4. Clean Mesh & UVs| Assets
    COLMAP -->|5. Assemble Metadata| Metadata
    DepthAny -->|5. Diagnostics & Manifest| Metadata

    Dash -->|Poll Job Status| JobsEP
    JobsEP -->|Read Job State| Worker

    Viewer -->|6. Request Manifest & Assets| ScenesEP
    ScenesEP -->|Serve PLY / JPG / JSON| Storage
    Viewer -->|Telemetry & Render Info| Diag
    SceneLib -->|Query Available Scenes| ScenesEP
```

---

## 2. Processing Pipeline & State Machine

Every capture job follows an asynchronous lifecycle managed by `PipelineJobManager`:

```mermaid
stateDiagram-v2
    [*] --> queued: User initiates capture
    queued --> processing: Worker claims job
    
    state processing {
        [*] --> image_validation: Validate format & dimensions
        image_validation --> frame_extraction: Sample video (2.0 fps)
        frame_extraction --> frame_analysis: Blur & duplicate filtering
        frame_analysis --> feature_extraction: SIFT feature detection
        feature_extraction --> feature_matching: Sequential / Vocab match
        feature_matching --> bundle_adjustment: Sparse triangulate & refine
        bundle_adjustment --> packaging: Generate scene_manifest.json
        packaging --> [*]
    }
    
    processing --> completed: All stages succeed & verified
    processing --> failed: Resource limit, timeout, or SfM failure
    processing --> cancelled: User aborted job
    
    completed --> [*]
    failed --> [*]
    cancelled --> [*]
```

### Job States:
- **`queued`**: Job metadata persisted to disk; waiting for reconstruction worker thread.
- **`processing`**: Background execution active. Sub-stages report granular progress:
  - `image_validation`: Verifies dimensions, MP limits, and format compatibility.
  - `frame_extraction` / `frame_analysis`: Decodes video and runs Laplacian variance blur rejection.
  - `depth_inference`: (Single-photo) Executes ONNX runtime inference.
  - `geometry_generation`: (Single-photo) Runs pinhole backprojection and topology boundary filtering.
  - `feature_extraction` / `matching` / `bundle_adjustment`: (COLMAP) Runs multi-view reconstruction.
  - `packaging`: Assembles `scene_manifest.json`, validates viewer bundle assets, and records checksums.
- **`completed`**: Viewer pack verified; scene ready for WebGL rendering.
- **`failed`**: Detailed diagnostic error logged without crashing the backend service.

---

## 3. Coordinate System & Transformations

SpatialForge maintains an explicit mathematical decoupling between **Reconstruction Source Space** and **Viewer World Space**:

1. **Viewer World Convention**:
   - Right-handed coordinate system.
   - $+Y$ points **Up** (world zenith).
   - $-Z$ points **Forward** (view direction into scene).
   - $+X$ points **Right**.
2. **Coordinate Matrix**:
   - Every `scene_manifest.json` specifies `coordinate_system.source_to_scene_matrix_row_major`.
   - The Three.js viewer wraps the primary visual assets in a top-level `<group matrix={sourceToScene} matrixAutoUpdate={false}>`, applying the transformation matrix directly to vertices on the GPU.

---

## 4. Architectural Boundaries & Security Guarantees

- **No Full Video Buffering**: Video streams are read frame-by-frame via OpenCV generators to ensure operation within 16 GB host RAM.
- **Path Traversal Protection**: Scene and asset API routes use strict path resolution checks. Paths containing `..` or targeting outside `datasets/` are blocked with HTTP 400/403.
- **Subprocess Isolation**: External binaries (COLMAP) run as isolated argument-list subprocesses with configured timeouts, per-stage log capture, and clean signal termination.
- **Progressive Asset Loading**: The viewer dynamically switches between GLTF/GLB models, PLY point clouds, and textured PLY meshes through a declarative renderer registry, applying React Suspense boundaries.
