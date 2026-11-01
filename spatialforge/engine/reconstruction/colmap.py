"""CPU-first COLMAP sparse reconstruction backend."""

from __future__ import annotations

import json
import shutil
from statistics import median
import time
from pathlib import Path
from typing import Any, Sequence

import yaml

from .base import (
    ReconstructionBackend,
    ReconstructionConfig,
    ReconstructionError,
    SceneInput,
    SceneValidationError,
)
from .exporter import write_camera_poses
from .metrics import compute_reconstruction_metrics
from .parser import ParsedModel, parse_text_model
from .quality_report import build_reconstruction_quality_report, write_reconstruction_quality_report
from .runner import ColmapRunner, resolve_colmap_executable


def load_reconstruction_config(path: str | Path) -> ReconstructionConfig:
    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Reconstruction configuration not found: {config_path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Reconstruction configuration must be a YAML mapping")
    unknown = set(raw) - set(ReconstructionConfig.__dataclass_fields__)
    if unknown:
        raise ValueError(f"Unknown reconstruction configuration values: {', '.join(sorted(unknown))}")
    config = ReconstructionConfig(**raw)
    config.validate()
    return config


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def validate_scene(scene_dir: str | Path, minimum_images: int = 3) -> SceneInput:
    scene = Path(scene_dir).expanduser().resolve()
    if not scene.is_dir():
        raise SceneValidationError(f"Scene directory does not exist: {scene}")
    manifest_path = scene / "metadata" / "capture_manifest.json"
    if not manifest_path.is_file():
        raise SceneValidationError(f"Capture manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SceneValidationError(f"Capture manifest is invalid: {manifest_path}") from exc
    if manifest.get("processing_status") != "completed":
        raise SceneValidationError("Capture must have processing_status='completed'")
    image_records = manifest.get("images")
    if not isinstance(image_records, list):
        raise SceneValidationError("Capture manifest field 'images' must be a list")

    images: list[Path] = []
    for record in image_records:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            raise SceneValidationError("Capture manifest contains an invalid image record")
        image_path = (scene / record["path"]).resolve()
        if not _inside(image_path, scene):
            raise SceneValidationError(f"Image path escapes the scene directory: {record['path']}")
        if not image_path.is_file() or image_path.stat().st_size == 0:
            raise SceneValidationError(f"Capture image is missing or empty: {record['path']}")
        images.append(image_path)

    if len(images) < minimum_images:
        raise SceneValidationError(
            f"At least {minimum_images} accepted images are required; found {len(images)}"
        )
    image_dir = scene / "images"
    if any(image.parent != image_dir.resolve() for image in images):
        raise SceneValidationError("All reconstruction images must be directly inside scene/images")
    return SceneInput(scene.name, scene, image_dir, tuple(images), manifest)


def _write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2), encoding="utf-8")
    temporary.replace(path)


def choose_primary_model(models: Sequence[tuple[Path, ParsedModel]]) -> tuple[Path, ParsedModel]:
    if not models:
        raise ReconstructionError("COLMAP mapper produced no sparse submodels")

    def _model_score(item: tuple[Path, ParsedModel]) -> tuple[int, int, float, str]:
        path, model = item
        registered_count = len(model.images)
        point_count = len(model.points)
        errors = [p.reprojection_error for p in model.points]
        neg_mean_error = -(sum(errors) / len(errors)) if errors else 0.0
        return (registered_count, point_count, neg_mean_error, path.name)

    return max(models, key=_model_score)


def choose_matching_strategy(config: ReconstructionConfig, scene_input: SceneInput) -> str:
    """Select a bounded matcher from capture ordering and dataset size."""
    if config.matcher != "auto":
        return config.matcher
    capture_mode = scene_input.capture_manifest.get("capture_mode", "video")
    if capture_mode == "video":
        return "sequential"
    if len(scene_input.images) <= config.max_exhaustive_images:
        return "exhaustive"
    if config.vocab_tree_path and Path(config.vocab_tree_path).expanduser().is_file():
        return "vocab_tree"
    raise ReconstructionError(
        f"Unordered photo set has {len(scene_input.images)} images, above the safe exhaustive "
        f"limit of {config.max_exhaustive_images}. Configure an existing vocab_tree_path; "
        "SpatialForge will not silently start an unbounded exhaustive match."
    )


def infer_camera_overrides(scene_input: SceneInput, camera_model: str) -> tuple[bool | None, str | None]:
    """Use consistent EXIF-derived focal estimates without inventing sensor calibration."""
    report_path = scene_input.scene_dir / "metadata" / "photo_quality_report.json"
    if not report_path.is_file():
        return None, None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        records = report.get("images", [])
        cameras = {
            (record.get("camera", {}).get("make"), record.get("camera", {}).get("model"))
            for record in records
            if record.get("camera", {}).get("make") or record.get("camera", {}).get("model")
        }
        estimates = [float(record["estimated_focal_pixels"]) for record in records if record.get("estimated_focal_pixels")]
        widths = [float(record["width"]) for record in records if record.get("estimated_focal_pixels")]
        heights = [float(record["height"]) for record in records if record.get("estimated_focal_pixels")]
    except (OSError, ValueError, TypeError, KeyError):
        return None, None
    single_camera = len(cameras) <= 1 if cameras else None
    if not estimates or len({round(width) for width in widths}) != 1 or len({round(height) for height in heights}) != 1:
        return single_camera, None
    focal = median(estimates)
    if max(abs(value - focal) for value in estimates) / focal > 0.08:
        return single_camera, None
    cx, cy = median(widths) / 2, median(heights) / 2
    if camera_model == "SIMPLE_PINHOLE":
        return single_camera, f"{focal:.6g},{cx:.6g},{cy:.6g}"
    if camera_model == "SIMPLE_RADIAL":
        return single_camera, f"{focal:.6g},{cx:.6g},{cy:.6g},0"
    return single_camera, None


def build_feature_arguments(
    config: ReconstructionConfig,
    database_path: Path,
    image_path: Path,
    *,
    cpu_option: str,
    single_camera: bool | None = None,
    camera_params: str | None = None,
    thread_option: str | None = None,
    max_image_size_option: str | None = None,
) -> list[str]:
    arguments = [
        "feature_extractor",
        "--database_path",
        str(database_path),
        "--image_path",
        str(image_path),
        "--ImageReader.camera_model",
        config.camera_model,
        "--ImageReader.single_camera",
        "1" if (config.single_camera if single_camera is None else single_camera) else "0",
        "--SiftExtraction.max_num_features",
        str(config.max_num_features),
    ]
    if thread_option:
        arguments.extend([thread_option, str(config.num_threads)])
    if max_image_size_option:
        arguments.extend([max_image_size_option, str(config.max_image_size)])
    arguments.extend([cpu_option, "0"])
    if camera_params:
        arguments.extend(["--ImageReader.camera_params", camera_params])
    return arguments


def build_matcher_arguments(
    config: ReconstructionConfig,
    database_path: Path,
    *,
    cpu_option: str,
    matcher: str | None = None,
    thread_option: str | None = None,
    sequential_thread_option: str | None = None,
) -> list[str]:
    selected = matcher or config.matcher
    if selected == "auto":
        raise ValueError("A concrete matcher must be selected before building arguments")
    command = f"{selected}_matcher"
    arguments = [command, "--database_path", str(database_path), cpu_option, "0"]
    if thread_option:
        arguments.extend([thread_option, str(config.num_threads)])
    if selected == "sequential":
        arguments.extend(["--SequentialMatching.overlap", str(config.sequential_overlap)])
        if sequential_thread_option:
            arguments.extend([sequential_thread_option, str(config.num_threads)])
    if selected == "vocab_tree":
        arguments.extend(["--VocabTreeMatching.vocab_tree_path", str(Path(config.vocab_tree_path or "").expanduser())])
    return arguments


class ColmapBackend(ReconstructionBackend):
    def __init__(self, config: ReconstructionConfig, runner: ColmapRunner | None = None) -> None:
        config.validate()
        self.config = config
        self._runner = runner

    @property
    def name(self) -> str:
        return "colmap"

    def reconstruct(self, scene_dir: str | Path) -> dict[str, Any]:
        started = time.perf_counter()
        scene = Path(scene_dir).expanduser().resolve()
        reconstruction_root = scene / "reconstruction" / "colmap"
        logs_dir = reconstruction_root / "logs"
        sparse_dir = reconstruction_root / "sparse"
        exports_dir = reconstruction_root / "exports"
        manifest_path = scene / "metadata" / "reconstruction_manifest.json"
        stage = "input_validation"
        stage_started = time.perf_counter()
        manifest: dict[str, Any] = {
            "scene_id": scene.name,
            "backend": self.name,
            "backend_version": None,
            "configuration": self.config.to_dict(),
            "processing_status": "running",
            "current_stage": stage,
            "failed_stage": None,
            "artifacts": {},
            "metrics": {},
            "warnings": [],
            "processing_duration_seconds": 0.0,
            "stage_timings": {},
        }
        should_write_manifest = True
        try:
            scene_input = validate_scene(scene, self.config.minimum_images)
            matching_strategy = choose_matching_strategy(self.config, scene_input)
            single_camera_override, camera_params = infer_camera_overrides(scene_input, self.config.camera_model)
            manifest["matching_strategy"] = matching_strategy
            manifest["camera_initialization"] = {
                "single_camera": self.config.single_camera if single_camera_override is None else single_camera_override,
                "exif_intrinsics_used": camera_params is not None,
            }
            if len(scene_input.images) < 15:
                manifest["warnings"].append(
                    "The dataset meets the minimum image count, but substantially more overlapping "
                    "images are normally needed for a robust indoor reconstruction."
                )
            if manifest_path.is_file():
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
                if existing.get("processing_status") == "completed":
                    should_write_manifest = False
                    raise ReconstructionError(
                        "A successful reconstruction already exists; refusing to overwrite it"
                    )

            logs_dir.mkdir(parents=True, exist_ok=True)
            sparse_dir.mkdir(parents=True, exist_ok=True)
            exports_dir.mkdir(parents=True, exist_ok=True)
            manifest["stage_timings"]["input_validation"] = round(time.perf_counter() - stage_started, 3)
            _write_json_atomic(manifest_path, manifest)

            stage = "environment"
            stage_started = time.perf_counter()
            manifest["current_stage"] = stage
            runner = self._runner or ColmapRunner(
                resolve_colmap_executable(self.config.colmap_path),
                self.config.timeout_seconds,
            )
            manifest["backend_version"] = runner.version(logs_dir)
            manifest["stage_timings"]["environment"] = round(time.perf_counter() - stage_started, 3)
            _write_json_atomic(manifest_path, manifest)

            database_path = reconstruction_root / "database.db"
            if database_path.is_file():
                database_path.unlink(missing_ok=True)
            for db_extra in (reconstruction_root / "database.db-wal", reconstruction_root / "database.db-shm"):
                if db_extra.is_file():
                    db_extra.unlink(missing_ok=True)

            stage = "feature_extraction"
            stage_started = time.perf_counter()
            manifest["current_stage"] = stage
            _write_json_atomic(manifest_path, manifest)
            feature_cpu_option = runner.select_option(
                "feature_extractor",
                ["--FeatureExtraction.use_gpu", "--SiftExtraction.use_gpu"],
                logs_dir,
            )
            for required_option in (
                "--database_path",
                "--image_path",
                "--ImageReader.camera_model",
                "--ImageReader.single_camera",
                "--SiftExtraction.max_num_features",
            ):
                runner.select_option("feature_extractor", [required_option], logs_dir)
            feature_thread_option = runner.find_option(
                "feature_extractor",
                ["--FeatureExtraction.num_threads", "--SiftExtraction.num_threads"],
                logs_dir,
            )
            max_image_size_option = runner.find_option(
                "feature_extractor",
                ["--FeatureExtraction.max_image_size", "--SiftExtraction.max_image_size"],
                logs_dir,
            )
            runner.run(
                build_feature_arguments(
                    self.config,
                    database_path,
                    scene_input.image_dir,
                    cpu_option=feature_cpu_option,
                    single_camera=single_camera_override,
                    camera_params=camera_params,
                    thread_option=feature_thread_option,
                    max_image_size_option=max_image_size_option,
                ),
                stage=stage,
                log_path=logs_dir / f"{stage}.log",
            )
            manifest["stage_timings"]["feature_extraction"] = round(time.perf_counter() - stage_started, 3)
            _write_json_atomic(manifest_path, manifest)

            stage = "feature_matching"
            stage_started = time.perf_counter()
            manifest["current_stage"] = stage
            _write_json_atomic(manifest_path, manifest)
            matcher_command = f"{matching_strategy}_matcher"
            matching_cpu_option = runner.select_option(
                matcher_command,
                ["--FeatureMatching.use_gpu", "--SiftMatching.use_gpu"],
                logs_dir,
            )
            runner.select_option(matcher_command, ["--database_path"], logs_dir)
            if matching_strategy == "sequential":
                runner.select_option(matcher_command, ["--SequentialMatching.overlap"], logs_dir)
            if matching_strategy == "vocab_tree":
                runner.select_option(matcher_command, ["--VocabTreeMatching.vocab_tree_path"], logs_dir)

            matching_thread_option = runner.find_option(
                matcher_command,
                ["--FeatureMatching.num_threads", "--SiftMatching.num_threads"],
                logs_dir,
            )
            seq_thread_option = (
                runner.find_option(matcher_command, ["--SequentialMatching.num_threads"], logs_dir)
                if matching_strategy == "sequential"
                else None
            )
            runner.run(
                build_matcher_arguments(
                    self.config,
                    database_path,
                    cpu_option=matching_cpu_option,
                    matcher=matching_strategy,
                    thread_option=matching_thread_option,
                    sequential_thread_option=seq_thread_option,
                ),
                stage=stage,
                log_path=logs_dir / f"{stage}.log",
            )
            manifest["stage_timings"]["feature_matching"] = round(time.perf_counter() - stage_started, 3)
            _write_json_atomic(manifest_path, manifest)

            stage = "sparse_mapping"
            stage_started = time.perf_counter()
            manifest["current_stage"] = stage
            _write_json_atomic(manifest_path, manifest)
            for required_option in ("--database_path", "--image_path", "--output_path"):
                runner.select_option("mapper", [required_option], logs_dir)

            # Clear out any stale submodels from previous runs
            for item in sparse_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                elif item.is_file():
                    item.unlink(missing_ok=True)

            mapper_arguments = [
                "mapper",
                "--database_path",
                str(database_path),
                "--image_path",
                str(scene_input.image_dir),
                "--output_path",
                str(sparse_dir),
            ]
            mapper_thread_option = runner.find_option("mapper", ["--Mapper.num_threads"], logs_dir)
            if mapper_thread_option:
                mapper_arguments.extend([mapper_thread_option, str(self.config.num_threads)])

            init_tri_option = runner.find_option("mapper", ["--Mapper.init_min_tri_angle"], logs_dir)
            if init_tri_option:
                mapper_arguments.extend([init_tri_option, str(self.config.init_min_tri_angle)])

            abs_pose_option = runner.find_option("mapper", ["--Mapper.abs_pose_min_num_inliers"], logs_dir)
            if abs_pose_option:
                mapper_arguments.extend([abs_pose_option, str(self.config.abs_pose_min_num_inliers)])

            runner.run(
                mapper_arguments,
                stage=stage,
                log_path=logs_dir / f"{stage}.log",
            )
            manifest["stage_timings"]["sparse_mapping"] = round(time.perf_counter() - stage_started, 3)
            _write_json_atomic(manifest_path, manifest)

            stage = "model_analysis"
            stage_started = time.perf_counter()
            manifest["current_stage"] = stage
            _write_json_atomic(manifest_path, manifest)
            submodels = sorted(path for path in sparse_dir.iterdir() if path.is_dir())
            parsed_models: list[tuple[Path, ParsedModel]] = []
            text_models_root = exports_dir / "text_models"
            for required_option in ("--input_path", "--output_path", "--output_type"):
                runner.select_option("model_converter", [required_option], logs_dir)
            for model_dir in submodels:
                text_dir = text_models_root / model_dir.name
                text_dir.mkdir(parents=True, exist_ok=True)
                runner.run(
                    [
                        "model_converter",
                        "--input_path",
                        str(model_dir),
                        "--output_path",
                        str(text_dir),
                        "--output_type",
                        "TXT",
                    ],
                    stage=f"convert_model_{model_dir.name}_to_text",
                    log_path=logs_dir / f"convert_model_{model_dir.name}_to_text.log",
                )
                parsed_models.append((model_dir, parse_text_model(text_dir)))
            primary_dir, primary_model = choose_primary_model(parsed_models)
            manifest["stage_timings"]["model_analysis"] = round(time.perf_counter() - stage_started, 3)
            _write_json_atomic(manifest_path, manifest)

            stage = "model_export"
            stage_started = time.perf_counter()
            manifest["current_stage"] = stage
            _write_json_atomic(manifest_path, manifest)
            ply_path = exports_dir / "sparse.ply"
            runner.run(
                [
                    "model_converter",
                    "--input_path",
                    str(primary_dir),
                    "--output_path",
                    str(ply_path),
                    "--output_type",
                    "PLY",
                ],
                stage="export_ply",
                log_path=logs_dir / "export_ply.log",
            )
            if not ply_path.is_file() or ply_path.stat().st_size == 0:
                raise ReconstructionError(f"Exported point cloud PLY is missing or empty at {ply_path}")
            poses_path = write_camera_poses(primary_model, exports_dir / "camera_poses.json")
            metrics = compute_reconstruction_metrics(
                primary_model,
                total_input_images=len(scene_input.images),
                submodel_count=len(parsed_models),
            )
            quality_path = write_reconstruction_quality_report(
                build_reconstruction_quality_report(
                    primary_model,
                    input_image_names=[path.name for path in scene_input.images],
                    metrics=metrics,
                ),
                scene / "metadata" / "reconstruction_quality.json",
            )
            manifest["profile"] = self.config.profile
            manifest["capabilities"] = {
                "profile": self.config.profile,
                "sparse_sfm": True,
                "dense_stereo": False,
                "cuda_enabled": False,
                "num_threads": self.config.num_threads,
                "max_image_size": self.config.max_image_size,
            }
            manifest["artifacts"] = {
                "database": database_path.relative_to(scene).as_posix(),
                "sparse_models": sparse_dir.relative_to(scene).as_posix(),
                "primary_model": primary_dir.relative_to(scene).as_posix(),
                "point_cloud_ply": ply_path.relative_to(scene).as_posix(),
                "camera_poses": poses_path.relative_to(scene).as_posix(),
                "logs": logs_dir.relative_to(scene).as_posix(),
                "quality_report": quality_path.relative_to(scene).as_posix(),
            }
            manifest["metrics"] = metrics
            manifest["stage_timings"]["model_export"] = round(time.perf_counter() - stage_started, 3)
            manifest["processing_status"] = "completed"
            manifest["current_stage"] = "completed"
        except Exception as exc:
            manifest["processing_status"] = "failed"
            manifest["failed_stage"] = stage
            manifest["current_stage"] = stage
            manifest["error"] = str(exc)
            raise
        finally:
            manifest["processing_duration_seconds"] = round(time.perf_counter() - started, 6)
            if should_write_manifest and scene.is_dir() and (scene / "metadata").is_dir():
                _write_json_atomic(manifest_path, manifest)
        return manifest
