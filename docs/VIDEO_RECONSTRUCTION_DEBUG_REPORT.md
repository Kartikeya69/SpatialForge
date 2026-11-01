# SpatialForge Video Reconstruction & 3D Viewer Engineering Report

**Investigation & Repair Reference:** `SPATIALFORGE-VID-2026-001`  
**Target Scene:** `scene_20261031T132349Z_4bfe84b483`  
**System Architecture:** SpatialForge Hybrid Photogrammetry & Neural Depth Engine  
**Author:** Principal Computer Vision & WebGL Specialist / QA Lead  
**Date:** 2026-10-31  

---

## Executive Summary

Single-photo reconstruction in SpatialForge previously displayed approximate 2.5D visual depth geometry because the single-image neural depth model (Depth Anything V2 ONNX) operates on a small normalized coordinate frame ($[-1.0, 1.4]$ units) close to the origin, exported as a connected surface mesh (`ply_mesh`).

In contrast, real video multi-view reconstruction utilizes sequential Structure-from-Motion (COLMAP) to reconstruct real physical coordinate spaces with a broad metric/SfM span ($86.18$ units across $[ -47.14, 39.04 ] \times [ -13.55, 25.11 ] \times [ 1.39, 80.27 ]$) and exports a sparse feature point cloud (`sparse.ply`). Although COLMAP successfully registered 19 of 22 extracted frames with sub-pixel reprojection error ($0.73$ px) and exported 987 validated 3D vertices, **Viewer 2.0 displayed a completely blank screen**.

Our root-cause investigation revealed **three intersecting defects across scene packaging, Three.js projection, and WebGL rendering** that caused genuine 3D geometry to be completely obscured and discarded. All three issues have been diagnosed, repaired, and verified with automated test coverage.

---

## 1. Reproduction & Stage-by-Stage Evidence

We audited all 9 stages of the video reconstruction pipeline for `scene_20261031T132349Z_4bfe84b483`:

| Stage | Expected Artifact | Actual State | Evidence / Metrics |
| :--- | :--- | :--- | :--- |
| **1. Video Decoding** | Valid MP4 stream | **Success** | `input/capture.mp4`: 854×480, 537 frames @ 29.99 fps (17.90s), 3.88 MB |
| **2. Frame Sampling & Filter** | Extracted sharp keyframes | **Success** | 36 sampled frames at 2.0 fps; 14 blurry frames filtered out; **22 sharp frames accepted** (Laplacian variance 89.3 – 674.3) |
| **3. SIFT Feature Extraction** | `database.db` with keypoints | **Success** | CPU SIFT extraction via `colmap.exe` completed with exit code 0 |
| **4. Feature Matching** | Inlier two-view tracks | **Success** | Sequential matcher with overlap 10; verification completed with exit code 0 |
| **5. Sparse Mapping** | `points3D.bin`, `images.bin` | **Success** | 1 submodel reconstructed; **19 registered images (86.4%)**, mean reprojection error **0.731 px** (median 0.623 px), mean track length 5.39 |
| **6. Geometry Export** | `sparse.ply` | **Success** | `reconstruction/colmap/exports/sparse.ply`: 14,992 bytes, binary little-endian PLY, **987 vertices**, finite coordinates, RGB per-vertex colors |
| **7. Camera Poses Export** | `camera_poses.json` | **Success** | `reconstruction/colmap/exports/camera_poses.json`: 32,544 bytes, 19 registered camera positions ($x, y, z$) and quaternions |
| **8. Scene Packaging** | `scene_manifest.json` | **Defective** | Hardcoded sub-pixel point size ($0.025$) and inverted yaw ($0.0^\circ$ facing $-Z$, whereas points were at $+Z$) |
| **9. Three.js / WebGL Rendering** | Visible 3D twin in viewport | **Defective (BLANK)** | **Hardcoded linear fog ($18 \dots 42$ units) completely obscured all points**, and point attenuation rounded point diameters to $< 0.18$ px, causing hardware rasterization discard |

---

## 2. Root Cause Analysis

### Cause A: Hardcoded Indoor Fog Blended Geometry Into Background Sky
In `frontend/src/viewer/SceneViewport.tsx`, the Three.js viewport included a fixed linear fog:
```tsx
<fog attach="fog" args={[manifest.viewer.background, 18, 42]} />
```
- For the tiny single-photo room preview, all geometry was located within $Z \in [-3.0, -0.7]$, well inside the 18-unit fog onset.
- For the video COLMAP reconstruction, the point cloud span is $86.18$ units, with points centered around $Z = 33.92$ (ranging up to $80.27$). OrbitControls positioned the orbit camera at $\approx 99.2$ units distance from the center.
- Linear fog computes:
  $$\text{fogFactor} = \text{clamp}\left(\frac{42 - \text{distance}}{42 - 18}, 0.0, 1.0\right) = 0.0 \quad (\text{for all } \text{distance} \ge 42)$$
- At distance 99.2, **every single pixel rendered was replaced with 100% fog color** (`#06131d`, identical to the background sky). The viewport was literally drawing the 3D points in the background color.

### Cause B: Sub-Pixel Attenuation Discarded Sparse Points
In `spatialforge/scenes/assemble.py`, the viewer pack generator declared:
```json
"viewer": { "point_size": 0.025 }
```
In `frontend/src/viewer/SceneAssets.tsx`, `pointsMaterial` enabled `sizeAttenuation={true}`. In perspective projection, projected screen size in pixels is:
$$\text{pointDiameter}_{\text{px}} = \text{pointSize} \times \frac{\text{viewportHeight}}{2 \cdot \tan(\text{fov} / 2) \cdot \text{distance}}$$
With `pointSize = 0.025`, `viewportHeight = 800`, `fov = 68°`, and `distance = 99.2`:
$$\text{pointDiameter}_{\text{px}} = 0.025 \times \frac{800}{133.8} \approx 0.15 \text{ pixels}$$
In WebGL rasterization, point primitives smaller than $0.5$ pixels fail pixel-center inclusion tests and are discarded by the GPU fragment generator.

### Cause C: Inverted Camera Spawn Yaw in First-Person Mode
COLMAP cameras look along positive $+Z$ into the reconstructed point cloud ($Z \in [1.39, 80.27]$). In `assemble.py`, `spawn_yaw_degrees` was hardcoded to $0.0^\circ$. In Three.js, yaw $0^\circ$ points towards $-Z$. Switching to First-Person mode turned the camera directly away from the reconstructed scene into empty space.

### Cause D: Lack of Viewer Pack Validation
The pipeline previously lacked an automated geometry verification gate. A viewer pack could declare `processing_status: "completed"` without verifying whether the primary visual asset was non-empty, had finite coordinates, or could be rendered by WebGL.

---

## 3. Engineering Repairs Implemented

### 1. Robust Viewer Pack Validation Engine (`spatialforge/scenes/validate.py`)
Created a standalone, thorough validation utility `validate_viewer_pack(scene_dir)`:
- Verifies `metadata/scene_manifest.json` schema and assets integrity.
- Confirms zero path traversal (`../`) for all declared files.
- Inspects PLY binary headers: rejects empty PLY files (element vertex $\le 0$), parses vertex elements, and enforces that all coordinates are finite ($\neg\text{NaN}, \neg\text{Inf}$).
- Inspects GLB containers: verifies `glTF` magic header and minimum byte length.
- Verifies camera poses and calculates real metric span and center coordinates.
- Exposed via backend endpoint: `GET /api/v1/scenes/{scene_id}/validate-viewer-pack`.

### 2. Upgraded Scene Packaging (`spatialforge/scenes/assemble.py`)
- **Adaptive Point Size**: Dynamically scales `viewer.point_size = round(max(0.15, min(0.65, span / 180.0)), 4)`. For `scene_20261031T132349Z_4bfe84b483`, point size is now `0.4788` (a 19× increase), rendering crisp $\approx 3.5\text{ px}$ points.
- **Directional Spawn Yaw**: Computes `spawn_yaw_degrees = math.degrees(math.atan2(dx, -dz))` pointing directly from camera position to the geometry center ($178.7^\circ$).
- **Overwrite & Validation Gate**: Added `overwrite: bool = True` and runs `validate_viewer_pack(scene)` before persisting. If validation fails, raises `SceneAssemblyError` and does not publish corrupt manifests.

### 3. Adaptive Fog & Viewport Projection (`frontend/src/viewer/SceneViewport.tsx`)
- Replaced hardcoded $18 \dots 42$ fog with bounds-adaptive distances:
  $$\text{fogNear} = \max(\text{span} \times 3.5, 120), \quad \text{fogFar} = \max(\text{span} \times 10.0, 500), \quad \text{cameraFar} = \max(\text{span} \times 30, 2500)$$
- Never envelopes the reconstructed object in opaque fog.

### 4. High-Visibility Point Cloud Material (`frontend/src/viewer/SceneAssets.tsx`)
- Set `fog={false}` on `pointsMaterial`: Point clouds are never fogged out regardless of zoom level or distance.
- Effective point size floor: `Math.max(pointSize || 0.35, span / 200, 0.25)`.
- Bounding sphere calculation: Calls `geometry.computeBoundingBox()` and `computeBoundingSphere()` upon loading.
- Scales camera station spheres and trajectory lines proportionally to the scene span.

### 5. Instant Camera Auto-Framing (`frontend/src/viewer/CameraModeRig.tsx` & `App.tsx`)
- Added **Frame Scene** action (`⛶ Frame Scene` button in toolbar, keyboard shortcut `F`):
  Fits the entire reconstruction into the viewport by positioning the camera at optimal distance $d = \text{span} \times 1.15$ looking directly at the bounding box center.
- In first-person mode, frames the yaw directly towards the center of geometry.

### 6. Comprehensive Reconstruction Diagnostics Panel (`frontend/src/components/DiagnosticsPanel.tsx`)
Added real-time developer diagnostics panel displaying:
- Scene ID, backend (`COLMAP`), viewer pack validation status (`✓ Verified Ready`).
- Geometry format (`ply`), declared assets, registered camera poses ($19$).
- Live point count ($987$) and triangle count ($0$).
- Bounding box coordinates, center, and real-time distance from camera to center.
- Near/Far planes, FOV ($68^\circ$), yaw angle, WebGL context status, draw calls.
- One-click **⛶ Frame Scene** button.

---

## 4. Verification & Validation Results

### Backend Automated Test Suite
- Executed `pytest -q`: **103 of 103 tests passed** (including 6 new dedicated tests in `tests/test_viewer_pack_validation.py`):
  - `test_validate_viewer_pack_rejects_empty_ply` (PASSED)
  - `test_validate_viewer_pack_rejects_non_finite_coordinates` (PASSED)
  - `test_assemble_reconstruction_calculates_adaptive_point_size_and_yaw` (PASSED)
  - `test_validate_viewer_pack_rejects_missing_geometry` (PASSED)
  - `test_backend_validate_viewer_pack_endpoint` (PASSED)
  - `test_backend_asset_delivery_endpoints` (PASSED)

### Frontend Automated Test Suite
- Executed `npm test -- --run`: **35 of 35 tests passed** across 17 test suites:
  - `SceneViewport.test.tsx` (PASSED)
  - `App.test.tsx` (PASSED)
  - `ProcessingDashboard.test.tsx` (PASSED)
  - `SceneLibrary.test.tsx` (PASSED)
  - `NavigationSearch.test.tsx` (PASSED)

### Production Build
- `npm run build`: Compiled cleanly into `dist/assets/index-BghcB-_z.js` and `dist/assets/SceneViewport-exSISNcF.js` with 0 TypeScript errors.

### Real Scene Verification (`scene_20261031T132349Z_4bfe84b483`)
- `GET /api/v1/scenes/scene_20261031T132349Z_4bfe84b483/validate-viewer-pack`:
  ```json
  {
    "is_valid": true,
    "scene_id": "scene_20261031T132349Z_4bfe84b483",
    "scene_type": "colmap_reconstruction",
    "visual_asset_path": "reconstruction/colmap/exports/sparse.ply",
    "geometry_format": "ply",
    "point_count": 987,
    "camera_pose_count": 19,
    "span": 86.1852,
    "errors": [],
    "warnings": []
  }
  ```
- Geometry: 987 crisp, colored 3D points rendered in the 3D canvas alongside the 19 registered camera positions.
- Camera: Orbit controls centered on $( -4.05, 5.78, 40.83 )$ with auto-framing.

---

## 5. Summary of Files Changed

| File | Changes |
| :--- | :--- |
| `spatialforge/scenes/validate.py` | Created viewer pack integrity verification engine (validates PLY, GLB, poses, coordinates). |
| `spatialforge/scenes/assemble.py` | Added adaptive point size, directional yaw, overwrite support, and validation gate. |
| `spatialforge/api/main.py` | Added `GET /api/v1/scenes/{scene_id}/validate-viewer-pack` and wired automated validation in reconstruction. |
| `frontend/src/viewer/SceneViewport.tsx` | Bounds-adaptive fog, bounds-adaptive camera far, geometry info hook, frameScene token. |
| `frontend/src/viewer/SceneAssets.tsx` | `fog={false}` on pointsMaterial, adaptive point size floor, bounding sphere computation, scaled camera trajectory markers. |
| `frontend/src/viewer/CameraModeRig.tsx` | Auto-framing handler (`frameSceneToken`), telemetry near/far/fov/status reporting. |
| `frontend/src/viewer/PerformanceProbe.tsx` | Memory geometries/textures reporting. |
| `frontend/src/components/DiagnosticsPanel.tsx` | Upgraded to developer diagnostics panel with real runtime measurements and ⛶ Frame Scene action. |
| `frontend/src/App.tsx` | Added Frame Scene toolbar button (`⛶`), keyboard shortcut `F`, wired telemetry & diagnostics panel. |
| `frontend/src/api.ts` | Added `validateViewerPack()` client endpoint. |
| `frontend/src/types.ts` | Declared `ViewerPackValidation`, expanded `CameraTelemetry` and `RenderMetrics`. |
| `frontend/src/styles.css` | Styled expanded Diagnostics Panel and toolbar buttons. |
| `tests/test_viewer_pack_validation.py` | Added comprehensive automated test suite covering 6 edge cases and contracts. |

---

## 6. Remaining Considerations for Techfest

1. **Sparse vs. Dense Geometry**:
   - The video pipeline currently executes COLMAP sparse reconstruction, producing an authentic, calibrated 3D point cloud with camera orbits.
   - For a full room mesh, dense stereo matching (MVS) or Delaunay meshing can be integrated as an optional post-processing pass when GPU compute is present, but for CPU-only laptop demonstrations, the sparse point cloud with camera stations is genuine, real-time, and stable.
2. **First-Person Navigation in Point Clouds**:
   - Navigation is disabled for sparse point clouds because there are no solid floor collider polygons. First-person looking and Orbit mode are fully supported.
