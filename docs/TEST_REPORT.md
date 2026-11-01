# SpatialForge Test Report

Date: 27 October 2026

## Automated verification

Final automated results:

- Python: **97 passed**, one third-party Starlette/httpx deprecation warning.
- Frontend: **34 passed across 17 files**.
- TypeScript project typecheck: passed.
- Vite production build: passed, 620 modules transformed.
- Initial application JavaScript: 264.32 kB (82.07 kB gzip).
- Lazy Three.js viewer chunk: 1,027.62 kB (284.58 kB gzip); Vite's >500 kB warning remains a documented performance limitation.

Commands:

```powershell
python -m pytest -q
cd frontend
npm test -- --run
npm run typecheck
npm run build
```

Coverage includes capture/video failures, adaptive photo-set analysis, exact duplicates, bounded matcher selection, COLMAP argument construction/parsing, sparse quality reports, edge-aware depth meshing, scene contracts and asset safety, POI concurrency, A* behavior, calibration, scene packages, capture readiness, dense stage sequencing, reconstructed-scene assembly, viewer interactions, coordinate transforms, movement, collisions, minimap transforms, resource cleanup and navigation state.

## Browser verification already performed

On the deterministic scene, the browser successfully selected Meeting Room A directly from the minimap, requested a 7.9 m obstacle-aware route, rendered the simplified route on the 3D floor and minimap, and displayed remaining distance. Earlier interaction checks also covered route cancellation and the POI authoring dialog. This is synthetic navigation validation, not real reconstruction evidence.

## Blocked tests

- Real smartphone video to sparse COLMAP reconstruction.
- Real dense stereo, fusion and mesh generation.
- Visual inspection of a real reconstructed room in the browser.
- Metric reconstruction accuracy and reconstruction/navigation alignment.
- Mobile/touch/AR devices.
- Public production deployment.
- Timed cross-laptop rehearsal.

Hardware-dependent commands and expected evidence are documented in `RECONSTRUCTION_GUIDE.md`.
