# SpatialForge Full Application Audit

Date: 26 October 2026

## Outcome

The production application now starts with an empty, real-data-only dashboard. Synthetic and legacy development data remain available under `test_fixtures/`, but the production dataset root contains no automatically discovered scene or job.

The reported continuous blinking was not reproducible as an exception or navigation loop in the live browser: the console was clean and the API received one scene-list request per page load. The rendering audit did find two concrete canvas-flash mechanisms:

1. `SceneViewport` keyed the React Three Fiber `Canvas` by quality preset. Every quality change destroyed the WebGL renderer, canvas, controls, animation loop and loaded scene, then recreated them.
2. GLTF/PLY loader caches were cleared from component cleanup. React StrictMode intentionally exercises cleanup during development, so a remount could invalidate a shared asset while the replacement tree was loading and make the global loading overlay reappear.

The canvas key and cleanup-time cache invalidation were removed. Scene-owned cloned geometry and materials are still disposed. A lifecycle regression test verifies that a quality change does not remount the canvas.

## Rendering and frontend fixes

- Kept one Canvas instance across quality changes.
- Removed the global Drei loader overlay that could cover and uncover the entire viewport during unrelated asset activity.
- Added explicit `webglcontextlost` and `webglcontextrestored` listeners with cleanup and a recoverable status surface.
- Retained StrictMode.
- Preserved abort controllers and request-sequence protection for stale scene loads.
- Added a stable empty state with real footage and `.sfscene` import actions.
- Corrected retry behavior so discovery failures retry discovery rather than a nonexistent selected scene.
- Kept renderer diagnostics opt-in and telemetry throttled.

## Real-data enforcement

- Moved `scene_synthetic_loft` to `test_fixtures/demo_scenes/scene_synthetic_loft`.
- Moved the two legacy capture/reconstruction development datasets to `test_fixtures/legacy_datasets/`.
- Changed the demo generator default output from `datasets/` to `test_fixtures/demo_scenes/`.
- Production `/api/v1/scenes` and `/api/v1/pipeline/jobs` now return empty collections on a clean workspace.
- Added `POST /api/v1/scenes/import` for user-supplied `.sfscene` archives.
- Package import validates extension, upload size, ZIP structure, traversal safety, duplicate members, checksums, declared sizes, schema, scene ID and embedded scene manifest before atomic installation.
- Existing fixture generators and synthetic unit-test inputs were retained exclusively for testing.

## Backend review

Capture uploads are streamed with a configured size limit and inspected off the event loop. Scene and asset paths remain rooted and validated. Reconstruction subprocess stages already use timeouts and persist real failure manifests. Scene-package imports refuse overwrite. No endpoint was found that fabricated reconstruction completion or artifacts.

Capture and reconstruction cancellation is not implemented. Python futures cannot safely terminate an already-running OpenCV or external COLMAP process with the current executor design; this remains explicit future work rather than a fake cancellation response.

## Files materially affected

- `frontend/src/App.tsx`
- `frontend/src/api.ts`
- `frontend/src/styles.css`
- `frontend/src/viewer/SceneViewport.tsx`
- `frontend/src/viewer/SceneAssets.tsx`
- `frontend/src/viewer/SceneViewport.test.tsx`
- `frontend/src/App.test.tsx`
- `spatialforge/api/main.py`
- `spatialforge/scenes/package.py`
- `scripts/create_demo_scene.py`
- `tests/test_scene_api.py`
- `tests/test_capture_readiness.py`
- `README.md`

## Remaining limitations

- No genuine room video is present in production storage.
- COLMAP is intentionally unavailable on this laptop, so real sparse/dense reconstruction remains blocked on Laptop 2.
- Cancellation and persistent cross-process job scheduling require a process-based worker design.
- The lazy Three.js chunk remains approximately 1.03 MB and produces Vite's size advisory.
- Mobile, AR, real-room alignment and long-duration GPU-memory behavior require device/real-data testing.

