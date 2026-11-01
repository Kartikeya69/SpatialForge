# SpatialForge — Reconstruction Results & Verification Benchmarks

**Submission**: Techfest Round 1: 3D Reconstruction & Roaming  
**Evaluation Scope**: Quantitative benchmarks, geometric validation, runtime performance, and representation limits across real smartphone capture pipelines.

---

## 1. Multi-View Video Reconstruction Benchmark (COLMAP SfM)

The multi-view video pipeline was evaluated on smartphone video captured under standard consumer conditions on a pure CPU host (Intel Iris/UHD integrated graphics, 16 GB RAM).

### Evaluated Scene: `scene_20261031T160047Z_cd37fab494`

| Metric Category | Parameter | Measured Value | Verification Source |
| :--- | :--- | :--- | :--- |
| **Input Media** | Video Duration | 17.90 seconds | Video demux log |
| | Input Resolution | 854 × 480 pixels | `input/capture.mp4` |
| | Total Sampled Frames | 36 frames (sampled at 2.0 fps) | `metadata/capture_manifest.json` |
| | Selected Sharp Keyframes | 22 frames | Blur & duplicate filter |
| **COLMAP Execution** | Backend & Build | COLMAP 4.2.0 (Commit `be5e291`, pure CPU) | Subprocess runner |
| | Feature Detector | SIFT (CPU, 8192 max features) | `feature_extraction.log` |
| | Matching Strategy | Sequential Matching (`sequential_overlap: 10`) | `feature_matching.log` |
| | Total Execution Duration | **64.23 seconds** | `reconstruction_manifest.json` |
| **SfM Quality** | Registered Cameras | **19 of 22 (86.36%)** | Camera pose manifest |
| | Triangulated 3D Points | **939 sparse feature points** | `reconstruction/colmap/exports/sparse.ply` |
| | Mean Reprojection Error | **0.71405 pixels** (Sub-pixel accuracy) | Bundle adjustment log |
| | Median Reprojection Error | **0.62742 pixels** | Bundle adjustment log |
| | Mean Track Length | 5.3972 observations/point | Point track registry |

### Nature of Sparse SfM Output
> [!NOTE]
> COLMAP Structure-from-Motion produces a **sparse 3D point cloud** representing distinct visual corners and textured keypoints, along with accurate **6-DoF camera trajectory poses**.
> A sparse point cloud is not a continuous watertight mesh. It provides camera localization, spatial bounding limits, and keypoint anchoring for navigation and scene layout.

---

## 2. Single-Photo Monocular Depth Reconstruction Benchmark

The single-photo 2.5D pipeline was evaluated on a single high-resolution consumer photograph using Depth Anything V2 Small ONNX running strictly on CPU.

### Evaluated Scene: `scene_20261101T035558Z_4a97da5bb5`

| Metric Category | Parameter | Measured Value | Verification Source |
| :--- | :--- | :--- | :--- |
| **Input Image** | Source File | `upload_000001.jpg` (Indoor room) | `input/` |
| | Dimensions | 960 × 1280 pixels (1.23 MP) | Image header |
| **Inference** | Model Architecture | Depth Anything V2 Small ONNX | ONNX Runtime CPU |
| | Model Input Resolution | 518 × 518 | Dynamic aspect padding |
| | Inference + Filtering Time | **24.49 seconds** | `single_image_manifest.json` |
| **Geometry Integrity** | Generated Vertices | **69,810 vertices** | `single-photo-depth-mesh.ply` |
| | Generated Triangles | **133,605 triangles** | `single-photo-depth-mesh.ply` |
| | Inverted Faces ($n_z < 0$) | **0 faces** (100% front-facing) | `validate_mesh_geometry` |
| | Clipped Cliff Discontinuities | **18,877 faces rejected** | Discontinuity filter ($\Delta d \le 0.08$) |
| | Mesh Face Retention | **87.62%** | Topology audit |
| | Mean Triangle Aspect Ratio | **1.74** (Well-conditioned) | Analytical edge ratio |
| | 99th Percentile Aspect Ratio | **4.55** (No slivers/needles) | Analytical edge ratio |
| | Maximum 3D Edge Length | **0.0546 units** (Bounded) | Euclidean distance check |
| **Viewer Integration** | Texture Asset | `assets/texture.jpg` (263 KB JPEG) | Three.js `TextureLoader` |
| | Surface Normals | Analytical $(n_x, n_y, n_z)$ | Embedded in PLY |
| | UV Coordinates | Normalized $(s, t)$ | Embedded in PLY |
| | Initial Camera Viewpoint | $(0.0, 0.0, 0.0) \to (0.0, 0.0, -2.39)$ | Matching FOV $58.11^\circ$ |
| | Parallax Orbit Bounds | Azimuth $\pm 35^\circ$, Polar $\pm 30^\circ$ | Restrained OrbitControls |

---

## 3. Second Validation Scene: `scene_20261101T041011Z_8526a98ff7`

- **Input File**: `upload_000001.png` (960 × 1280)
- **Vertices**: 67,759
- **Faces**: 127,951
- **Inverted Faces**: 0
- **Rejected Depth Jump Discontinuities**: 23,255
- **Face Retention**: 84.62%
- **Look-at Target**: $(0.0, 0.0, -2.27)$ with vertical FOV $44.90^\circ$

---

## 4. Technical Distinctions & Known Limitations

1. **2.5D Relief vs. 360° Walk-Through**:
   - Single-photo reconstruction estimates relative depth from a single optical center. It creates a 2.5D embossed relief mesh.
   - Hidden geometry behind furniture, walls, and occluding objects cannot physically be observed from one photo.
   - SpatialForge explicitly marks single-photo scenes with `is_2_5d: true` and initializes the camera at the source pinhole origin, restraining orbit to $\pm 35^\circ$ parallax to prevent users from looking behind the relief.
2. **Metric Scale Calibration**:
   - Monocular depth and uncalibrated monocular SfM have arbitrary scale ($s \in \mathbb{R}^+$).
   - SpatialForge marks uncalibrated scenes with `metric_scale_status: "arbitrary"`. Metric dimensions (meters) are only enabled when users supply known physical distance ground-truth in the calibration dialog.
