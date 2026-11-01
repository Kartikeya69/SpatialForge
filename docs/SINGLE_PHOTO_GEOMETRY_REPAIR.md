# SpatialForge — Critical Single-Photo 2.5D Geometry Repair Report

## 1. Executive Summary

This report documents the diagnosis, mathematical repair, and end-to-end verification of SpatialForge's single-photo reconstruction pipeline (`Depth Anything V2 ONNX` CPU pipeline).

### Observed Symptoms Prior to Repair
- Severely distorted 2.5D meshes with spiky, stretched triangular surfaces.
- Large black vertical geometry and unnatural dark polygons intersecting the room.
- Fragmented, torn image textures appearing unrecognizable from any viewing angle.
- The 3D viewer camera spawned at an oblique $+45^\circ$ angle (`+4.52, +3.27, +0.93`), displaying the ragged side profile of the relief map rather than the photographic view.
- 10,151 inverted or backfacing faces out of 147,237 faces in user capture `scene_20261101T035558Z_4a97da5bb5`.

### Repair Outcomes
- **Inverted / Folded Faces**: Completely eliminated ($10,151 \to 0$ inverted faces).
- **Edge Discontinuities & Occlusion Cliffs**: Bounded strictly. Relative depth jumps $\Delta d > 0.08$ and 3D edge lengths $> 3.8 \times d_{\text{expected}}$ are filtered prior to mesh construction (18,877 cliff faces clipped in user scene; 133,605 high-quality faces retained with 87.62% retention).
- **Triangle Aspect Ratio**: Reduced from $> 50.0$ to a mean of $1.74$ (99th percentile $4.55$).
- **Analytical Surface Normals**: Calculated via central differences on the smooth depth field and baked directly into PLY vertices (`property float nx, ny, nz`), avoiding distorted post-hoc WebGL normal generation.
- **UV Parameterization & Texturing**: $(s, t)$ texture coordinates baked into PLY, with `assets/texture.jpg` exported and rendered via Three.js `TextureLoader` on `MeshStandardMaterial`.
- **Source Camera Framing**: When loading a 2.5D scene, the viewer camera now initializes exactly at $(0, 0, 0)$ looking at $(0, 0, -z_{\text{median}})$ with the source camera's vertical FOV ($58.11^\circ$). Initial display is a pixel-perfect, distortion-free match to the user's photo.
- **Restrained Parallax Mode**: OrbitControls are bounded to $\pm 35^\circ$ azimuth and $90^\circ \pm 30^\circ$ polar tilt, giving an intuitive 3D parallax depth experience while preventing rotation behind the relief sheet.
- **Diagnostics & Wireframe Toggle**: Added live diagnostic previews (grayscale depth, Turbo heatmap, discontinuity map, 20-bin histogram) and interactive wireframe toggling in `DiagnosticsPanel`.

---

## 2. Complete Pipeline Audit (Phases 1–5)

```
[Uploaded Photo]
       │
       ▼
[Exif & Pinhole Intrinsics Estimation]
       │
       ▼
[Depth Anything V2 ONNX Inference] ──> Raw Relative Inverse Depth
       │
       ▼
[Percentile Normalization [1%, 99%]] ──> Metric-Free Depth [0.0, 1.0]
       │
       ▼
[Bilateral Smoothing] ──> Noise-Free Edge-Preserving Depth Field
       │
       ▼
[Pinhole Camera Backprojection] ──> Camera-Space Vertices (X, Y, -Z)
       │
       ▼
[Analytical Grid Normals & UVs] ──> (nx, ny, nz) pointing +Z & (s, t)
       │
       ▼
[Discontinuity & Topology Filtering] ──> Strict Cliff Rejection & Inverted Normal Elimination
       │
       ▼
[Asset Packaging] ──> assets/single-photo-depth-mesh.ply + assets/texture.jpg + metadata/
       │
       ▼
[Three.js PLYLoader + TextureLoader] ──> WebGL Rendering with Parallax Orbit Rig
```

### 2.1 Image Preprocessing & Depth Inference
- **Input Image**: Decoded with orientation handling via `decode_oriented_image`.
- **Focal Length**: Estimated from EXIF 35mm equivalent focal length when present; otherwise defaults to standard pinhole assumption:
  $$f = 0.9 \times \max(W, H)$$
  Principal point is set strictly to optical center $(c_x, c_y) = (W / 2, H / 2)$.
- **Inference**: Depth Anything V2 Small ONNX model runs on CPU, producing raw inverse relative depth.
- **Normalization**: Clipped to $[p_{01}, p_{99}]$ to prevent singular hot/cold pixels from compressing scene dynamic range, then scaled to $[0.0, 1.0]$.

### 2.2 Camera-Space Backprojection Math
For a grid point $(u, v)$ with normalized depth $d(u, v) \in [0, 1]$:
$$Z(u, v) = -(z_{\text{min}} + d(u, v) \cdot (z_{\text{max}} - z_{\text{min}}))$$
$$X(u, v) = \frac{u - c_x}{f_x} \cdot |Z(u, v)|$$
$$Y(u, v) = -\frac{v - c_y}{f_y} \cdot |Z(u, v)|$$
where $-Z$ extends forward into the scene, $+X$ extends right, and $+Y$ extends up. This guarantees right-handed coordinates identical to Three.js conventions.

### 2.3 Mesh Topology & Filtering
Triangles are formed across grid cells $[(u, v), (u+1, v), (u, v+1), (u+1, v+1)]$.
To prevent geometry tearing, a triangle $(v_0, v_1, v_2)$ is accepted if and only if:
1. **Relative Depth Discontinuity**:
   $$\max(|d_0 - d_1|, |d_1 - d_2|, |d_2 - d_0|) \le 0.08$$
2. **Euclidean Edge Length**:
   $$\max(\|v_1 - v_0\|, \|v_2 - v_1\|, \|v_0 - v_2\|) \le 3.8 \times d_{\text{expected}}$$
3. **Strict Outward Front-Facing Normal**:
   $$n = (v_1 - v_0) \times (v_2 - v_0), \quad \frac{n_z}{\|n\|} \ge 0.05$$
4. **Non-Degenerate Face Area**:
   $$\|n\| \ge 10^{-12}$$

Triangles failing any condition are rejected, creating clean silhouette cutouts around foreground subjects rather than sheer cliff geometry.

---

## 3. Root Cause Deep Dive

| Defect | Root Cause in Original Code | Mechanical & Visual Impact | Permanent Solution |
| :--- | :--- | :--- | :--- |
| **Inverted / Black Geometry** | Winding order was arbitrary; 10,151 faces had $n_z < 0$. Three.js `computeVertexNormals` averaged these into adjacent vertices. | Dark black vertical triangles, folded surfaces, and broken lighting. | Enforced strict CCW winding in camera space and rejected any face with $n_z / \|n\| < 0.05$. Calculated analytical normals on grid. |
| **Severe Surface Stretching** | Jump threshold was $0.12 \times \text{median}(Z) \approx 0.60$ units. Foreground-to-background boundaries were bridged. | Polygons stretched 50× across depth boundaries, creating artificial walls. | Reduced relative depth jump cutoff to $\le 0.08$ and bounded 3D edge length to $\le 3.8 \times d_{\text{expected}}$. |
| **Artificial Staircases** | `refine_relative_depth` dilated Sobel/Canny edges and injected raw noisy depth back into smoothed depth. | High-contrast wallpapers or textures created jagged stepped geometry. | Replaced noise injection with edge-preserving bilateral filtering: `cv2.bilateralFilter(d, 5, 0.05, 5)`. |
| **Extreme Oblique Camera** | `CameraModeRig` positioned camera at `+4.52, +3.27, +0.93` at 45° angle. | Looked directly at side relief cliffs, destroying photograph perspective. | Set default camera to source position $(0, 0, 0)$ looking at $(0, 0, -z_{\text{median}})$ with matching vertical FOV. |
| **Missing Texture** | Mesh relied solely on low-resolution vertex colors; UV attributes were not exported. | Muddy, torn texture appearance. | Exported `assets/texture.jpg` (JPEG) and $(s, t)$ UV coordinates; loaded in Three.js via `TextureLoader`. |

---

## 4. Verification and Numerical Results

### User Failing Scene: `scene_20261101T035558Z_4a97da5bb5`

| Metric | Before Repair | After Repair | Status |
| :--- | :--- | :--- | :--- |
| **Total Mesh Vertices** | 74,484 | 69,810 | Verified clean |
| **Total Mesh Faces** | 147,237 | 133,605 | Retained 87.62% |
| **Inverted Faces ($n_z < 0$)** | **10,151** | **0** | **100% Fixed** |
| **Cliff Discontinuities Rejected** | 0 | 18,877 | Bounded |
| **Maximum 3D Edge Length** | 0.6021 units | 0.0546 units | **11× reduction** |
| **Mean Triangle Aspect Ratio** | ~52.4 (extreme cliffs) | 1.74 | Well-conditioned |
| **99th Percentile Aspect Ratio** | > 80.0 | 4.55 | No needles/slivers |
| **Surface Normal Export** | None (computed in WebGL) | Analytical $(n_x, n_y, n_z)$ | Embedded in PLY |
| **UV Coordinates Export** | None | Normalized $(s, t)$ | Embedded in PLY |
| **High-Res Texture** | Absent | `assets/texture.jpg` (263 KB) | Rendered |
| **Viewer Source Camera** | $(+4.52, +3.27, +0.93)$ | $(0.0, 0.0, 0.0) \to (0, 0, -2.39)$ | Matching FOV $58.11^\circ$ |
| **Parallax Restraints** | Unrestricted 360° | Azimuth $\pm 35^\circ$, Polar $\pm 30^\circ$ | Constrained |

### Second Test Scene: `scene_20261101T041011Z_8526a98ff7`
- **Vertices**: 67,759
- **Faces**: 127,951
- **Inverted Faces**: 0
- **Rejected Cliff Discontinuities**: 23,255 (84.62% retention)
- **Source Camera Look At**: $(0.0, 0.0, -2.27)$ with vertical FOV $44.90^\circ$

---

## 5. Diagnostic Artifacts Generated

For every single-photo reconstruction, SpatialForge now generates full diagnostic metadata under `metadata/`:
1. `metadata/depth_grayscale.png`: 8-bit normalized grayscale depth map.
2. `metadata/depth_heatmap.png`: Turbo-colormap depth gradient visualization.
3. `metadata/depth_discontinuity.png`: Magma-colormap Sobel gradient edge map showing depth boundaries.
4. `metadata/depth_diagnostics.json`: Comprehensive telemetry document containing:
   - 20-bin depth histogram
   - Percentiles ($p_{01}, p_{05}, p_{25}, p_{50}, p_{75}, p_{95}, p_{99}$)
   - NaN / Inf counts (verified 0)
   - Mesh topology validation metrics (retained face count, clipped edges, outward normal verification)
   - Source camera viewpoint parameters

In the UI, users can open the **Diagnostics Panel (▥)** to inspect the depth heatmap and discontinuity map side-by-side with live mesh metrics, and click **Show Wireframe / Show Texture** to inspect the underlying triangle tessellation in real time.

---

## 6. Test Suite Status

- **Backend Pytest**: **110 passed**, 0 failed.
- **Frontend Vitest**: **40 passed** (18 test suites), 0 failed.
- **Frontend Production Build**: `tsc -b && vite build` completed cleanly with exit code 0.
