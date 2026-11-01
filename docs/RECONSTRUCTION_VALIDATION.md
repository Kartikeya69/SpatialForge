# Reconstruction Validation Protocol

## Automated evidence

Run from the repository root:

```powershell
py -m pytest -q
cd frontend
npm test -- --run
npm run typecheck
npm run build
```

Unit tests cover corrupt inputs, duplicate analysis, feature-aware reports, matcher selection, COLMAP command construction/parsing, depth validation/back-projection, discontinuity-aware meshing, scene contracts and viewer rendering/lifecycle behavior. Passing mocks prove interfaces and failure handling, not real reconstruction quality.

## Real multi-photo gate

1. Upload an overlapping room photo set with original EXIF intact.
2. Review the quality/connectivity report and rejected images.
3. On Laptop 2, run the configured COLMAP sparse and dense pipelines.
4. Preserve all commands/logs and confirm no synthetic/test asset entered the scene.
5. Record registered/input images, sparse points, reprojection and track statistics, submodels and durations.
6. Visually inspect camera trajectory, sparse cloud, dense cloud and mesh. State who inspected them.
7. Measure at least three non-collinear landmarks, calibrate scale, and record residual error.
8. Load the packaged scene in Viewer 2.0 and measure load/runtime behavior on the target browser.

Success requires a recognizable scene with plausible cameras and sufficient registration; numeric counts alone do not pass the gate.

## Real single-photo gate

1. Configure reviewed ONNX weights and record their exact model/version/license.
2. Upload a genuine indoor photograph.
3. Confirm the job used real inference and inspect depth boundaries, mesh stretching and texture alignment.
4. Confirm the manifest remains arbitrary-scale and navigation-disabled.
5. Record inference/geometry timings and browser behavior.
6. If ground-truth depth exists, align it using a declared method before computing depth error.

## Current unresolved gates

This laptop has no verified COLMAP execution, real room capture, approved depth weights, or ground-truth depth dataset. Therefore real multi-view output, dense/textured quality, single-image inference quality, Gaussian Splatting, hardware memory limits and physical accuracy remain unverified. Cancellation of an already-running native COLMAP process and automatic retry are also not implemented; the durable failure manifest supports diagnosis and an operator may rerun after correcting the cause. Queued/running state is in memory, while completed/failed stage manifests persist.

Gaussian Splatting remains only a scene-contract extension point. A maintained implementation, compatible license, suitable GPU, dataset conversion, checkpoint/export format and browser renderer must be selected and tested before it becomes a production path.
