# SpatialForge — Local vs. Production Architecture

## 1. System Overview

SpatialForge is designed with two distinct, deterministic operational modes:

1. **MODE A — FULL LOCAL APPLICATION (`VITE_APP_MODE=full`)**:
   - The complete, fully-featured 3D reconstruction platform running on your local workstation.
   - Powered by a Python 3.12 FastAPI backend, COLMAP 4.2+ (CPU SfM), and ONNX Runtime (Depth Anything V2 Small).
   - Capable of video keyframe extraction, blur filtering, multi-photo overlap estimation, sparse bundle adjustment, camera registration, and 2.5D monocular depth meshing.
   - Retains full write capabilities: capture uploads, real-time job execution, scene renaming, and scene package importing.

2. **MODE B — PUBLIC SHOWCASE VIEWER (`VITE_APP_MODE=showcase`)**:
   - A serverless, static WebGL 2.0 demonstration deployment for competition judges, evaluators, and mobile exploration.
   - Hosted on CDN infrastructure (e.g., Vercel / Netlify / GitHub Pages) without Python or server GPU/CPU workers.
   - Loads verified, static exported 3D geometry bundles (such as genuine COLMAP sparse point clouds with 19 registered camera poses, and an interactive indoor twin lab with collision boundaries and POI navigation).
   - Explicitly read-only: does not disguise absent server capabilities, display fake reconstruction progress, or silently swap modes.

---

## 2. Feature Availability Matrix

| Feature / Capability | Local Workstation Mode (`full`) | Public Showcase Mode (`showcase`) | Architectural Detail |
| :--- | :---: | :---: | :--- |
| **Dashboard** | ✅ Live Backend Data | ✅ Showcase Data | Displays real local datasets or verified showcase scenes without crashing. |
| **3D WebGL Viewer 2.0** | ✅ Full Local Assets | ✅ Static Bundles | Orbit, Overview, and First-Person roaming supported across both. |
| **Real COLMAP Scene** | ✅ Live Generated | ✅ Exported Bundle | 939 triangulated points (`sparse.ply`) + 19 camera poses (`camera_poses.json`). |
| **Interactive Roaming Twin** | ✅ Available | ✅ Exported Bundle | GLTF mesh with AABB colliders, 2D floor grid, and POI navigation search. |
| **Video Reconstruction** | ✅ Fully Functional | ❌ Explicitly Offline | Requires local ffmpeg, frame blur analyzer, and COLMAP SfM runner. |
| **Photo-Set Reconstruction** | ✅ Fully Functional | ❌ Explicitly Offline | Requires local pairwise feature matcher and sparse bundle adjustor. |
| **Single-Photo 2.5D AI** | ✅ Fully Functional | ❌ Explicitly Offline | Requires local ONNX Runtime CPU inference for Depth Anything V2. |
| **Processing Job Queue** | ✅ Real-time Polling | ❌ Explicitly Offline | Worker queues run on local Python server; showcase renders clear offline banner. |
| **Scene Management** | ✅ Create / Edit / Delete | 👁️ Read-Only | Deletion and renaming disabled in showcase to protect demonstration assets. |
| **Telemetry & Metrics** | ✅ Live GPU & Stats | ✅ Live GPU & Stats | WebGL draw calls, triangle counts, point counts, and FPS telemetry. |

---

## 3. Runtime Mode Configuration

SpatialForge detects its runtime mode deterministically at application startup. Dynamic mid-session mode swapping on network errors has been completely eliminated.

### Determination Precedence:
1. **Explicit Environment Flag**:
   - `VITE_APP_MODE=full` forces Full Local Mode.
   - `VITE_APP_MODE=showcase` forces Public Showcase Mode.
2. **Hostname-based Default**:
   - `localhost` or `127.0.0.1` defaults to **Full Local Mode** (`full`).
   - Remote domains (`*.vercel.app`, custom hostnames) default to **Public Showcase Mode** (`showcase`).

```typescript
// frontend/src/api.ts
export type AppRuntimeMode = "full" | "showcase";

function detectInitialMode(): AppRuntimeMode {
  const envMode = (import.meta.env.VITE_APP_MODE as string | undefined)?.toLowerCase();
  if (envMode === "showcase") return "showcase";
  if (envMode === "full") return "full";

  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host !== "localhost" && host !== "127.0.0.1") {
      return "showcase";
    }
  }
  return "full";
}
```

---

## 4. Local Workstation Startup Instructions

To run the complete platform locally:

```powershell
# In repository root
powershell -ExecutionPolicy Bypass -File .\scripts\start_dev.ps1
```
This boots:
- Backend: `http://127.0.0.1:8000` (FastAPI + Uvicorn)
- Frontend: `http://localhost:5173` (Vite development server in `full` mode)

---

## 5. Public Showcase Hosting Instructions

To deploy the static showcase to Vercel:

1. Import the repository into Vercel.
2. Set Root Directory to `frontend`.
3. Set Build Command to `npm run build` and Output Directory to `dist`.
4. Deploy. The build produces a self-contained bundle under 70 KB with static showcase assets in `/showcase/`.
