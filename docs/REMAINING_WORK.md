# SpatialForge Remaining Work

Updated: 26 October 2026  
Verified completion: **15/51**

## P0 — must happen before the 31 October Round 1 submission

- [ ] Record one 60–90 second real room video at 1080p with slow translation and overlapping views.
- [ ] Transfer it to Laptop 2 and run the existing Capture Engine.
- [ ] Generate `capture_readiness.json`; recapture if it reports blocking findings.
- [ ] Run real COLMAP sparse reconstruction and preserve all logs.
- [ ] Inspect registered cameras and sparse points in COLMAP/MeshLab; record actual metrics.
- [ ] Run the dense adapter if the installed COLMAP build supports the required stereo stage.
- [ ] Measure at least three non-collinear landmarks and create reconstruction/viewer correspondences.
- [ ] Calibrate coordinates and inspect RMS/max error.
- [ ] Assemble the real scene manifest, export a `.sfscene`, import it on Laptop 1, and open it in Viewer 2.0.
- [ ] Verify Walk mode and camera alignment. Do not enable collision/navigation until generated drafts are manually checked.
- [ ] Record the 3–5 minute demonstration using the prepared script.
- [ ] Initialize the intended Git repository or copy this workspace into it; this directory currently has no `.git` metadata.
- [ ] Freeze risky changes by 30 October and archive the exact submitted package.

## P1 — next software work

- [ ] Build one persistent cross-stage job state machine with cancellation and retry.
- [ ] Add the processing dashboard and artifact/log viewer.
- [ ] Add visual/manual editing for draft walkability grids and colliders.
- [ ] Add POI editing and deletion controls to the frontend.
- [ ] Add GLB triangle-mesh floor/obstacle extraction.
- [ ] Derive room/door connectivity and retain multiple valid components rather than only the largest.
- [ ] Add true remaining-distance route instructions and accessibility metadata.

## P2 — reconstruction quality

- [ ] Validate COLMAP dense stereo on Laptop 2.
- [ ] Integrate mesh cleanup and texture baking through a maintained external tool.
- [ ] Select and validate a maintained Gaussian Splat trainer on suitable GPU hardware.
- [ ] Add a real splat renderer with budgets and cleanup.
- [ ] Benchmark completeness and geometric error against measured room dimensions.

## P3 — after the stable submission

- [ ] Multi-floor graph with stairs/elevators.
- [ ] Touch locomotion and real mobile-browser tests.
- [ ] AR anchors, device localization, and relocalization.
- [ ] Semantic suggestions with manual correction.
- [ ] Collaborative annotations and replaceable remote compute.
- [ ] Public production deployment after a hosting target is chosen.

## External inputs required

1. Real smartphone video.
2. Laptop 2 access with the exact COLMAP launcher path.
3. Three or more known landmark correspondences, preferably measured in metres.
4. A decision on hosting and domain for public deployment.
5. Physical Android/iOS devices for mobile and AR validation.
