# Single-Photo Test Sample Directory

Place a single perspective room photograph here for evaluating the **Single-Photo 2.5D Depth Reconstruction Pipeline**.

### Recommended Capture Characteristics
- **Format**: `.jpg`, `.jpeg`, or `.png`
- **Resolution**: 1280×960 up to 1920×1440 (1–3 Megapixels recommended for CPU inference)
- **Content**: Indoor room scene (bedroom, office, studio, lounge) with clear depth layers (foreground desk/furniture, middle room, background wall).
- **Lighting**: Even ambient light, minimal deep shadows, no direct lens flare or blown-out sunlight windows.
- **Orientation**: Standard landscape or portrait (EXIF orientation tags are automatically respected).

### Expected Output
- `assets/single-photo-depth-mesh.ply`: Clean 2.5D surface mesh with outward-facing unit normals and UV texture coordinates.
- `assets/texture.jpg`: Source photograph mapped to the 3D surface.
- `metadata/depth_grayscale.png` & `metadata/depth_heatmap.png`: Normalized depth visualizations.
- `metadata/depth_discontinuity.png`: Magma edge map showing detected depth boundaries.
- `metadata/depth_diagnostics.json`: 20-bin histogram, percentiles, and topology metrics.
