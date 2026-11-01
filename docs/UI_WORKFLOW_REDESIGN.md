# SpatialForge — UI/UX Reorganization and Workflow Integration
**Production Architectural Documentation & Implementation Report**

---

## 1. Overview & Architecture

SpatialForge has been reorganized into a unified, clean, and intuitive capture-to-spatial-viewer workflow. The user interface connects the three core pipelines (**Photo Set Photogrammetry**, **Video Reconstruction**, and **Single-Photo AI Depth**) with a persistent application navigation model comprising five top-level workspaces:

```
[ ⊞ Dashboard | ▤ My Scenes | ◫ Processing | ⚙ Settings | ◈ 3D Viewer ]
```

- **Dashboard**: High-level overview, 3 bespoke capture launch cards, active processing job radar alerts, system status, and recent scene cards with 1-click **Open in Viewer** buttons.
- **My Scenes**: Comprehensive digital twin library displaying real scene metadata, validated geometry counts, inline renaming, `.sfscene` package export, safe deletion, and direct viewer launch.
- **Processing Studio**: Dedicated capture & reconstruction workspace with 3 independent capture workflows, live radar status sweeps, multi-view overlap guidance, and safe history management.
- **Settings & System Diagnostics**: Hardware telemetry (Intel CPU mode, physical RAM headroom), ONNX Runtime & COLMAP engine verification, processing profile thresholds, and storage disk consumption.
- **3D Viewer (Viewer 2.0)**: Hardware-accelerated Three.js canvas featuring bounds-adaptive fog, zero-fog point clouds, auto-framing (`⛶ Frame Scene`), orbit/walk/overview camera controls, minimap, and live developer diagnostics.

---

## 2. Priority 1: Scene Access & Verification

### Target Scene: `scene_20261031T132349Z_4bfe84b483` (Video SfM)
- **Input Type**: Video Capture (104 extracted frames, 19 registered cameras).
- **Reconstruction Output**: 987 sparse 3D COLMAP vertices, span: 86.18 units.
- **Verification Status**: `is_valid: True` via [`validate_viewer_pack()`](file:///spatialforge/scenes/validate.py).
- **Navigation Path**: Available on **Dashboard → Recent Scenes** and **My Scenes → Video SfM Filter**. Clicking **Open in Viewer** loads the scene directly in Viewer 2.0 with bounds-adaptive fog ($\approx 300\dots 860$ units) and auto-framing at optimal viewing distance ($\approx 99.2$ units).

### Single-Photo AI Scene: `scene_20261031T142500Z_livingroom_preview` (Living Room Aerial)
- **Input Type**: Single Photo AI Depth (Depth Anything V2 Small ONNX).
- **Reconstruction Output**: 82,280 vertices, 161,613 triangles, span: 2.57 units.
- **Inference Latency**: 0.89 seconds (local CPU inference via cached session).
- **Quality Score**: 90% confidence with dynamic multiple-of-14 aspect-ratio preservation.

---

## 3. Five Primary Application Workspaces

### A. Dashboard (`DashboardView.tsx`)
- **System Ready Pill**: Displays real-time CPU execution mode, Intel integrated graphics compatibility, and 16 GB RAM headroom.
- **Active Job Alert Banner**: Dynamically appears when a background reconstruction job is running, featuring a pulsing radar ping, current stage, and a direct `View in Processing Studio →` shortcut.
- **Three Reconstruction Launch Cards**:
  1. *Photo Set Reconstruction*: Multi-view overlap evaluation, SIFT matching, and 3D point cloud generation.
  2. *Video Reconstruction*: Automated 2 FPS keyframe sampling, motion blur filtering, and validated viewer-pack assembly.
  3. *Single-Photo AI Reconstruction*: Aspect-ratio preserving neural depth estimation with bilateral edge filtering and interactive 3D textured mesh.
- **Recent Digital Twins Grid**: Real scene cards with point/triangle/camera badges and direct **◈ Open in Viewer** actions.

### B. My Scenes (`MyScenesView.tsx`)
- **Search & Filtering**: Filter by capture type (*All Scenes*, *Single Photo AI*, *Video SfM*, *Photo Set*) or text search across scene titles, identifiers, and descriptions.
- **Scene Cards**:
  - User-friendly display name (with inline **✎ Rename** dialog updating `scene_manifest.json` on disk).
  - Scene identifier (`scene_...`) and formatted creation timestamp.
  - Validated metrics: Points, Triangles, Cameras, and Spatial Span.
  - Primary **◈ Open in Viewer** button.
  - Standalone **⤓ Export** link downloading `.sfscene` zip package with checksums.
  - Safe **🗑 Delete** button with confirmation modal explaining asset removal.
- **Package Import**: "+ Import .sfscene" button supporting drag-and-drop of portable scene archives.

### C. Processing Studio (`ProcessingDashboard.tsx`)
- **Capture-to-Reconstruction Wizard**:
  - *Step 1*: File dropzone with format validation.
  - *Step 2*: Input quality analysis (sharpness, brightness, contrast, textureless percentage).
  - *Step 3*: Profile selection (`fast`, `balanced`, `quality`) and depth exaggeration settings.
  - *Step 4*: Start Reconstruction.
  - *Step 5*: Real-time radar scanner hero card with stage timeline and guidance prompts (*"Analyze Overlap Quality"* or *"Start COLMAP Reconstruction Now"*).
- **Job Feed & History Management**:
  - Complete list of queued, processing, and completed jobs.
  - Filter by search or status.
  - Retry failed jobs and cooperative cancellation.
  - Dedicated **"Clear Failed Job Artifacts"** and **"Clear Completed Job Records"** controls.

### D. Settings & Diagnostics (`SettingsView.tsx`)
- **Hardware Telemetry**: OS, processor model, physical RAM (total/available/load %), and execution provider.
- **Model Engine Verification**:
  - `Depth Anything V2 Small ONNX`: File existence, size (98.4 MB), and ONNX Runtime CPU provider.
  - `COLMAP Photogrammetry`: Executable path and CPU sparse bundle adjustment mode.
- **Memory Profiles**: Details on `Fast` (128 MB RAM headroom), `Balanced` (768 MB RAM headroom), and `Quality` (1536 MB RAM headroom) guards.
- **Storage Management**: Dataset root location, active scene directories, and total megabytes occupied.

### E. 3D Viewer (`SceneViewport.tsx` & Viewer 2.0)
- **First-Person / Orbit / Overview Modes**: Seamless switching with collision geometry and ground navigation grid.
- **Auto-Framing (`⛶ Frame Scene`)**: Automatically centers camera on geometry bounds using bounding sphere trigonometry.
- **Developer Diagnostics Panel (`▥`)**: Live telemetry showing FPS, draw calls, triangles, points, bounding boxes, camera distance, and unified quality confidence scores.
- **Bounds-Adaptive Fog**: Prevents distant point clouds from being occluded by linear fog.

---

## 4. Backend API Integration Matrix

| Endpoint | Method | Purpose |
| :--- | :---: | :--- |
| `/api/v1/scenes` | `GET` | List all valid scenes with metadata, timestamps, and primary asset types. |
| `/api/v1/scenes/{scene_id}/manifest` | `GET` | Load full scene manifest schema. |
| `/api/v1/scenes/{scene_id}/validate-viewer-pack` | `GET` | Strict validation gate (geometry existence, point count $>0$, finite coordinates). |
| `/api/v1/scenes/{scene_id}/quality-report` | `GET` | Unified quality report with confidence score, limitations, and recommendations. |
| `/api/v1/scenes/{scene_id}/rename` | `PATCH` | Atomically rename scene display name in `scene_manifest.json`. |
| `/api/v1/scenes/{scene_id}/export` | `GET` | Stream portable `.sfscene` zip package with checksums. |
| `/api/v1/scenes/{scene_id}` | `DELETE` | Permanently remove scene directory and clean up in-memory registry. |
| `/api/v1/system/diagnostics` | `GET` | Platform, CPU/GPU, memory snapshot, model status, and storage usage. |
| `/api/v1/pipeline/jobs` | `GET` | Inspect active and historical reconstruction jobs. |
| `/api/v1/pipeline/jobs/clear-history` | `POST` | Safely purge failed/incomplete temporary files without touching valid scenes. |
| `/api/v1/pipeline/jobs/clear-completed-jobs`| `POST` | Clear in-memory completed notifications while preserving scene datasets. |

---

## 5. Verification & Test Suite Summary

- **Backend Pytest**: **104 passed** (100% of test suites, 0 failures).
- **Frontend Vitest**: **35 passed** across all 17 component and unit test suites.
- **TypeScript Compiler**: **0 errors** (`tsc -b --pretty false`).
- **Production Build**: **Successful** (`frontend/dist` with optimized Three.js bundle).
- **Development Servers**: Running on `http://127.0.0.1:8000` (FastAPI) and `http://127.0.0.1:5173` (Vite).
