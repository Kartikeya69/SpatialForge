# Universal Capture Pipeline

Date: 27 October 2026

SpatialForge accepts three user-supplied capture modes through one processing dashboard. Production startup remains empty until the user uploads data or imports a validated scene package.

## Shared storage contract

Every job receives a collision-resistant `scene_*` directory with `input/`, `images/`, `metadata/`, and `logs/`. Original uploads are preserved in `input/`. Generated reconstruction images use normalized JPEG files directly below `images/`. Durable manifests, rather than invented percentages, drive the processing dashboard.

## Photo sets

Endpoint: `POST /api/v1/captures/photos` with repeated multipart field `photos`.

Accepted extensions are JPG, JPEG, PNG, HEIC and HEIF. HEIC/HEIF succeeds only when the installed Pillow build has a compatible decoder; otherwise the job records an actionable decoder error. SpatialForge applies EXIF orientation, validates resolution and blur, conservatively rejects duplicate images, exports ordered JPEGs, and writes `capture_manifest.json` with `capture_mode: photo_set`.

The resulting image inventory is accepted by the existing COLMAP backend. Three views are the technical minimum to start multi-view geometry, but image count is never treated as proof of viability. Feature overlap, camera registration and actual reconstruction artifacts determine success.

## Video

Endpoint: `POST /api/v1/captures` with multipart field `video`.

Supported container extensions are MP4, MOV, M4V, MKV and WebM. Actual decoding capability is verified by OpenCV after upload. Frames are streamed rather than loaded into memory, sampled at the configured rate, checked for resolution/blur/duplicates, and written to the same COLMAP-ready image contract as a photo set.

## Single photo

Endpoint: `POST /api/v1/captures/single` with multipart field `image`.

The worker validates and EXIF-orients the image, executes a user-configured Depth Anything V2-compatible ONNX model through OpenCV DNN on CPU, validates the relative depth output, back-projects image pixels into colored camera-space geometry, writes a PLY point cloud and produces a Viewer 2.0 scene manifest.

Set the model path before starting the API:

```powershell
$env:SPATIALFORGE_DEPTH_MODEL = "C:\Models\depth_anything_v2.onnx"
python -m uvicorn spatialforge.api.main:app --reload
```

SpatialForge does not download weights. The operator must verify the selected model file's source, compatibility and license. Missing or incompatible weights produce a real failed job; there is no synthetic fallback.

## Viewer policy

Photo/video reconstructions use the existing GLB, glTF or PLY renderers and gain walk navigation only after reviewed navigation geometry exists. Single-photo scenes start in orbit mode, declare arbitrary scene units, disable walk mode, and identify themselves as AI-estimated 2.5D previews.

## Dashboard stages

- Photo set: photo validation → readiness → sparse reconstruction → dense reconstruction → viewer package.
- Video: frame extraction → readiness → sparse reconstruction → dense reconstruction → viewer package.
- Single photo: image validation → depth inference → geometry generation → packaging.

The COLMAP action remains explicit. If COLMAP is absent, the persisted reconstruction manifest contains the actual environment error.

