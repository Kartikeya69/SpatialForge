# SpatialForge — Navigation Regression & Dashboard Repair Report

## 1. Executive Summary

Following the introduction of the static showcase deployment bundle, users reported that the application stopped behaving like the localhost platform. Specifically:
- The **Dashboard** crashed upon mounting.
- Navigation between pages showed inconsistent state.
- Standalone auto-fallback in `api.ts` was fragile, dynamically toggling modes mid-session upon individual network errors.
- Pages dependent on the Python backend (Create, Processing) lacked clear boundary indications on the public deployment.

All root causes have been traced, repaired, verified with 155 automated tests (45 frontend + 110 backend), and documented.

---

## 2. Broken Pages & Exact Root Causes

### 1. Dashboard (`src/components/DashboardView.tsx`)
- **Observed Symptom**: Crash with blank screen upon opening the Dashboard or on page reload.
- **Exact Exception**:
  ```
  TypeError: Cannot read properties of undefined (reading 'includes')
    at DashboardView.tsx:177
  ```
- **Root Cause**:
  `DashboardView.tsx` line 177 evaluated:
  `scene.asset_types.includes("ply")`
  In `frontend/public/showcase/scenes.json`, the two demonstration scenes omitted the optional `asset_types` array. When `DashboardView` iterated over `recentScenes`, accessing `.includes()` on `undefined` threw an unhandled React runtime error that crashed the entire component tree.
- **Fix Applied**:
  1. Updated `frontend/public/showcase/scenes.json` to include valid `asset_types`, `primary_asset_type`, and `manifest_url`.
  2. Added defensive null-coalescing in `DashboardView.tsx`: `const assetTypes = scene.asset_types ?? []`.
  3. Added dedicated regression unit tests in `DashboardView.test.tsx`.

### 2. My Scenes (`src/components/MyScenesView.tsx`)
- **Observed Symptom**: Potential crash when filtering scenes or viewing cards.
- **Root Cause**:
  Lines 42 and 170 accessed `scene.asset_types.includes("ply")` without checking for undefined.
- **Fix Applied**:
  Updated filtering and card rendering to use `const assetTypes = scene.asset_types ?? []` and safely check `.includes()`.

### 3. Scene Library Dropdown (`src/components/SceneLibrary.tsx`)
- **Observed Symptom**: Crash when searching scenes by keyword.
- **Root Cause**:
  Lines 16 and 57 accessed `scene.asset_types.join(" ")` and `scene.asset_types.slice(0, 4)` directly.
- **Fix Applied**:
  Wrapped with default array `(scene.asset_types ?? []).join(" ")` and `(scene.asset_types ?? []).slice(0, 4)`.

### 4. API Client & Auto-Fallback (`src/api.ts`)
- **Observed Symptom**: Inconsistent application state; some endpoints queried backend while others queried static files.
- **Root Cause**:
  `api.ts` used a mutable global `let isStandaloneMode = false` and attempted to dynamically toggle it on `fetch().catch()`. If one call failed, the entire app flipped into standalone mode, breaking subsequent calls to the local FastAPI server.
- **Fix Applied**:
  1. Introduced typed deterministic runtime mode: `export type AppRuntimeMode = "full" | "showcase"`.
  2. Determined mode once at startup via `import.meta.env.VITE_APP_MODE` or hostname (`localhost` = full, remote = showcase).
  3. Eliminated silent failover in Full Mode: real backend errors are surfaced directly without masking.
  4. Added runtime enforcement: write operations throw clear errors when invoked in Showcase mode.

### 5. Create & Processing Workflows in Showcase Mode
- **Observed Symptom**: Users on Vercel could click "Start Reconstruction", which attempted to POST to `/api/v1/captures` and failed silently or caused confusing spinner states.
- **Fix Applied**:
  1. Added dedicated showcase notification banners in `CreateWorkflowView.tsx` and `ProcessingDashboard.tsx` explaining that background photogrammetry execution requires the local desktop engine.
  2. Provided direct one-click navigation buttons to explore the pre-computed reconstructions in Viewer 2.0.
  3. Added explicit Topbar runtime mode badge (`[Local Engine]` vs `[Public Showcase]`).

---

## 3. Navigation Matrix Audit

| Route / View | Full Local Mode (`localhost:5173`) | Public Showcase Mode (`spatialforge-3d.vercel.app`) | State & Link Integrity |
| :--- | :--- | :--- | :--- |
| **Dashboard** | ✅ Shows all local scenes & real active jobs | ✅ Shows showcase scenes & explanation banner | Retains active tab, no unhandled exceptions. |
| **Create** | ✅ Drag-drop upload, frame extraction, reconstruction | 👁️ Explains local requirement; routes to Viewer | Clean validation; no infinite spinners. |
| **Processing** | ✅ Live job stages, queue polling, cancel/clear | 👁️ Explains worker requirement; routes to Viewer | Empty queue handled safely; no 404 polling. |
| **My Scenes** | ✅ Full scene list, rename, delete, import `.sfscene` | 👁️ Lists showcase scenes; read-only protection | Scene filtering by type works without crash. |
| **Settings** | ✅ Live CPU, RAM, ONNX, and COLMAP diagnostics | ✅ Client WebGL diagnostics & showcase notice | Diagnostics fallback handles offline safely. |
| **3D Viewer** | ✅ Loads all 12 local scenes, 2.5D, and camera poses | ✅ Loads COLMAP video scene & Synthetic Loft | Orbit, Overview, and First-Person walk active. |

---

## 4. Tests Added & Verification Evidence

1. **New Regression Test Suite (`frontend/src/components/DashboardView.test.tsx`)**:
   - `renders empty state without crashing when scenes array is empty` (PASS)
   - `reproduces and prevents crash when scenes have undefined asset_types` (PASS)
   - `renders recent scenes and triggers open in viewer` (PASS)
   - `triggers capture navigation when clicking workflow cards` (PASS)
   - `displays public showcase banner when in showcase mode` (PASS)

2. **Automated Test Results**:
   - **Frontend Test Suite (Vitest)**: 19 test files, 45 passed (0 failed).
   - **Backend Test Suite (Pytest)**: 110 passed (0 failed).
   - **TypeScript Compilation (`tsc -b`)**: 0 errors.
   - **Vite Production Build (`vite build`)**: Exit code 0, 100% chunks generated.
   - **Vite Preview Server (`localhost:4173`)**: All 9 showcase assets verified with HTTP 200.
