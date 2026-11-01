# SpatialForge — 3D Reconstruction & Spatial Exploration Platform

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/Frontend-React%2018-61DAFB.svg)](https://reactjs.org/)
[![Three.js](https://img.shields.io/badge/3D-Three.js%20%2F%20R3F-black.svg)](https://threejs.org/)
[![COLMAP 4.2](https://img.shields.io/badge/SfM-COLMAP%20CPU-orange.svg)](https://colmap.github.io/)
[![Depth Anything V2](https://img.shields.io/badge/AI-Depth%20Anything%20V2-7928CA.svg)](https://github.com/DepthAnything/Depth-Anything-V2)
[![Tests Passing](https://img.shields.io/badge/Tests-150%20Passing-brightgreen.svg)]()

> **Techfest Round 1: 3D Reconstruction & Roaming Submission**  
> SpatialForge is an end-to-end, browser-accessible indoor 3D reconstruction and spatial navigation platform designed to run reliably on consumer laptop hardware (Intel Iris/UHD integrated graphics, 16 GB RAM).  
> 🌐 **Live Public 3D Showcase Viewer**: **[https://frontend-nine-mu-97.vercel.app](https://frontend-nine-mu-97.vercel.app)** (Interactive browser roaming, real COLMAP sparse cloud & camera trajectory, zero installation required). See [docs/PUBLIC_VIEWER_DEPLOYMENT.md](docs/PUBLIC_VIEWER_DEPLOYMENT.md) for full deployment details.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Key Features](#2-key-features)
3. [System Architecture](#3-system-architecture)
4. [Technology Stack](#4-technology-stack)
5. [Supported Reconstruction Modes](#5-supported-reconstruction-modes)
6. [Hardware Requirements](#6-hardware-requirements)
7. [Software Prerequisites](#7-software-prerequisites)
8. [Installation Instructions](#8-installation-instructions)
9. [Backend Setup](#9-backend-setup)
10. [Frontend Setup](#10-frontend-setup)
11. [COLMAP Installation & Configuration](#11-colmap-installation--configuration)
12. [Model Dependency Installation](#12-model-dependency-installation)
13. [Running SpatialForge Locally](#13-running-spatialforge-locally)
14. [Reconstructing a Sample Scene](#14-reconstructing-a-sample-scene)
15. [Using the 3D Viewer & Telemetry](#15-using-the-3d-viewer--telemetry)
16. [Capture SOP](#16-capture-sop)
17. [Testing Instructions](#17-testing-instructions)
18. [Example Reconstruction Results](#18-example-reconstruction-results)
19. [Known Limitations & Design Boundaries](#19-known-limitations--design-boundaries)
20. [Project Directory Structure](#20-project-directory-structure)
21. [Techfest Round 1 Submission Information](#21-techfest-round-1-submission-information)

---

## 1. Project Overview

SpatialForge converts standard smartphone captures (continuous video, multi-view photo sets, or single photographs) into interactive 3D spatial representations inspectable directly inside any modern web browser.

Traditional photogrammetry tools often demand high-end dedicated GPUs with CUDA, leaving mobile users and low-power laptops unable to reconstruct indoor environments. SpatialForge solves this by providing:
- A CPU-optimized **Structure-from-Motion (SfM)** pipeline utilizing COLMAP.
- An intelligent **video frame selection engine** that filters motion blur, camera pauses, and duplicate angles.
- A **monocular 2.5D depth reconstruction pipeline** leveraging Depth Anything V2 ONNX for immediate room previews from a single photo.
- An interactive **Three.js / WebGL viewer** featuring smooth camera orbiting, first-person navigation, metric scale calibration, and live geometric telemetry.

---

## 2. Key Features

- **Three Capture Workflows**:
  - **Video**: Upload an `.mp4` walkthrough; SpatialForge extracts, de-blurs, selects keyframes, and runs sparse SfM.
  - **Photo Set**: Upload 15–80 overlapping photos for multi-view triangulation.
  - **Single Photo**: Upload 1 indoor photograph for AI-guided relative depth mesh generation with texture mapping.
- **Automated Video Frame Analysis**:
  - Laplacian variance sharpness scoring to reject motion-blurred frames.
  - Color histogram cross-correlation to eliminate camera stagnation.
- **Verified 3D Viewer Bundle**:
  - Declarative scene packaging via JSON manifests (`schema_version: 1.0.0`).
  - Supports textured PLY meshes, PLY point clouds, and GLTF/GLB models.
  - Right-handed $Y$-up coordinate system transformation ($source \to scene$).
- **Geometric Quality & Topology Safeguards**:
  - Zero inverted faces guaranteed ($n_z / \|n\| \ge 0.05$).
  - Discontinuity edge clipping ($\Delta d \le 0.08$) eliminates artificial wall stretching.
  - Analytical surface normal export embedded in PLY geometry.
- **Diagnostic Telemetry**:
  - Real-time WebGL metrics (FPS, draw calls, triangles, vertices, camera poses).
  - Depth map heatmaps, discontinuity maps, and 20-bin depth histograms.
  - Interactive textured vs. wireframe mesh toggle.

---

## 3. System Architecture

SpatialForge is structured into three clean layers:

```
[Web Client (React 18 + Three.js)]
         │
         ▼  (REST API / Asset Delivery)
[API Gateway (FastAPI + Pydantic)]
         │
         ▼  (Job Queue & Background Worker)
[Reconstruction Engine (COLMAP SfM + Depth Anything V2 ONNX)]
         │
         ▼  (Verified Package)
[Scene Storage (datasets/scene_<id>/)]
```

For full architectural details, sequence diagrams, and state machines, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 4. Technology Stack

- **Backend**: Python 3.12, FastAPI, Uvicorn, Pydantic v2, PyYAML
- **Computer Vision & ML**: OpenCV (`opencv-python-headless`), NumPy, ONNX Runtime (CPU execution provider)
- **Photogrammetry**: COLMAP 4.2+ (CPU command-line build)
- **Frontend**: React 18, TypeScript 5.4, Vite 5, React Three Fiber (`@react-three/fiber`), Drei (`@react-three/drei`), Three.js
- **Testing**: Pytest (110 tests), Vitest (40 tests across 18 suites)

---

## 5. Supported Reconstruction Modes

| Mode | Input | Target Output | Processing Time (CPU) | Scale Status |
| :--- | :--- | :--- | :--- | :--- |
| **Video** | `.mp4`, `.mov` (15–45s) | Sparse point cloud (`sparse.ply`) + camera poses | 45–90 seconds | Arbitrary (Calibratable) |
| **Photo Set** | 15–60 overlapping images | Sparse point cloud (`sparse.ply`) + camera poses | 60–180 seconds | Arbitrary (Calibratable) |
| **Single Photo** | Single `.jpg`, `.png` | Textured 2.5D mesh (`mesh.ply` + `texture.jpg`) | 15–30 seconds | Arbitrary relative |

---

## 6. Hardware Requirements

- **Minimum Host Hardware**:
  - CPU: Quad-core 64-bit x86 processor (Intel Core i5 8th Gen / AMD Ryzen 3500U or newer)
  - RAM: **16 GB RAM** (System enforces headroom checks $\ge 768$ MB before starting jobs)
  - Graphics: Integrated Intel UHD / Iris Xe Graphics (or AMD Radeon Vega)
  - Storage: 5 GB free disk space
- **Recommended**:
  - 16 GB+ RAM, modern multi-core processor (6+ cores), SSD storage.
  - Dedicated GPU is supported by COLMAP when CUDA is installed, but **not required**.

---

## 7. Software Prerequisites

- **Operating System**: Windows 10/11 (64-bit), Linux (Ubuntu 22.04+), or macOS (13+)
- **Python**: Version **3.11** or **3.12** installed and on `PATH`
- **Node.js**: Version **18.x** or **20.x LTS** (with `npm`)
- **COLMAP**: Version 4.0 or newer (Windows CPU binary or Linux package)
- **Git**: Version 2.30+

---

## 8. Installation Instructions

### One-Command Setup (Windows PowerShell)

Clone the repository and run the automated bootstrap script:

```powershell
git clone https://github.com/Kartikeya69/SpatialForge.git
cd spatialforge
powershell -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
```

This idempotent script will:
1. Verify system resources (RAM and disk space).
2. Create and configure the local Python virtual environment (`.venv`).
3. Install backend dependencies and developer tools.
4. Install frontend npm dependencies.
5. Create `.env` from template if not present.
6. Run environment validation checks.

---

## 9. Backend Setup

If performing manual installation:

```bash
# 1. Create and activate virtual environment
python -m venv .venv

# Windows:
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# 2. Upgrade pip and install package in editable mode with development dependencies
pip install --upgrade pip setuptools wheel
pip install -e .[dev]

# 3. Create environment configuration
cp .env.example .env
```

---

## 10. Frontend Setup

```bash
cd frontend
npm install
npm run build   # Verifies TypeScript compilation and production bundle
cd ..
```

---

## 11. COLMAP Installation & Configuration

COLMAP provides the Structure-from-Motion core for video and multi-photo reconstruction.

### Windows (CPU-Only, No CUDA required):
1. Download `colmap-x64-windows-nocuda.zip` from [COLMAP GitHub Releases](https://github.com/colmap/colmap/releases).
2. Extract the archive (e.g. to `C:\Users\<user>\Downloads\colmap-x64-windows-nocuda` or `C:\tools\colmap`).
3. Set the path in your `.env` file:
   ```ini
   SPATIALFORGE_COLMAP_PATH=C:\tools\colmap\bin\colmap.exe
   ```
   *(Alternatively, add COLMAP's `bin` folder to your Windows system `PATH`).*

### Linux (Ubuntu / Debian):
```bash
sudo apt update
sudo apt install colmap
```

SpatialForge automatically checks `SPATIALFORGE_COLMAP_PATH`, system `PATH`, and standard download locations.

---

## 12. Model Dependency Installation

For the **Single-Photo 2.5D Depth Reconstruction** pipeline, download the Depth Anything V2 Small ONNX model weights:

1. Download `depth_anything_v2_small.onnx` (~99 MB) from the [Depth Anything V2 ONNX Release](https://github.com/fabio-sim/Depth-Anything-ONNX/releases) or Hugging Face.
2. Place the file in the `models/` directory:
   ```
   models/depth_anything_v2_small.onnx
   ```
3. Verify the path in `.env`:
   ```ini
   SPATIALFORGE_DEPTH_MODEL=models/depth_anything_v2_small.onnx
   ```

---

## 13. Running SpatialForge Locally

### Option A: Automated Multi-Process Dev Script (Recommended)

From PowerShell in the project root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_dev.ps1
```

This concurrently launches:
- **FastAPI Backend**: `http://127.0.0.1:8000`
- **Vite Frontend**: `http://127.0.0.1:5173`
- Streams logs to `logs/backend.log` and `logs/frontend.log`.
- Press `Ctrl+C` in the terminal to gracefully stop both servers.

### Option B: Separate Terminals

**Terminal 1 (Backend API):**
```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn spatialforge.api.main:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 (Frontend Client):**
```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

---

## 14. Reconstructing a Sample Scene

1. Open `http://localhost:5173` in Chrome, Edge, or Firefox.
2. Navigate to **Create / Import**.
3. Choose your input modality:
   - **Video**: Drag and drop a room walkthrough `.mp4`. Click **Extract & Analyze**. Review the extracted keyframes and blur metrics, then click **Start Reconstruction**.
   - **Photo Set**: Select multiple overlapping photos.
   - **Single Photo**: Drop an indoor image to instantly generate a 2.5D relief mesh.
4. Watch the progress stages in real time under **Processing Dashboard**.
5. Once marked **Ready**, click **Open in Viewer**.

---

## 15. Using the 3D Viewer & Telemetry

- **Camera Navigation**:
  - **Orbit Mode**: Left-click drag to rotate around the target; right-click drag to pan; scroll wheel to zoom.
  - **Single-Photo Parallax**: Restrained within $\pm 35^\circ$ azimuth and $90^\circ \pm 30^\circ$ polar tilt to preserve photographic perspective without flipping behind the surface.
  - **Walk Mode**: WASD keys to move, mouse-look to look around (enabled when collision/navigation mesh exists).
- **Interactive Controls Toolbar (Bottom)**:
  - `⛶ Frame Scene`: Centers and frames the loaded geometry in the camera viewport.
  - `↺ Reset Camera`: Returns to the default spawn pose.
  - `⚙ Viewer Settings`: Adjusts walk speed, look sensitivity, and quality presets (Low, Balanced, High).
  - `⌁ Toggle Trajectory`: Shows or hides the 3D camera trajectory path and registration markers.
  - `▥ Diagnostics Panel`: Opens live WebGL telemetry, depth maps, and the **Show Wireframe** toggle.

---

## 16. Capture SOP

For field capture instructions, lighting advice, camera overlap percentages, and motion-blur mitigation protocols, review the standard operating procedure in [docs/CAPTURE_SOP.md](docs/CAPTURE_SOP.md).

---

## 17. Testing Instructions

SpatialForge includes a comprehensive automated test suite covering all APIs, ingestion, photogrammetry runners, geometry math, and React components.

```powershell
# Run backend tests (110 tests):
.\.venv\Scripts\pytest

# Run frontend tests (40 tests across 18 suites):
npm test --prefix frontend -- --run

# Run frontend production build check:
npm run build --prefix frontend
```

---

## 18. Example Reconstruction Results

| Pipeline | Test Scene | Key Metric | Verified Outcome |
| :--- | :--- | :--- | :--- |
| **Video (COLMAP)** | `scene_20261031T160047Z_cd37fab494` | Reprojection Error | **0.714 px**, 19/22 cameras registered, 939 sparse 3D points |
| **Single Photo (AI)** | `scene_20261101T035558Z_4a97da5bb5` | Geometry Topology | **0 inverted faces**, 133,605 faces, 1.74 mean aspect ratio |

For complete benchmark tables and logs, see [docs/RECONSTRUCTION_RESULTS.md](docs/RECONSTRUCTION_RESULTS.md).

---

## 19. Known Limitations & Design Boundaries

1. **Sparse vs. Dense Geometry**:
   - The multi-view video pipeline generates a **sparse 3D point cloud** representing tracked feature landmarks and registered camera poses. It does not synthesize an implicit dense Poisson surface mesh without an external GPU dense-stereo worker.
2. **Monocular 2.5D Depth**:
   - Single-photo depth estimation creates a 2.5D relief map viewed from the camera's optical center. Unseen geometry behind foreground objects cannot be hallucinated.
3. **Metric Scale**:
   - Monocular photogrammetry is scale-ambiguous. Real-world meters require manual ground-truth calibration via known landmark distances.

---

## 20. Project Directory Structure

```
spatialforge/
├── .env.example                     # Portable configuration template
├── .gitignore                       # Clean Git exclusion rules
├── pyproject.toml                   # Python package specification & dependencies
├── README.md                        # Master documentation (this file)
│
├── configs/                         # Default pipeline profiles
│   ├── capture.yaml                 # Video sampling & blur thresholds
│   └── reconstruction.yaml          # COLMAP SfM parameters
│
├── docs/                            # Competition & technical reports
│   ├── ARCHITECTURE.md              # System architecture & Mermaid flowcharts
│   ├── CAPTURE_SOP.md               # Standard Operating Procedure for capture
│   ├── RECONSTRUCTION_RESULTS.md    # Quantitative benchmark metrics
│   ├── SINGLE_PHOTO_GEOMETRY_REPAIR.md # Geometry repair derivations
│   └── TECHFEST_SUBMISSION_READINESS.md# Round 1 submission checklist
│
├── frontend/                        # React 18 + Three.js application
│   ├── package.json                 # Node.js dependencies
│   ├── vite.config.ts               # Vite configuration & proxy
│   └── src/                         # React components & WebGL viewports
│
├── models/                          # Machine learning weights (ONNX)
│   └── .gitkeep
│
├── scripts/                         # Developer automation scripts
│   ├── setup_windows.ps1            # Idempotent setup bootstrap
│   └── start_dev.ps1                # Dual-service dev server runner
│
├── spatialforge/                    # Python core backend package
│   ├── api/                         # FastAPI routes & endpoints
│   ├── engine/                      # Ingestion, SfM, and depth engines
│   ├── navigation/                  # Walkability grids & colliders
│   └── scenes/                      # Scene manifests & validation
│
├── test/                            # Competition evaluation datasets
│   ├── README.md                    # Sample dataset instructions
│   ├── single_photo/                # Single-photo test sample
│   ├── photo_set/                   # Multi-photo test sample
│   └── video/                       # Video walkthrough sample
│
└── tests/                           # Pytest unit & integration test suite
```

---

## 21. Techfest Round 1 Submission Information

- **Competition**: Techfest Round 1 — 3D Reconstruction & Roaming
- **Category**: Indoor Spatial Digital Twin & WebGL Exploration
- **Team Submission Deliverables**:
  1. Technical Abstract PDF (5 pages max)
  2. Public GitHub Code Repository
  3. Working Web Viewer Proof-of-Concept Link
  4. Demonstration Video (3–5 minutes)
- **Submission Readiness Checklist**: Refer to [docs/TECHFEST_SUBMISSION_READINESS.md](docs/TECHFEST_SUBMISSION_READINESS.md).
