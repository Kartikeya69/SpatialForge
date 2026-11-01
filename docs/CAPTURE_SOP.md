# SpatialForge — Standard Operating Procedure (SOP): 3D Scene Capture

**Document ID**: SOP-SF-001  
**Target Submission**: Techfest Round 1: 3D Reconstruction & Roaming  
**Scope**: Field capture protocols for smartphones and consumer cameras to ensure high-fidelity 3D photogrammetric and depth reconstruction.

---

## 1. Purpose & Scope

This Standard Operating Procedure (SOP) defines the standardized methodology for capturing physical indoor spaces (rooms, halls, laboratories, exhibition booths) for 3D reconstruction in SpatialForge. Adhering to these protocols ensures sufficient parallax, visual overlap, sharp features, and consistent photometric properties required for Structure-from-Motion (COLMAP) and Monocular Depth Estimation.

---

## 2. Environment Preparation

1. **Static Environment**:
   - Ensure the capture environment is completely static. No moving individuals, pets, ceiling fans, or oscillating curtains should be active during capture.
   - Doors and furniture must remain in fixed positions throughout the entire session.
2. **Surface Considerations**:
   - **Challenging Surfaces**: Plain textureless white walls, shiny polished marble floors, large mirrors, and transparent glass windows lack photometric feature descriptors (SIFT).
   - **Mitigation**: Add temporary visual landmarks if necessary (e.g., patterned tape, magazines, printed calibration markers, or textured rugs) to provide trackable feature points.
   - Close blinds or curtains over reflective windows to avoid external lighting shifts.
3. **Lighting Recommendations**:
   - Diffuse, indirect ambient lighting is ideal.
   - Avoid strong directional spotlights, harsh direct sunlight shafts, or flickering fluorescent bulbs.
   - Turn on all overhead room lights to achieve uniform illumination across corners.

---

## 3. Camera & Hardware Configuration

- **Device**: Modern smartphone (iOS / Android) or mirrorless digital camera.
- **Lens Selection**: Use the primary **wide lens (1×)**. Avoid ultra-wide (0.5×) or telephoto (3×/5×) lenses, as extreme optical distortion or narrow field of view degrades bundle adjustment stability.
- **Digital Zoom**: Strictly **1.0×**. Never use digital zoom.
- **Focus & Exposure Locking**:
  - Lock auto-exposure (AE) and auto-focus (AF) before starting the capture trajectory (long-press on target subject).
  - Rapid exposure hunting or white-balance shifts between frames will cause feature descriptor mismatches.
- **Resolution & Framerate**:
  - Video: **1080p (1920×1080) at 30 fps or 60 fps**. (4K is acceptable but increases decoding time without adding proportional SfM benefit on CPU).
  - Photos: **8–12 Megapixels** (standard native resolution).
- **Aspect Ratio**: Native 4:3 (photos) or 16:9 (video). Maintain consistent landscape orientation.

---

## 4. Multi-Photo Capture Protocol

For highest precision and geometric stability:

1. **Overlap Guidelines**:
   - Maintain a minimum of **70% to 80% visual overlap** between consecutive photographs.
   - Every physical surface point should be visible in at least **3 to 5 separate photographs** taken from different baseline angles.
2. **Camera Motion Strategy**:
   - **Perimeter Loop**: Walk slowly along the outer boundary of the room, facing inward with a slight forward angle, taking a photograph every 20–30 cm.
   - **Center Inward Orbit**: For central furniture (desks, tables), perform a 360-degree orbit around the object maintaining consistent distance.
   - **Height Variation**: Take a sequence at eye level (~1.6 m) and a supplementary pass with the camera tilted downward or at chest height (~1.1 m) to capture horizontal surfaces (tabletops, chair seats).
3. **Pure Translation vs. Rotation**:
   - **Never rotate the camera in place like a panorama**. Pure rotational motion provides zero geometric baseline ($B=0$) and cannot triangulate 3D depth. Always physically step to a new position.

---

## 5. Video Recording Protocol

1. **Capture Duration**:
   - Aim for **20 to 60 seconds** of continuous video.
   - Excessively long videos (> 3 minutes) consume unnecessary memory on 16 GB RAM systems without improving sparse SfM quality.
2. **Walking Cadence & Motion Blur Prevention**:
   - Walk using the "ninja walk" or heel-to-toe technique to minimize vertical camera bounce.
   - Keep translation velocity slow and steady: approximately **0.2 to 0.4 meters per second**.
   - Turn corners gradually in smooth circular arcs; avoid snappy, quick turns that introduce rotational motion blur.
3. **Trajectory Closure**:
   - Conclude the video recording trajectory near the exact starting position. Closed-loop trajectories allow COLMAP to perform global loop closure and eliminate drift error.

---

## 6. Data Transfer Protocol (Lossless Offloading)

> [!CAUTION]
> Never transfer captured media using messaging platforms (WhatsApp, Telegram, Discord, Slack) that re-encode, resize, or strip EXIF metadata from photos and videos!

Approved Transfer Methods:
1. **Direct USB Cable Connection**: Copy files directly from phone storage to the local PC.
2. **Local Network / SMB Share**: Transfer original files via AirDrop, LocalSend, or shared local folder.
3. **Cloud Storage as Raw File**: Google Drive or OneDrive using "Upload File" (ensuring "Original Quality" is preserved).

---

## 7. Frame Quality Assessment & Automated Analysis

SpatialForge provides built-in automated media analysis:

1. **Blur Detection (Laplacian Variance)**:
   - Evaluates high-frequency image gradients:
     $$\text{Var}(\nabla^2 I) \ge \tau_{\text{blur}} \quad (\text{default: } 80.0)$$
   - Blurry frames from rapid movement are automatically filtered out.
2. **Duplicate & Stagnation Detection**:
   - Computes normalized color histogram correlation between adjacent frames.
   - Correlation $> 0.995$ indicates camera standing still; redundant duplicate frames are discarded.
3. **Camera Calibration Extraction**:
   - Reads EXIF tags (35mm equivalent focal length, sensor dimensions, F-stop, exposure time) to seed COLMAP's pinhole camera model.

---

## 8. Common Capture Pitfalls & Remediation

| Symptom / Failure | Root Cause | Remediation Protocol |
| :--- | :--- | :--- |
| **COLMAP registers 0 or few cameras** | Zero-baseline rotation (standing in one spot turning around). | Recapture by physically walking a path with 20–30 cm steps between views. |
| **Fragmented / Multiple Sub-models** | Insufficient overlap ($< 60\%$) between sections of the room. | Recapture maintaining $\ge 75\%$ overlap; ensure transition views link different room zones. |
| **Excessive Motion Blur** | Rapid camera swinging or low shutter speed in dark lighting. | Increase room lighting; slow down physical walking speed to 0.2 m/s. |
| **Missing Plain Wall Geometry** | Textureless white walls lack SIFT feature descriptors. | Add visual features or use the **Single-Photo 2.5D Monocular Depth** pipeline for textureless rooms. |
| **Severe 2.5D Mesh Tearing** | Sharp foreground occlusions bridged by old depth jump thresholds. | Handled automatically by SpatialForge's updated discontinuity filter ($\Delta d \le 0.08$) and front-facing normal check ($n_z / \|n\| \ge 0.05$). |
