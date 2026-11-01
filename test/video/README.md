# Video Test Sample Directory

Place a continuous smartphone or camera video recording here for evaluating the **Automated Video Frame Selection and COLMAP Reconstruction Pipeline**.

### Recommended Capture Characteristics
- **Format**: `.mp4`, `.mov`, `.avi`
- **Duration**: 15–40 seconds
- **Motion Speed**: Slow, steady panning or walking motion (approx. 0.2–0.4 m/s) to prevent rotational motion blur
- **Resolution**: 1080p (1920×1080) at 30 fps or 60 fps
- **Trajectory**: Closed loop or arc around the room perimeter, returning near the starting position to facilitate loop closure in SfM

### Processing Stages
1. **Frame Extraction**: Decodes video frames at configured sample rate (e.g. 2.0 fps).
2. **Quality Analysis**: Evaluates Laplacian variance for sharpness/blur rejection and color histograms for duplicate detection.
3. **Keyframe Selection**: Selects sharp, non-redundant keyframes for feature matching.
4. **COLMAP SfM**: Performs feature extraction, sequential/vocab-tree matching, and bundle adjustment.
5. **Scene Packaging**: Packages 3D sparse points and camera trajectory for Three.js WebGL visualization.
