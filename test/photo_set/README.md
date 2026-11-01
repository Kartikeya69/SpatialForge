# Photo-Set Test Sample Directory

Place a multi-view collection of overlapping photographs here for evaluating the **Structure-from-Motion (COLMAP) Multi-Photo Pipeline**.

### Recommended Capture Characteristics
- **Format**: `.jpg`, `.jpeg`, or `.png`
- **Count**: 15–60 overlapping images
- **Overlap**: Minimum 70–80% overlap between consecutive frames
- **Motion Strategy**: Circular orbit around a central subject or outward panoramic loop along room perimeter
- **Baseline**: Small steps between shots (15–30 cm); avoid sudden large camera jumps
- **Camera Settings**: Fixed focal length (no optical zoom changes during sequence), locked focus/exposure if possible

### Expected Output
- `assets/sparse.ply`: Triangulated 3D sparse feature points.
- `metadata/camera_poses.json`: Extracted 6-DoF camera poses and viewing rays.
- `metadata/reconstruction_manifest.json`: COLMAP runtime, registered camera count, and mean reprojection error.
