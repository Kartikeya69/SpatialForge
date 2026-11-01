# SpatialForge — Public Showcase 3D Viewer Deployment Guide

> **Live Production URLs**:  
> - Primary: **[https://spatialforge-3d.vercel.app](https://spatialforge-3d.vercel.app)**  
> - Mirror: **[https://spatialforge-viewer.vercel.app](https://spatialforge-viewer.vercel.app)**  
> **Status**: Live, public, zero-backend WebGL 3D reconstruction and roaming.

## Overview

SpatialForge features an automated, serverless-capable **Public Showcase Mode**. When deployed to a public URL (such as Vercel, Netlify, or GitHub Pages), judges and evaluators can interact with real 3D reconstructed environments directly in their browser without requiring local installation, Python dependencies, or a running COLMAP worker.

---

## 1. Architecture: Local Reconstruction Engine vs. Public Showcase Viewer

| Dimension | Local Workstation Pipeline | Public Cloud Showcase Viewer |
| :--- | :--- | :--- |
| **Hosting Target** | Local Windows workstation (16 GB RAM, CPU/GPU) | Vercel Serverless / Static CDN |
| **Compute Engine** | COLMAP 4.2.0 CPU + Depth Anything V2 ONNX | Static WebGL 2.0 / Three.js (Zero server compute) |
| **Data Layer** | FastAPI endpoints (`/api/v1/scenes/*`) | Bundled static JSON + PLY + GLTF (`/showcase/*`) |
| **Failover Design** | Direct API request | Auto-fallback to `/showcase/scenes.json` when offline |
| **Total Asset Size**| Variable (source videos & intermediate databases) | **68.7 KB total bundle** (high-efficiency binary geometry) |

---

## 2. Bundled Showcase Scenes & Privacy Verification

The showcase bundle (`frontend/public/showcase/`) includes two self-contained scenes:

### Scene 1: Real COLMAP Sparse Reconstruction
- **Scene ID**: `scene_20261031T160047Z_cd37fab494`
- **Reconstruction Type**: Real Structure-from-Motion (SfM) via COLMAP CPU.
- **Assets**:
  - `reconstruction/colmap/exports/sparse.ply` (14.2 KB — 939 triangulated 3D points)
  - `reconstruction/colmap/exports/camera_poses.json` (32.5 KB — 19 registered camera positions and orientations)
  - `metadata/scene_manifest.json` (2.6 KB)
- **Privacy & Security Verification**:
  - **No raw personal imagery, video frames, or facial textures** are bundled.
  - The scene consists purely of abstract 3D coordinate point clouds and mathematical camera frustums.
  - Fully compliant with competition privacy guidelines.

### Scene 2: Interactive Indoor Twin (Synthetic Loft)
- **Scene ID**: `scene_synthetic_loft`
- **Reconstruction Type**: Full Walkable Indoor Digital Twin.
- **Assets**:
  - `assets/demo-room.gltf` (3.7 KB — architectural mesh geometry)
  - `assets/diagnostic-points.ply` (2.4 KB)
  - `navigation/colliders.json` (3.0 KB — AABB wall and obstacle colliders)
  - `navigation/grid.json` (2.4 KB — 2D floor occupancy grid for pathfinding)
  - `metadata/pois.json` (2.8 KB — Points of Interest with aliases)
  - `metadata/scene_manifest.json` (3.2 KB)
- **Judge Roaming Features**:
  - First-person walking mode (`W`, `A`, `S`, `D`, mouse look, collision detection).
  - Orbit and Overview inspection modes.
  - Interactive Point of Interest (POI) search and waypoint routing.

---

## 3. Step-by-Step Vercel Deployment Instructions

Deploying the viewer to Vercel takes less than 2 minutes.

### Method A: One-Click GitHub Import (Recommended)

1. Navigate to [https://vercel.com/new](https://vercel.com/new).
2. Sign in with GitHub and select your repository: `Kartikeya69/SpatialForge`.
3. In the project configuration:
   - **Framework Preset**: `Vite`
   - **Root Directory**: `frontend` *(or leave as repository root; `vercel.json` in both locations is already pre-configured)*
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. Click **Deploy**.
5. Once deployment completes, Vercel provides a public production URL (e.g., `https://spatialforge-kartikeya.vercel.app`).
6. Copy and paste this URL into your Techfest Round 1 Technical Abstract and submission form.

### Method B: Vercel CLI (Command Line)

If you prefer deploying via terminal:

```powershell
npm install -g vercel
cd frontend
vercel
```
Follow the interactive prompts (Accept defaults). For production release:
```powershell
vercel --prod
```

---

## 4. Hosting Routing & Rewrites Configuration

Both `frontend/vercel.json` and the root `vercel.json` are pre-configured with SPA fallbacks and API rewrites:

```json
{
  "framework": "vite",
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "cleanUrls": true,
  "rewrites": [
    { "source": "/api/v1/scenes", "destination": "/showcase/scenes.json" },
    { "source": "/api/v1/scenes/:sceneId/manifest", "destination": "/showcase/:sceneId/metadata/scene_manifest.json" },
    { "source": "/api/v1/scenes/:sceneId/assets/:path*", "destination": "/showcase/:sceneId/:path*" },
    { "source": "/api/v1/scenes/:sceneId/pois", "destination": "/showcase/:sceneId/metadata/pois.json" },
    { "source": "/api/v1/pipeline/jobs", "destination": "/showcase/empty_jobs.json" },
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

This guarantees that:
1. Deep-linking to specific scenes or sub-routes does not return `404 Not Found`.
2. Any legacy client code requesting `/api/v1/scenes` receives the static showcase payload with zero server runtime.
3. CORS headers and MIME types are properly set for `.ply` and `.gltf` binary streams.

---

## 5. Verification Checklist

- [x] All 40 unit and integration tests pass cleanly (`npm test --prefix frontend -- --run`).
- [x] Frontend builds without TypeScript or Rollup errors (`npm run build --prefix frontend`).
- [x] Standalone fallback mode auto-activates when backend is not reached.
- [x] Both real COLMAP sparse cloud and walkable indoor digital twin load properly.
- [x] Zero personal imagery or unconsented data included in repository.
- [x] Bundle payload optimized to under 70 KB total.
