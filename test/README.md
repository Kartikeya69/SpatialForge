# SpatialForge — Test Datasets & Evaluation Samples

This directory provides sample capture data and test guidelines for evaluating the SpatialForge 3D reconstruction and WebGL inspection pipeline in compliance with **Techfest Round 1: 3D Reconstruction & Roaming** submission criteria.

---

## 1. Directory Structure

```
test/
├── README.md                  # This guide and dataset manifest
├── single_photo/              # Single-photo test sample (monocular 2.5D depth)
│   ├── README.md              # Single-photo capture specifications & instructions
│   └── .gitkeep
├── photo_set/                 # Multi-view overlapping image set (COLMAP SfM)
│   ├── README.md              # Photo set overlap, baseline, and angle requirements
│   └── .gitkeep
└── video/                     # Continuous motion video capture
    ├── README.md              # Video framerate, camera motion, and resolution specs
    └── .gitkeep
```

---

## 2. Evaluation Datasets Overview

SpatialForge supports three distinct capture and reconstruction modalities:

| Modality | Input Type | Minimum Requirements | Recommended Resolution | Primary Backend Pipeline | Expected Output |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Video** | `.mp4`, `.mov`, `.avi` | 15–45 seconds, steady smooth loop | 1080p (1920×1080) or 720p | Frame selection + COLMAP SfM | Registered camera poses, sparse point cloud, camera trajectory |
| **Photo Set** | Multi-view `.jpg`, `.png` | 15–80 overlapping photos ($>70\%$ overlap) | 2–12 MP | COLMAP SfM (CPU sparse) | Sparse 3D tie points, camera poses, trajectory line |
| **Single Photo** | Single `.jpg`, `.png` | 1 perspective photo of indoor room | 1–4 MP (e.g. 1280×960) | Depth Anything V2 ONNX | 2.5D textured mesh (`.ply` + `.jpg`), surface normals, depth diagnostics |

---

## 3. How to Run Reconstruction on a Test Sample

### A. Via the Web Application (Interactive UI)
1. Start the backend and frontend services:
   ```powershell
   # Windows PowerShell:
   .\scripts\start_dev.ps1
   ```
2. Open your browser at `http://localhost:5173`.
3. In the header navigation, select **Create / Import**.
4. Select the corresponding capture card (**Photo Set**, **Video**, or **Single Photo**).
5. Drag and drop your test file(s) into the dedicated dropzone.
6. Click **Extract & Analyze** (for video) or **Start Reconstruction**.
7. Monitor live stage progress in the **Processing Dashboard**. Once status reaches **Ready**, click **Open in Viewer** to inspect the 3D scene.

### B. Via Backend CLI / Script
You can also run reconstruction directly via Python:

```powershell
# Single-Photo 2.5D Reconstruction:
python -c "from spatialforge.engine.reconstruction.single_image import SingleImagePipeline; SingleImagePipeline().process('test/single_photo/sample_room.jpg', 'datasets/scene_test_single', 'sample_room.jpg')"

# Multi-Image / Photo Set Ingestion:
python -c "from spatialforge.engine.ingestion.pipeline import process_photo_set; process_photo_set('test/photo_set', 'datasets/scene_test_photoset')"
```

---

## 4. Privacy & Consent Notice

> [!IMPORTANT]
> To comply with data privacy policies and competition ethics:
> - Do not upload or commit unconsented personal spaces or identifiable individuals.
> - Ensure all test datasets are captured in public spaces, university laboratories, or consent-cleared test rooms.
> - Prior to final competition submission, participants must verify that sample media placed in `test/` has explicit consent for public evaluation.
