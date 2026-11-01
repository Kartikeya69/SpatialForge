# Multi-Photo Reconstruction 2.0

SpatialForge prepares unordered user photographs for a genuine COLMAP reconstruction. It never substitutes fixture images or writes fabricated COLMAP outputs.

## Preflight and selection

`photo_quality_report.json` records the decoded resolution, aspect ratio, standardized Laplacian sharpness, exposure, contrast, entropy, saturation, ORB feature count/density, SHA-256, perceptual hash, EXIF camera identity and 35 mm-equivalent focal estimate for every input. The blur cutoff is relative to the set median, rather than one camera-independent constant.

Fast, Balanced and Quality profiles bound analysis resolution, feature count, candidate pairs, source megapixels and photo count. The `auto` profile uses detected physical RAM and selects Fast on this 8 GB machine. Fundamental-matrix RANSAC verifies general multi-view overlap, with a homography fallback for planar/degenerate cases. Per-image graph degree highlights weakly connected views.

ORB ratio-test matches plus homography RANSAC provide a conservative overlap graph. Connected components, isolated photographs, perspective-change flags, exact duplicates and near-duplicates are reported. A near-duplicate is excluded only when it is also geometrically redundant; the sharper view is retained. The upload UI can retain noncritical blur/redundancy warnings, while exact duplicates and invalid files remain excluded. These measurements are preflight heuristics: only successful COLMAP registration proves SfM connectivity.

## COLMAP behavior

- Ordered video frames use sequential matching.
- Unordered photo sets up to `max_exhaustive_images` use exhaustive matching.
- Larger unordered sets require an explicitly configured, existing vocabulary tree. The pipeline fails safely instead of launching an unbounded exhaustive match.
- Consistent EXIF-derived focal estimates initialize `SIMPLE_PINHOLE` or `SIMPLE_RADIAL`; varying camera identities disable single-camera sharing. Missing or inconsistent EXIF falls back to COLMAP estimation and is reported.
- Sparse reports include registered/input ratio, point count, submodel count, reprojection statistics and track-length statistics when COLMAP exports tracks.

Dense presets change real COLMAP parameters: image size, PatchMatch window radius/sample count, and fusion pixel/reprojection thresholds. `low`, `balanced`, and `high` are computational presets, not quality guarantees. Dense PLY/mesh output is not described as textured GLB: texture generation and GLB conversion require a separately verified external toolchain.

## Scale and completeness

SfM output has arbitrary scale until measured correspondences are solved with `scripts/calibrate_scene.py`. The existing similarity calibration records scale, alignment and RMSE; it never infers metres from image content.

`reconstruction_quality.json` separates measured sparse evidence from recommendations. Unregistered images, multiple submodels and elevated reprojection error can identify likely recapture needs. It cannot certify hidden surfaces, mesh holes, recognizability or geometric accuracy without inspection and reference measurements.

## Configuration

Edit `configs/reconstruction.yaml`. A vocabulary tree is user-supplied; SpatialForge does not download one. COLMAP remains an external Laptop 2 dependency.

Photo preprocessing supports cooperative cancellation and records real completed/total analysis units without inventing a percentage. Cancelled or failed jobs remove partially exported reconstruction images.

