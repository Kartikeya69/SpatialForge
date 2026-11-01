# Single-Image Reconstruction Limitations

Date: 27 October 2026

SpatialForge's single-photo mode is an **AI-estimated 3D preview**, not a measured digital twin.

## What the mode does

- Applies EXIF orientation to the genuine uploaded photograph.
- Uses a configured monocular relative-depth model.
- Converts relative depth and image color into a viewable 2.5D point cloud.
- Packages the result through the standard SpatialForge scene contract.
- Starts Viewer 2.0 in orbit inspection mode.

## What it cannot establish

- Geometry hidden behind visible surfaces.
- The back sides of objects.
- Absolute metric scale from an ordinary monocular photograph.
- Reliable floor walkability, wall thickness, doorway connectivity or obstacle volume.
- A safe first-person navigation space.
- Reconstruction accuracy comparable to a registered multi-view capture.

Depth discontinuities, reflective surfaces, glass, mirrors, low texture, unusual optics and images far outside the model's training distribution can produce artifacts. The exported depth scale is arbitrary and must not be interpreted as metres.

## Safety and product restrictions

- `metric_scale_status` is `arbitrary`.
- `navigation.enabled` is false.
- Walk mode is disabled in Viewer 2.0.
- No colliders, routes or POIs are inferred automatically.
- Scene copy explicitly states that geometry is AI-estimated and unseen regions are not reconstructed.
- Invalid, constant or non-finite depth outputs fail the job.

## Model setup

SpatialForge contains an OpenCV-DNN ONNX adapter but no bundled weights. Set `SPATIALFORGE_DEPTH_MODEL` to a compatible Depth Anything V2 ONNX file only after reviewing the model's license and provenance. A missing model, unsupported ONNX graph, memory failure or invalid output is reported directly.

Competition evidence should use video or overlapping photographs as the primary digital-twin workflow. Single-photo mode should be presented only as a constrained preview feature.

