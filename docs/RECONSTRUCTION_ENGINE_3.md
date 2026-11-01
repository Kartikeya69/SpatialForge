# SpatialForge — Reconstruction Intelligence Engine 3.0
**Production Engineering & Architectural Specification**

---

## 1. Executive Summary

SpatialForge Reconstruction Intelligence Engine 3.0 upgrades the three core reconstruction pipelines—**Single-Photo AI Depth**, **Multi-Photo COLMAP Photogrammetry**, and **Video-to-3D Reconstruction**—into a unified, resource-aware, and failure-resilient 3D spatial reconstruction engine designed specifically for Intel integrated graphics and 16 GB RAM hardware constraints.

The upgrade completely resolves the critical blank-viewer defect in video reconstruction, eliminates aspect-ratio stretching in single-photo monocular inference, introduces a strict validation gate preventing empty viewer packs, and equips Viewer 2.0 with developer diagnostics, auto-framing, and an honest unified quality reporting engine.

---

## 2. P0 Resolution: Video Reconstruction & Blank 3D Viewer

### Target Scene Audited
`scene_20261031T132349Z_4bfe84b483` (Video Capture: 104 extracted frames, 19 registered camera poses, 987 sparse 3D COLMAP vertices, span: 86.18 units).

### Root-Cause Triad
1. **Linear Fog Occlusion**: `SceneViewport.tsx` hardcoded a fixed three.js fog range `[18, 42]`. The reconstructed video point cloud had a spatial span of 86.18 units, and the default orbit camera was positioned at a Euclidean distance of 99.2 units from the centroid. At $d > 42$, Three.js linear fog colored 100% of the points with the background canvas color (`#06131d`), rendering the geometry completely invisible without generating any WebGL error.
2. **Sub-Pixel Point Rasterization**: Under perspective projection with `sizeAttenuation=true`, a world-space point size of $0.025$ at a viewing distance of $\sim 99$ units projected points to $< 0.18$ screen pixels, which WebGL hardware rasterizers discarded.
3. **Inverted Spawn Yaw**: Sparse COLMAP reconstruction points were clustered at $+Z$, while the initial camera yaw was oriented toward $-Z$ ($0^\circ$).

### Permanent Fixes Implemented
- **Bounds-Adaptive Fog & Far Planes** ([`SceneViewport.tsx`](file:///frontend/src/viewer/SceneViewport.tsx)): Fog `near` and `far` scale dynamically with scene span:
  $$\text{fog.near} = \text{span} \times 3.5, \quad \text{fog.far} = \text{span} \times 10.0, \quad \text{camera.far} = \max(2500, \text{span} \times 12.0)$$
- **Zero-Fog Point Materials** ([`SceneAssets.tsx`](file:///frontend/src/viewer/SceneAssets.tsx)): Point clouds now explicitly enforce `fog={false}` on `pointsMaterial`. Point size scales adaptively with scene span ($\text{point\_size} = \max(0.012, \text{span} / 180)$).
- **Auto-Framing (`⛶ Frame Scene`)** ([`CameraModeRig.tsx`](file:///frontend/src/viewer/CameraModeRig.tsx)): Added automated bounds framing that positions the camera at the optimal viewing distance $D = \frac{\text{span}}{2 \tan(\text{FOV} / 2)} \times 1.45$.

---

## 3. Strict Viewer-Pack Validation Gate

Created [`spatialforge/scenes/validate.py`](file:///spatialforge/scenes/validate.py) with the `validate_viewer_pack()` engine and exposed endpoint `GET /api/v1/scenes/{scene_id}/validate-viewer-pack`:
- **Header & Format Integrity**: Validates ASCII PLY headers, magic bytes (`b"glTF"` for GLB), vertex element counts, and face element counts.
- **Coordinate Finiteness**: Reads binary/ASCII point coordinates and strictly checks $\forall v \in V, \, \text{isfinite}(v)$.
- **Non-Empty Geometry Guarantee**: A scene is rejected if vertex count is 0 or if declared visual assets are missing from disk.
- **Atomic Assembly Guard**: In `assemble_reconstructed_scene()`, the validation gate executes before marking a scene completed; if validation fails, the job status is set to `failed` and partial files are removed.

---

## 4. Intelligent Input Media Analyzer

Implemented [`spatialforge/engine/analysis/media_analyzer.py`](file:///spatialforge/engine/analysis/media_analyzer.py) to provide CPU-fast, resource-bounded computer vision analysis:
- **Sharpness**: Laplacian operator variance ($\sigma^2(\nabla^2 I)$).
- **Exposure & Contrast**: Greyscale mean brightness, standard deviation, and under/overexposure pixel percentage thresholds.
- **Feature Richness**: OpenCV FAST feature detector calculating keypoint density per megapixel.
- **Texture Analysis**: Sobel gradient magnitude measuring the percentage of low-texture flat surfaces.
- **Pairwise Overlap & Diversity**: ORB descriptors with Lowe's ratio test and RANSAC homography estimation, measuring inlier count, displacement, and angular diversity across multi-view photo sets and video sequences.

---

## 5. Advanced Single-Photo AI Pipeline

Refactored [`spatialforge/engine/reconstruction/single_image.py`](file:///spatialforge/engine/reconstruction/single_image.py):
1. **Dynamic Multiple-of-14 Aspect-Ratio Preservation**: Depth Anything V2 requires input dimensions to be divisible by 14. Instead of squashing images into an arbitrary $518 \times 518$ square (which warped portrait images by over 23%), the engine dynamically computes:
   $$\text{scale} = \frac{\text{input\_size}}{\max(H, W)}, \quad H_{\text{target}} = \text{round}\left(\frac{H \cdot \text{scale}}{14}\right) \times 14, \quad W_{\text{target}} = \text{round}\left(\frac{W \cdot \text{scale}}{14}\right) \times 14$$
   Preserving genuine optical proportions without distortion or wasted padding compute.
2. **Singleton ONNX Session Caching**: The ONNX runtime session and execution provider are cached in-memory across requests, cutting inference latency from $> 15$ seconds to **$< 0.9$ seconds** on CPU.
3. **Edge-Aware Bilateral Depth Refinement**: Combines edge-preserving bilateral filtering with multi-scale Canny and Sobel gradient magnitude masking, preserving crisp structural step boundaries across furniture, kitchen islands, and doorways.
4. **Adaptive Discontinuity Triangulation**: Back-projects relative depth to camera space and triangulates only continuous local cells, eliminating foreground-background "rubber-sheet" tearing.

---

## 6. Unified Quality Report

Created [`spatialforge/engine/quality/report.py`](file:///spatialforge/engine/quality/report.py) and exposed `GET /api/v1/scenes/{scene_id}/quality-report`.

### Real Verification Benchmark

| Metric / Attribute | Living Room Aerial (`scene_20261031T142500Z_livingroom_preview`) | Video SfM (`scene_20261031T132349Z_4bfe84b483`) |
| :--- | :--- | :--- |
| **Pipeline Type** | Single-Photo 2.5D Monocular AI | Multi-View Video COLMAP SfM |
| **Status** | Completed (`is_valid = True`) | Completed (`is_valid = True`) |
| **Confidence Score** | **90%** | **50%** (Honest rating for sparse point cloud) |
| **Point Count** | **82,280 points** | **987 points** |
| **Triangle / Face Count**| **161,613 faces** | 0 faces (Point cloud) |
| **Bounding Box Span** | 2.57 units | 86.18 units |
| **Inference / Solve Time**| **0.89 seconds** (CPU) | ~4 minutes (COLMAP CPU) |
| **Scale Status** | Arbitrary Non-Metric | Arbitrary Non-Metric |
| **Primary Visual Asset** | `assets/single-photo-depth-mesh.ply` | `reconstruction/colmap/exports/sparse.ply` |

---

## 7. Developer Diagnostics & UI Studio

- **Developer Diagnostics Panel** ([`DiagnosticsPanel.tsx`](file:///frontend/src/components/DiagnosticsPanel.tsx)): Live telemetry showing FPS, draw calls, triangle/point counts, bounding box coordinates, camera distance, near/far planes, WebGL active context, and unified quality confidence.
- **Frame Scene Action**: Instant one-click `⛶ Frame Scene` fits the camera viewport around loaded geometry.
- **Studio Interface** ([`ProcessingDashboard.tsx`](file:///frontend/src/components/ProcessingDashboard.tsx)):
  - 3 dedicated capture mode tabs (Photo set, Video, Single photo) with feature badges.
  - Interactive radar status card visualizing active reconstruction stages.
  - Interactive guidance prompts ("Yes, Analyze Capture Quality", "Start 3D COLMAP Reconstruction Now").
  - History management with single-job deletion and bulk clear for failed jobs (`POST /api/v1/pipeline/jobs/clear-history`).

---

## 8. Hardware & Dependency Constraints

- **Compute Mode**: Strictly CPU-first execution (`CPUExecutionProvider` in ONNX Runtime; CPU feature extraction and matching in COLMAP).
- **RAM Headroom**: Profile guards (`fast`: 128 MB, `balanced`: 768 MB, `quality`: 1536 MB headroom) checked via `GlobalMemoryStatusEx` before pipeline launch, preventing out-of-memory crashes on 16 GB systems.
- **GPU Compatibility**: Intel integrated graphics verified via WebGL 2.0 without CUDA dependencies.
