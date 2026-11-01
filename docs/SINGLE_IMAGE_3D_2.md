# Single-Image 3D 2.0

This workflow runs real inference with a user-supplied Depth Anything V2-compatible ONNX model through OpenCV DNN on CPU. There is no fallback depth map. If weights are absent or invalid, the job fails with a specific error.

## Why Depth Anything V2

The existing ONNX adapter has a small dependency surface, can run without CUDA, and is suitable for relative indoor depth previews. Metric3D and ZoeDepth may provide different tradeoffs, but adding them would require separately verified exports, licenses, preprocessing and hardware measurements. They are not silently represented as supported. Depth Anything V2 output here is explicitly relative, not metric.

## Geometry

SpatialForge applies robust percentile normalization and bilateral smoothing while restoring discontinuities supported by image edges. It uses EXIF 35 mm-equivalent focal length when present; otherwise it records the `0.9 × max(image dimension)` pinhole assumption. Depth is back-projected to camera coordinates.

Adjacent pixels become colored PLY mesh triangles only when their depth span is below a local discontinuity limit. This prevents many foreground/background bridges. The viewer computes normals if absent and renders vertex colors. A point cloud is retained as a diagnostic representation. The processing report records vertex/triangle counts, rejected triangles, timings, focal source and depth exaggeration.

Triangles are now assessed independently, degenerate faces are rejected, and unused vertices are compacted before export. The report includes triangle-retention ratio and normalized-depth percentiles. Processing profiles set real mesh-resolution and source-megapixel limits; `auto` selects Fast on the detected 8 GB system.

Depth exaggeration is a visual control from 0.25× to 3×. It never changes the scale label. Navigation is disabled, orbit inspection is the safe default, and unseen geometry is not generated.

## Known limitations

- Hidden surfaces, room interiors behind openings and object backs do not exist.
- Reflections, glass, textureless surfaces and distribution shift can corrupt depth.
- Image edges are not guaranteed to be physical depth boundaries.
- There is no calibrated uncertainty percentage.
- No semantic room-layout model or generative inpainting is bundled. Adding one requires license, model-size, memory and real-data evaluation first. Generated regions must be distinct from observed geometry.

Configure weights with `SPATIALFORGE_DEPTH_MODEL=C:\path\model.onnx`. The repository does not include or download model weights.

Cancellation is checked before inference, immediately after inference and before later exports. Native OpenCV inference already executing cannot be pre-empted safely. Partial output assets are removed after cancellation or failure.

