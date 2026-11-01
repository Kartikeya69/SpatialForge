# Reconstruction Benchmarks

Benchmarks are evidence records, not marketing scores. Run:

```powershell
py scripts\benchmark_reconstruction.py datasets\<scene_id> --output datasets\<scene_id>\metadata\benchmark.json
```

The command reads durable manifests and reports only values actually present. Missing sparse, dense or single-image measurements are listed under `unavailable`; visual quality is always `false` until a human inspection record is added separately.

For multi-view data record input/registered images, registration ratio, reprojection error, track lengths, sparse points, submodels and runtime. Dense point/mesh complexity should be added only after parsing a real output file. Geometric accuracy requires measured reference points and calibration residuals. Browser performance must be captured on the target device with the diagnostics panel; it is not inferred from file size.

For single-image data, `single_image_quality.json` records input resolution, focal assumption, inference/geometry duration, vertices, triangles and discontinuity rejections. Depth error may only be computed against aligned ground truth. Peak memory is currently unavailable because the OpenCV DNN adapter does not expose reliable per-inference allocation telemetry.

The committed unit fixtures test algorithms but are not benchmark datasets. No cross-model accuracy ranking is claimed.

