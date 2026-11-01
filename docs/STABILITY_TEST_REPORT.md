# SpatialForge Stability Test Report

Date: 26 October 2026

## Automated results

- Python: **80 passed**, with one third-party Starlette/httpx deprecation warning.
- Frontend: **33 passed across 17 files**.
- TypeScript project typecheck: passed.
- Vite production build: passed; 620 modules transformed.
- Initial JavaScript: 258.25 kB, 80.13 kB gzip.
- Lazy viewer chunk: 1,027.19 kB, 284.48 kB gzip; the >500 kB advisory remains.

New regression coverage verifies:

- An empty API response renders no fictional scene.
- A rendering-quality change does not remount the WebGL Canvas.
- WebGL context loss produces a visible recoverable state and restoration clears it.
- Valid `.sfscene` packages import through the API.
- Unsupported package extensions are rejected.
- Existing package checksum, traversal, overwrite and asset safety tests still pass.

## Browser smoke test

The actual Vite frontend and FastAPI backend were tested at `http://127.0.0.1:5173/` and `http://127.0.0.1:8000/`.

- Empty startup rendered successfully.
- Three consecutive browser refreshes ended in the same stable empty state.
- Browser console warnings/errors after the refresh sequence: **0**.
- API request behavior: exactly one `GET /api/v1/scenes` per page load; no retry or polling loop.
- The footage-import processing dialog opened and reported zero jobs.
- Backend health, empty scene enumeration and empty job enumeration returned 200 responses.

## Resource lifecycle observations

- Quality changes no longer change the Canvas React key.
- WebGL context listeners are added and removed by one effect.
- First-person pointer, keyboard and pointer-lock listeners retain explicit cleanup.
- Scene requests and POI requests use AbortController cleanup.
- Stale scene responses are prevented from replacing the current scene by a sequence token.
- Cloned scene geometry/material resources are disposed when an asset component unmounts.

This was a functional lifecycle audit, not a long-duration heap/GPU capture. Browser tooling available in this environment did not expose reliable GPU-memory counters. A multi-hour real-scene soak test remains required after Laptop 2 produces an asset.

## Known unverified scenarios

- Rendering and switching a genuine large reconstruction.
- Automatic browser recovery from device-specific GPU resets.
- Long-duration memory stability with large textures and point clouds.
- Concurrent real reconstruction jobs and cancellation.
- Mobile browser and AR stability.
