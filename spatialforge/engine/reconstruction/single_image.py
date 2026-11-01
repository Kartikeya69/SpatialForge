"""Single-image relative-depth inference and explicitly non-metric 2.5D export."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from spatialforge import __version__
from spatialforge.engine.ingestion.images import decode_oriented_image
from spatialforge.engine.ingestion.photo_analysis import focal_pixels_from_metadata, read_camera_metadata
from spatialforge.scenes.schema import SceneManifest
from spatialforge.engine.processing_profiles import (
    ProcessingCancelled,
    ProcessingProfileName,
    resolve_processing_profile,
    validate_memory_headroom,
)


class DepthModelUnavailable(RuntimeError):
    """Raised when configured depth weights are absent or incompatible."""


class SingleImageReconstructionError(RuntimeError):
    """Raised when relative depth cannot produce valid display geometry."""


DepthEstimator = Callable[[np.ndarray], np.ndarray]

_CACHED_SESSION = None
_CACHED_MODEL_PATH: Path | None = None
_CACHED_INPUT_NAME: str | None = None
_CACHED_OUTPUT_NAME: str | None = None


class DepthAnythingV2Onnx:
    """CPU-compatible adapter for user-supplied Depth Anything V2 ONNX weights."""

    def __init__(self, model_path: str | Path | None = None, input_size: int = 518) -> None:
        global _CACHED_SESSION, _CACHED_MODEL_PATH, _CACHED_INPUT_NAME, _CACHED_OUTPUT_NAME
        configured = model_path or os.getenv("SPATIALFORGE_DEPTH_MODEL")
        if not configured:
            raise DepthModelUnavailable(
                "Single-photo depth weights are not configured. Set SPATIALFORGE_DEPTH_MODEL "
                "to a compatible Depth Anything V2 ONNX file after reviewing its license."
            )
        self.model_path = Path(configured).expanduser().resolve()
        if not self.model_path.is_file() or self.model_path.suffix.lower() != ".onnx":
            raise DepthModelUnavailable(f"Depth model is missing or is not an ONNX file: {self.model_path}")
        if input_size < 64:
            raise ValueError("input_size must be at least 64")
        self.input_size = input_size
        self._session = None
        self.net = None

        if _CACHED_SESSION is not None and _CACHED_MODEL_PATH == self.model_path:
            self._session = _CACHED_SESSION
            self._input_name = _CACHED_INPUT_NAME
            self._output_name = _CACHED_OUTPUT_NAME
            return

        # Prefer ONNX Runtime for CPU inference if available (handles modern transformer operators),
        # with fallback to OpenCV DNN.
        loaded = False
        try:
            import onnxruntime as ort

            session_options = ort.SessionOptions()
            session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._session = ort.InferenceSession(
                str(self.model_path), session_options, providers=["CPUExecutionProvider"]
            )
            self._input_name = self._session.get_inputs()[0].name
            self._output_name = self._session.get_outputs()[0].name
            _CACHED_SESSION = self._session
            _CACHED_MODEL_PATH = self.model_path
            _CACHED_INPUT_NAME = self._input_name
            _CACHED_OUTPUT_NAME = self._output_name
            loaded = True
        except Exception:
            pass

        if not loaded:
            try:
                self.net = cv2.dnn.readNetFromONNX(str(self.model_path))
                self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
                loaded = True
            except cv2.error as exc:
                raise DepthModelUnavailable(f"Could not load the configured depth model: {exc}") from exc

    def __call__(self, image: np.ndarray) -> np.ndarray:
        height, width = image.shape[:2]
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        if self._session is not None:
            # Preserve aspect ratio while aligning dimensions to multiple of 14 for Depth Anything V2
            scale = self.input_size / max(height, width)
            target_h = max(14, int(round(height * scale / 14.0)) * 14)
            target_w = max(14, int(round(width * scale / 14.0)) * 14)
            resized = cv2.resize(rgb, (target_w, target_h), interpolation=cv2.INTER_CUBIC)
        else:
            resized = cv2.resize(rgb, (self.input_size, self.input_size), interpolation=cv2.INTER_CUBIC)

        normalized = resized.astype(np.float32) / 255.0
        normalized = (normalized - np.array([0.485, 0.456, 0.406], np.float32)) / np.array(
            [0.229, 0.224, 0.225], np.float32
        )
        blob = np.transpose(normalized, (2, 0, 1))[None]
        try:
            if self._session is not None:
                output = np.asarray(
                    self._session.run([self._output_name], {self._input_name: blob})[0], dtype=np.float32
                ).squeeze()
            else:
                self.net.setInput(blob)
                output = np.asarray(self.net.forward(), dtype=np.float32).squeeze()
        except Exception as exc:
            message = str(exc)
            if "memory" in message.lower() or "alloc" in message.lower():
                raise SingleImageReconstructionError(
                    "Depth inference ran out of memory. Use a smaller compatible model or another machine."
                ) from exc
            raise SingleImageReconstructionError(f"Depth inference failed: {message}") from exc
        if output.ndim != 2:
            raise SingleImageReconstructionError(f"Depth model returned an unsupported shape: {output.shape}")
        depth = cv2.resize(output, (width, height), interpolation=cv2.INTER_CUBIC)
        return validate_relative_depth(depth)


def validate_relative_depth(depth: np.ndarray) -> np.ndarray:
    values = np.asarray(depth, dtype=np.float32)
    if values.ndim != 2 or values.size == 0:
        raise SingleImageReconstructionError("Depth output must be a non-empty 2D array")
    if not np.isfinite(values).all():
        raise SingleImageReconstructionError("Depth output contains non-finite values")
    low, high = np.percentile(values, [1, 99])
    if high - low < 1e-6:
        raise SingleImageReconstructionError("Depth output has no usable variation")
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def refine_relative_depth(depth: np.ndarray, image: np.ndarray) -> np.ndarray:
    """Smooth depth while preserving true depth edges without injecting texture staircases."""
    normalized = validate_relative_depth(depth).astype(np.float32)
    # Edge-preserving bilateral filter on depth directly preserves physical depth steps
    # while smoothing out sensor and high-frequency inference noise
    smoothed = cv2.bilateralFilter(normalized, 5, 0.05, 5)
    return validate_relative_depth(smoothed)


def depth_to_colored_points(
    image: np.ndarray,
    relative_depth: np.ndarray,
    *,
    focal_length_pixels: float | None = None,
    max_dimension: int = 320,
    near: float = 0.7,
    depth_range: float = 2.3,
    return_rich: bool = False,
) -> tuple[np.ndarray, np.ndarray] | tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float]:
    """Back-project relative depth into a colored, arbitrary-scale camera-space grid with analytical normals and UVs."""
    if image.shape[:2] != relative_depth.shape:
        raise ValueError("Image and depth dimensions must match")
    height, width = relative_depth.shape
    scale = min(1.0, max_dimension / max(height, width))
    target = (max(2, round(width * scale)), max(2, round(height * scale)))
    target_width, target_height = target
    color = cv2.resize(image, target, interpolation=cv2.INTER_AREA)
    depth = cv2.resize(relative_depth, target, interpolation=cv2.INTER_AREA)

    focal = (focal_length_pixels or max(width, height) * 0.9) * scale
    if focal <= 0:
        raise ValueError("focal_length_pixels must be positive")

    z_distance = near + (1.0 - depth) * depth_range
    u, v = np.meshgrid(np.arange(target_width, dtype=np.float32), np.arange(target_height, dtype=np.float32))
    cx = (target_width - 1.0) / 2.0
    cy = (target_height - 1.0) / 2.0
    x = (u - cx) * z_distance / focal
    y = -(v - cy) * z_distance / focal
    z = -z_distance

    points = np.column_stack((x.ravel(), y.ravel(), z.ravel())).astype(np.float32)
    colors = cv2.cvtColor(color, cv2.COLOR_BGR2RGB).reshape(-1, 3).astype(np.uint8)

    if not return_rich:
        return points, colors

    # UV coordinates: s in [0, 1] (left-to-right), t in [0, 1] (bottom-to-top for Three.js)
    s = (u / (target_width - 1.0)).ravel().astype(np.float32)
    t = (1.0 - (v / (target_height - 1.0))).ravel().astype(np.float32)
    uvs = np.column_stack((s, t))

    # Analytical grid surface normals via central differences
    points_grid = np.stack([x, y, z], axis=-1)
    vu = np.zeros_like(points_grid)
    vv = np.zeros_like(points_grid)
    vu[:, 1:-1] = points_grid[:, 2:] - points_grid[:, :-2]
    vu[:, 0] = points_grid[:, 1] - points_grid[:, 0]
    vu[:, -1] = points_grid[:, -1] - points_grid[:, -2]

    vv[1:-1, :] = points_grid[2:, :] - points_grid[:-2, :]
    vv[0, :] = points_grid[1, :] - points_grid[0, :]
    vv[-1, :] = points_grid[-1, :] - points_grid[-2, :]

    # vv points down (-Y), vu points right (+X). Cross(vv, vu) points towards +Z (camera)
    grid_normals = np.cross(vv, vu)
    norm_len = np.linalg.norm(grid_normals, axis=-1, keepdims=True)
    grid_normals = grid_normals / np.maximum(norm_len, 1e-9)
    normals = grid_normals.reshape(-1, 3).astype(np.float32)

    fov_y_deg = float(2.0 * np.arctan((target_height / 2.0) / focal) * (180.0 / np.pi))
    median_z = float(np.median(z_distance))

    return points, colors, normals, uvs, fov_y_deg, median_z


def validate_mesh_geometry(
    points: np.ndarray,
    faces: np.ndarray,
    *,
    min_faces: int = 50,
) -> None:
    """Rigorously validate mesh topology and geometry integrity before publishing."""
    if len(points) == 0:
        raise SingleImageReconstructionError("Mesh contains zero vertices")
    if len(faces) < min_faces:
        raise SingleImageReconstructionError(
            f"Mesh has only {len(faces)} faces, below minimum of {min_faces}"
        )
    if not np.isfinite(points).all():
        raise SingleImageReconstructionError("Mesh contains non-finite vertex coordinates")
    if faces.min() < 0 or faces.max() >= len(points):
        raise SingleImageReconstructionError("Mesh face indices exceed vertex bounds")

    v0 = points[faces[:, 0]]
    v1 = points[faces[:, 1]]
    v2 = points[faces[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    fn_len = np.linalg.norm(fn, axis=1)
    if np.any(fn_len < 1e-12):
        raise SingleImageReconstructionError("Mesh contains zero-area degenerate faces")

    # Front-facing verification: faces must point towards camera (+Z direction)
    nz_ratio = fn[:, 2] / np.maximum(fn_len, 1e-9)
    backfacing_count = int(np.sum(nz_ratio < 0.0))
    if backfacing_count > 0:
        raise SingleImageReconstructionError(
            f"Mesh topology error: {backfacing_count} faces are back-facing or inverted"
        )

    # Plausible bounding box bounds
    bbox_min = points.min(axis=0)
    bbox_max = points.max(axis=0)
    span = bbox_max - bbox_min
    if np.any(span < 1e-4) or np.any(span > 100.0):
        raise SingleImageReconstructionError(f"Mesh bounding box span is implausible: {span}")


def depth_to_colored_mesh(
    image: np.ndarray,
    relative_depth: np.ndarray,
    *,
    focal_length_pixels: float | None = None,
    max_dimension: int = 320,
    near: float = 0.7,
    depth_range: float = 2.3,
    discontinuity_threshold: float = 0.08,
    return_rich: bool = False,
) -> (
    tuple[np.ndarray, np.ndarray, np.ndarray, int]
    | tuple[np.ndarray, np.ndarray, np.ndarray, int, np.ndarray, np.ndarray, float, float]
):
    """Back-project depth and triangulate strictly continuous, front-facing image cells."""
    points, colors, raw_normals, uvs, fov_y_deg, median_z = depth_to_colored_points(
        image,
        relative_depth,
        focal_length_pixels=focal_length_pixels,
        max_dimension=max_dimension,
        near=near,
        depth_range=depth_range,
        return_rich=True,
    )
    height, width = relative_depth.shape
    scale = min(1.0, max_dimension / max(height, width))
    target_width, target_height = max(2, round(width * scale)), max(2, round(height * scale))
    focal = (focal_length_pixels or max(width, height) * 0.9) * scale

    faces: list[tuple[int, int, int]] = []
    rejected = 0

    for row in range(target_height - 1):
        for column in range(target_width - 1):
            a = row * target_width + column
            b, c, d = a + 1, a + target_width, a + target_width + 1

            for tri in ((a, c, b), (b, c, d)):
                p0, p1, p2 = points[tri[0]], points[tri[1]], points[tri[2]]
                z0, z1, z2 = -p0[2], -p1[2], -p2[2]

                # 1. Reject edge depth discontinuities relative to local depth (occlusion boundaries)
                rel_d01 = abs(z1 - z0) / min(z0, z1)
                rel_d12 = abs(z2 - z1) / min(z1, z2)
                rel_d20 = abs(z0 - z2) / min(z2, z0)
                if max(rel_d01, rel_d12, rel_d20) > discontinuity_threshold:
                    rejected += 1
                    continue

                # 2. Reject edge lengths exceeding expected grid step (preventing stretched tear-polygons)
                z_min = min(z0, z1, z2)
                expected_step = (z_min / focal) * np.sqrt(2.0)
                e01 = np.linalg.norm(p1 - p0)
                e12 = np.linalg.norm(p2 - p1)
                e20 = np.linalg.norm(p0 - p2)
                if max(e01, e12, e20) > 3.8 * expected_step:
                    rejected += 1
                    continue

                # 3. Reject back-facing or steep grazing triangles (outward normal must face camera)
                n = np.cross(p1 - p0, p2 - p0)
                n_len = np.linalg.norm(n)
                if n_len < 1e-9:
                    rejected += 1
                    continue
                nz_ratio = n[2] / n_len
                # In camera space looking down -Z, outward normal must have positive Z component (facing camera)
                if nz_ratio < 0.05:
                    rejected += 1
                    continue

                faces.append(tri)

    face_array = np.asarray(faces, dtype=np.int32).reshape(-1, 3)
    if len(face_array) == 0:
        raise SingleImageReconstructionError("Depth discontinuities rejected every mesh triangle")

    used = np.unique(face_array.ravel())
    remap = np.full(len(points), -1, dtype=np.int32)
    remap[used] = np.arange(len(used), dtype=np.int32)
    remapped_faces = remap[face_array]
    cleaned_points = points[used]
    cleaned_colors = colors[used]
    cleaned_normals = raw_normals[used]
    cleaned_uvs = uvs[used]

    # Validate mesh topology before returning
    validate_mesh_geometry(cleaned_points, remapped_faces, min_faces=max(10, len(face_array) // 10))

    if not return_rich:
        return cleaned_points, cleaned_colors, remapped_faces, rejected

    return (
        cleaned_points,
        cleaned_colors,
        remapped_faces,
        rejected,
        cleaned_normals,
        cleaned_uvs,
        fov_y_deg,
        median_z,
    )


def write_colored_ply(path: str | Path, points: np.ndarray, colors: np.ndarray) -> Path:
    """Export point cloud to PLY with positions and vertex colors."""
    output = Path(path)
    if points.ndim != 2 or points.shape[1] != 3 or colors.shape != points.shape:
        raise ValueError("points and colors must both have shape (N, 3)")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", encoding="ascii", newline="\n") as stream:
        stream.write("ply\nformat ascii 1.0\n")
        stream.write(f"element vertex {len(points)}\n")
        stream.write("property float x\nproperty float y\nproperty float z\n")
        stream.write("property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
        for point, color in zip(points, colors, strict=True):
            stream.write(
                f"{point[0]:.6g} {point[1]:.6g} {point[2]:.6g} "
                f"{int(color[0])} {int(color[1])} {int(color[2])}\n"
            )
    temporary.replace(output)
    return output


def write_colored_mesh_ply(
    path: str | Path,
    points: np.ndarray,
    colors: np.ndarray,
    faces: np.ndarray,
    normals: np.ndarray | None = None,
    uvs: np.ndarray | None = None,
) -> Path:
    """Export 2.5D surface mesh to PLY with positions, normals, UVs, and vertex colors."""
    output = Path(path)
    if points.ndim != 2 or points.shape[1] != 3 or colors.shape != points.shape:
        raise ValueError("points and colors must both have shape (N, 3)")
    if faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError("faces must have shape (M, 3)")
    has_normals = normals is not None and normals.shape == points.shape
    has_uvs = uvs is not None and uvs.shape == (len(points), 2)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", encoding="ascii", newline="\n") as stream:
        stream.write("ply\nformat ascii 1.0\n")
        stream.write(f"element vertex {len(points)}\n")
        stream.write("property float x\nproperty float y\nproperty float z\n")
        if has_normals:
            stream.write("property float nx\nproperty float ny\nproperty float nz\n")
        if has_uvs:
            stream.write("property float s\nproperty float t\n")
        stream.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        stream.write(f"element face {len(faces)}\nproperty list uchar int vertex_indices\nend_header\n")

        for i in range(len(points)):
            p = points[i]
            c = colors[i]
            line = f"{p[0]:.6g} {p[1]:.6g} {p[2]:.6g} "
            if has_normals:
                n = normals[i]
                line += f"{n[0]:.5f} {n[1]:.5f} {n[2]:.5f} "
            if has_uvs:
                uv = uvs[i]
                line += f"{uv[0]:.6f} {uv[1]:.6f} "
            line += f"{int(c[0])} {int(c[1])} {int(c[2])}\n"
            stream.write(line)

        for face in faces:
            stream.write(f"3 {int(face[0])} {int(face[1])} {int(face[2])}\n")

    temporary.replace(output)
    return output


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


class SingleImagePipeline:
    def __init__(self, estimator: DepthEstimator | None = None) -> None:
        self.estimator = estimator

    def process(
        self,
        input_path: str | Path,
        scene_dir: str | Path,
        original_filename: str,
        *,
        depth_exaggeration: float = 1.0,
        profile: ProcessingProfileName = "auto",
        is_cancelled: Callable[[], bool] | None = None,
        on_stage: Callable[[str], None] | None = None,
    ) -> dict:
        if not 0.25 <= depth_exaggeration <= 3.0:
            raise ValueError("depth_exaggeration must be between 0.25 and 3.0")
        started = time.perf_counter()
        active_profile = resolve_processing_profile(profile)
        memory = validate_memory_headroom(active_profile)
        scene = Path(scene_dir).expanduser().resolve()
        for child in ("input", "images", "assets", "metadata", "logs"):
            (scene / child).mkdir(parents=True, exist_ok=True)
        process_manifest_path = scene / "metadata" / "single_image_manifest.json"
        process_manifest = {
            "scene_id": scene.name,
            "capture_mode": "single_photo",
            "original_input_filename": original_filename,
            "processing_status": "processing",
            "current_stage": "image_validation",
            "model": "Depth Anything V2 ONNX",
            "metric_scale_status": "arbitrary",
            "warnings": [
                "This is an AI-estimated 2.5D preview. Hidden geometry and absolute metric scale are unknown."
            ],
            "artifacts": {},
            "pipeline_version": __version__,
            "processing_profile": active_profile.to_dict(),
            "memory_at_start": memory,
        }
        created_outputs: list[Path] = []
        _write_json(process_manifest_path, process_manifest)
        try:
            if is_cancelled and is_cancelled():
                raise ProcessingCancelled("Single-image processing was cancelled")
            image = decode_oriented_image(input_path)
            megapixels = image.shape[0] * image.shape[1] / 1_000_000
            if megapixels > active_profile.max_source_megapixels:
                raise SingleImageReconstructionError(
                    f"Input is {megapixels:.1f} MP, above the {active_profile.name} profile limit of "
                    f"{active_profile.max_source_megapixels:.1f} MP"
                )
            camera_metadata = read_camera_metadata(input_path)
            focal_pixels = focal_pixels_from_metadata(camera_metadata, image.shape[1])
            focal_source = "exif_35mm_equivalent" if focal_pixels is not None else "assumed_0.9_max_dimension"
            process_manifest["image"] = {"width": image.shape[1], "height": image.shape[0]}
            process_manifest["current_stage"] = "depth_inference"
            if on_stage:
                on_stage("depth_inference")
            _write_json(process_manifest_path, process_manifest)
            profile_input_sizes = {
                "fast": 392,
                "balanced": 518,
                "quality": 644,
            }
            model_input_size = profile_input_sizes.get(active_profile.name, 518)
            estimator = self.estimator or DepthAnythingV2Onnx(input_size=model_input_size)
            inference_started = time.perf_counter()
            depth = refine_relative_depth(estimator(image), image)
            inference_seconds = time.perf_counter() - inference_started
            if is_cancelled and is_cancelled():
                raise ProcessingCancelled("Single-image processing was cancelled after depth inference")
            process_manifest["current_stage"] = "geometry_generation"
            if on_stage:
                on_stage("geometry_generation")
            _write_json(process_manifest_path, process_manifest)
            geometry_started = time.perf_counter()
            (
                points,
                colors,
                faces,
                rejected_faces,
                normals,
                uvs,
                fov_y_deg,
                median_z,
            ) = depth_to_colored_mesh(
                image,
                depth,
                focal_length_pixels=focal_pixels,
                max_dimension=active_profile.geometry_max_dimension,
                depth_range=2.3 * depth_exaggeration,
                return_rich=True,
            )
            mesh_path = write_colored_mesh_ply(
                scene / "assets" / "single-photo-depth-mesh.ply",
                points,
                colors,
                faces,
                normals=normals,
                uvs=uvs,
            )
            created_outputs.append(mesh_path)
            ply_path = write_colored_ply(scene / "assets" / "single-photo-depth.ply", points, colors)
            created_outputs.append(ply_path)
            geometry_seconds = time.perf_counter() - geometry_started

            # 1. High-resolution source texture export for 1:1 photorealistic rendering
            texture_path = scene / "assets" / "texture.jpg"
            if not cv2.imwrite(str(texture_path), image, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                raise SingleImageReconstructionError("Texture asset could not be written")
            created_outputs.append(texture_path)

            # 2. Raw 16-bit relative depth PNG
            preview = (depth * 65535).astype(np.uint16)
            depth_path = scene / "metadata" / "relative_depth.png"
            if not cv2.imwrite(str(depth_path), preview):
                raise SingleImageReconstructionError("Relative depth preview could not be written")
            created_outputs.append(depth_path)

            # 3. Diagnostic visualizations: Grayscale, Heatmap, Discontinuity Map
            gray8 = (depth * 255.0).astype(np.uint8)
            grayscale_path = scene / "metadata" / "depth_grayscale.png"
            cv2.imwrite(str(grayscale_path), gray8)
            created_outputs.append(grayscale_path)

            heatmap = cv2.applyColorMap(gray8, cv2.COLORMAP_TURBO)
            heatmap_path = scene / "metadata" / "depth_heatmap.png"
            cv2.imwrite(str(heatmap_path), heatmap)
            created_outputs.append(heatmap_path)

            depth_f32 = depth.astype(np.float32)
            gx = cv2.Sobel(depth_f32, cv2.CV_32F, 1, 0, ksize=3)
            gy = cv2.Sobel(depth_f32, cv2.CV_32F, 0, 1, ksize=3)
            grad = cv2.magnitude(gx, gy)
            grad_norm = np.clip(grad * 8.0, 0.0, 1.0)
            grad8 = (grad_norm * 255.0).astype(np.uint8)
            discontinuity_overlay = cv2.applyColorMap(grad8, cv2.COLORMAP_MAGMA)
            discontinuity_path = scene / "metadata" / "depth_discontinuity.png"
            cv2.imwrite(str(discontinuity_path), discontinuity_overlay)
            created_outputs.append(discontinuity_path)

            # 4. Diagnostic statistics & 20-bin histogram
            hist, bin_edges = np.histogram(depth, bins=20, range=(0.0, 1.0))
            diagnostics_doc = {
                "schema_version": "1.0.0",
                "scene_id": scene.name,
                "depth_statistics": {
                    "min": float(depth.min()),
                    "max": float(depth.max()),
                    "mean": float(depth.mean()),
                    "median": float(np.median(depth)),
                    "std": float(depth.std()),
                    "nan_count": int(np.isnan(depth).sum()),
                    "inf_count": int(np.isinf(depth).sum()),
                    "percentiles": {
                        "p01": round(float(np.percentile(depth, 1)), 6),
                        "p05": round(float(np.percentile(depth, 5)), 6),
                        "p25": round(float(np.percentile(depth, 25)), 6),
                        "p50": round(float(np.percentile(depth, 50)), 6),
                        "p75": round(float(np.percentile(depth, 75)), 6),
                        "p95": round(float(np.percentile(depth, 95)), 6),
                        "p99": round(float(np.percentile(depth, 99)), 6),
                    },
                    "histogram_20_bins": {
                        "counts": hist.tolist(),
                        "bin_edges": [round(float(b), 4) for b in bin_edges],
                    },
                },
                "mesh_validation": {
                    "vertex_count": len(points),
                    "triangle_count": len(faces),
                    "rejected_discontinuities_or_folded": rejected_faces,
                    "retention_percentage": round((len(faces) / max(1, len(faces) + rejected_faces)) * 100.0, 2),
                    "all_normals_frontfacing": True,
                    "source_camera": {
                        "position": [0.0, 0.0, 0.0],
                        "look_at": [0.0, 0.0, round(-median_z, 4)],
                        "fov_y_degrees": round(fov_y_deg, 2),
                    },
                },
            }
            diagnostics_path = scene / "metadata" / "depth_diagnostics.json"
            _write_json(diagnostics_path, diagnostics_doc)
            created_outputs.append(diagnostics_path)

            minimum = points.min(axis=0)
            maximum = points.max(axis=0)
            maximum = np.maximum(maximum, minimum + 1e-4)
            scene_manifest = SceneManifest.model_validate({
                "schema_version": "1.0.0",
                "scene_id": scene.name,
                "scene_name": f"Single-photo: {Path(original_filename).stem}",
                "description": "AI-estimated non-metric 2.5D preview from one user photograph. Unseen geometry is not reconstructed.",
                "synthetic_demo": False,
                "processing_status": "completed",
                "coordinate_system": {
                    "handedness": "right",
                    "up_axis": "Y",
                    "forward_axis": "-Z",
                    "source_convention": "Pinhole back-projection of relative monocular depth",
                    "source_to_scene_matrix_row_major": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                },
                "units": {"name": "scene_unit", "metric_scale_status": "arbitrary", "meters_per_unit": None},
                "origin": [0, 0, 0],
                "bounding_box": {"minimum": minimum.tolist(), "maximum": maximum.tolist()},
                "reconstruction": {
                    "backend": "depth_anything_v2_onnx",
                    "backend_version": None,
                    "source": "reconstruction",
                    "status": "completed",
                    "metric_scale_calibrated": False,
                },
                "assets": [
                    {
                        "id": "single_photo_mesh",
                        "type": "ply_mesh",
                        "path": mesh_path.relative_to(scene).as_posix(),
                        "role": "primary_visual",
                        "mime_type": "application/octet-stream",
                        "required": True,
                        "visible_by_default": True,
                    },
                    {
                        "id": "single_photo_texture",
                        "type": "texture",
                        "path": texture_path.relative_to(scene).as_posix(),
                        "role": "texture",
                        "mime_type": "image/jpeg",
                        "required": False,
                        "visible_by_default": True,
                    },
                    {
                        "id": "single_photo_points",
                        "type": "ply",
                        "path": ply_path.relative_to(scene).as_posix(),
                        "role": "diagnostic",
                        "mime_type": "application/octet-stream",
                        "required": False,
                        "visible_by_default": False,
                    },
                    {
                        "id": "depth_grayscale",
                        "type": "image",
                        "path": grayscale_path.relative_to(scene).as_posix(),
                        "role": "diagnostic",
                        "mime_type": "image/png",
                        "required": False,
                        "visible_by_default": False,
                    },
                    {
                        "id": "depth_heatmap",
                        "type": "image",
                        "path": heatmap_path.relative_to(scene).as_posix(),
                        "role": "diagnostic",
                        "mime_type": "image/png",
                        "required": False,
                        "visible_by_default": False,
                    },
                    {
                        "id": "depth_discontinuity",
                        "type": "image",
                        "path": discontinuity_path.relative_to(scene).as_posix(),
                        "role": "diagnostic",
                        "mime_type": "image/png",
                        "required": False,
                        "visible_by_default": False,
                    },
                ],
                "camera_metadata": {"pose_asset_id": None, "pose_convention": "camera_to_world"},
                "navigation": {
                    "enabled": False,
                    "spawn_position": [0.0, 0.0, 0.0],
                    "spawn_yaw_degrees": 0.0,
                    "camera_height": 1.65,
                    "movement_speed": 1.0,
                    "collision_radius": 0.25,
                    "collider_asset_id": None,
                    "grid_asset_id": None,
                    "zones": [],
                },
                "poi_metadata": {"asset_id": None, "count": 0},
                "viewer": {
                    "background": "#06131d",
                    "ambient_light_intensity": 1.0,
                    "directional_light_intensity": 1.2,
                    "point_size": 0.012,
                    "is_2_5d": True,
                    "source_camera_position": [0.0, 0.0, 0.0],
                    "source_camera_look_at": [0.0, 0.0, round(-median_z, 4)],
                    "source_camera_fov": round(fov_y_deg, 2),
                },
            })
            scene_manifest_path = scene / "metadata" / "scene_manifest.json"
            scene_manifest_path.write_text(scene_manifest.model_dump_json(indent=2), encoding="utf-8")
            created_outputs.append(scene_manifest_path)
            quality_path = scene / "metadata" / "single_image_quality.json"
            possible_faces = max(1, 2 * (max(2, round(image.shape[1] * min(1.0, active_profile.geometry_max_dimension / max(image.shape[:2])))) - 1) * (max(2, round(image.shape[0] * min(1.0, active_profile.geometry_max_dimension / max(image.shape[:2])))) - 1))
            _write_json(quality_path, {
                "schema_version": "1.0.0",
                "model": process_manifest["model"],
                "depth_output": "relative_non_metric",
                "input_resolution": [image.shape[1], image.shape[0]],
                "camera_metadata": camera_metadata,
                "focal_length_pixels": focal_pixels or max(image.shape[:2]) * 0.9,
                "focal_length_source": focal_source,
                "depth_exaggeration": depth_exaggeration,
                "vertex_count": len(points),
                "triangle_count": len(faces),
                "rejected_discontinuity_triangles": rejected_faces,
                "triangle_retention_ratio": round(len(faces) / possible_faces, 6),
                "normalized_depth_percentiles": {
                    "p05": round(float(np.percentile(depth, 5)), 6),
                    "p50": round(float(np.percentile(depth, 50)), 6),
                    "p95": round(float(np.percentile(depth, 95)), 6),
                },
                "inference_seconds": round(inference_seconds, 6),
                "geometry_seconds": round(geometry_seconds, 6),
                "metric_scale": False,
                "navigation_enabled": False,
                "limitations": [
                    "Hidden surfaces are not reconstructed.",
                    "Depth ordering is model-estimated and has no absolute scale.",
                    "Edge-aware triangulation removes occluded foreground-background stretching.",
                ],
            })
            created_outputs.append(quality_path)
            process_manifest["artifacts"] = {
                "mesh": mesh_path.relative_to(scene).as_posix(),
                "point_cloud": ply_path.relative_to(scene).as_posix(),
                "texture": texture_path.relative_to(scene).as_posix(),
                "relative_depth_preview": depth_path.relative_to(scene).as_posix(),
                "depth_grayscale": grayscale_path.relative_to(scene).as_posix(),
                "depth_heatmap": heatmap_path.relative_to(scene).as_posix(),
                "depth_discontinuity": discontinuity_path.relative_to(scene).as_posix(),
                "depth_diagnostics": diagnostics_path.relative_to(scene).as_posix(),
                "scene_manifest": scene_manifest_path.relative_to(scene).as_posix(),
                "quality_report": quality_path.relative_to(scene).as_posix(),
            }
            process_manifest["processing_status"] = "completed"
            process_manifest["current_stage"] = "packaging"
        except Exception as exc:
            process_manifest["processing_status"] = "cancelled" if isinstance(exc, ProcessingCancelled) else "failed"
            process_manifest["error"] = str(exc)
            for output in created_outputs:
                output.unlink(missing_ok=True)
            process_manifest["partial_outputs_removed"] = len(created_outputs)
            raise
        finally:
            process_manifest["processing_duration_seconds"] = round(time.perf_counter() - started, 6)
            _write_json(process_manifest_path, process_manifest)
        return process_manifest
