# SpatialForge Real-Data Verification

Date: 26 October 2026

## Production data lineage

| Feature | Accepted data source | Validation |
| --- | --- | --- |
| Capture | User-uploaded MP4 or MOV | Extension, size, OpenCV readability, metadata and frame-quality manifest |
| Sparse reconstruction | Accepted capture images | Actual COLMAP subprocess output and required model artifacts |
| Dense reconstruction | Successful sparse model | Actual undistortion, stereo, fusion and meshing stage artifacts |
| Viewer scene | User-imported `.sfscene` or assembled reconstruction | Checksummed package inventory and strict scene-manifest schema |
| POIs | Explicit user creation or imported declared POI asset | Scene-scoped schema validation and persistence |
| Obstacles/walkability | Declared collider/grid assets generated from geometry or manually reviewed | Bounds, grid and collider schema validation |
| Routes | Current camera position, selected scene POI and current navigation grid | Runtime A* search, clearance, unreachable-target error handling |
| Performance metrics | Active WebGL renderer | Runtime frame samples and renderer counters only while diagnostics are open |
| Processing status | Persisted stage manifests and live workers | No invented percentages or completion state |

## Fixture isolation

Synthetic assets are retained at:

- `test_fixtures/demo_scenes/`
- `test_fixtures/legacy_datasets/`

They are outside the production `datasets/` root and cannot appear in ordinary scene discovery. Automated tests create additional temporary synthetic data under pytest-managed temporary directories. The demo generator also defaults to `test_fixtures/demo_scenes`.

## Clean-start behavior

With `datasets/` empty:

- `GET /api/v1/scenes` returns `{"scenes": [], "count": 0}`.
- `GET /api/v1/pipeline/jobs` returns `{"jobs": [], "count": 0}`.
- The browser displays “No digital twins yet.”
- No Three.js canvas is created until a validated scene exists.
- The user can import footage or a portable scene package.

## Still requiring real-world evidence

The capture, reconstruction, calibration and packaging algorithms are tested independently, but the complete smartphone-video-to-browser chain has not been certified with genuine room footage. Required evidence is:

1. A real 60–90 second indoor smartphone video.
2. Successful frame acceptance with adequate overlap.
3. Actual COLMAP sparse registration on Laptop 2.
4. Dense output or another explicitly selected visual representation.
5. Measured scale calibration.
6. Visual inspection of geometry, camera trajectory and navigation alignment.

SpatialForge must report the genuine failure if any stage fails; no synthetic scene is used as fallback.

