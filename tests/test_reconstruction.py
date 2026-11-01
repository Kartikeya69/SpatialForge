from __future__ import annotations

import json
from pathlib import Path

import pytest

from spatialforge.engine.reconstruction.base import ReconstructionConfig, SceneValidationError
from spatialforge.engine.reconstruction.colmap import (
    ColmapBackend,
    build_feature_arguments,
    build_matcher_arguments,
    choose_primary_model,
    validate_scene,
)
from spatialforge.engine.reconstruction.parser import ParsedModel, RegisteredImage


def make_scene(root: Path, image_count: int = 4, *, status: str = "completed") -> Path:
    scene = root / "scene_test"
    (scene / "images").mkdir(parents=True)
    (scene / "metadata").mkdir()
    images = []
    for index in range(image_count):
        path = scene / "images" / f"frame_{index + 1:06d}.jpg"
        path.write_bytes(b"jpeg-data")
        images.append({"path": f"images/{path.name}"})
    (scene / "metadata" / "capture_manifest.json").write_text(
        json.dumps({"processing_status": status, "accepted_frames": image_count, "images": images}),
        encoding="utf-8",
    )
    return scene


def test_missing_scene_directory(tmp_path: Path) -> None:
    with pytest.raises(SceneValidationError, match="does not exist"):
        validate_scene(tmp_path / "missing")


def test_invalid_capture_manifest(tmp_path: Path) -> None:
    scene = tmp_path / "scene_bad"
    (scene / "metadata").mkdir(parents=True)
    (scene / "metadata" / "capture_manifest.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(SceneValidationError, match="invalid"):
        validate_scene(scene)


def test_incomplete_capture_is_rejected(tmp_path: Path) -> None:
    scene = make_scene(tmp_path, status="failed")
    with pytest.raises(SceneValidationError, match="completed"):
        validate_scene(scene)


def test_missing_image_and_path_traversal_are_rejected(tmp_path: Path) -> None:
    scene = make_scene(tmp_path)
    manifest_path = scene / "metadata" / "capture_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["images"][0]["path"] = "images/missing.jpg"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SceneValidationError, match="missing or empty"):
        validate_scene(scene)

    manifest["images"][0]["path"] = "../outside.jpg"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SceneValidationError, match="escapes"):
        validate_scene(scene)


def test_insufficient_images(tmp_path: Path) -> None:
    scene = make_scene(tmp_path, image_count=2)
    with pytest.raises(SceneValidationError, match="At least 3"):
        validate_scene(scene)


def test_cpu_feature_and_matcher_commands() -> None:
    config = ReconstructionConfig(matcher="sequential", sequential_overlap=7)
    feature = build_feature_arguments(
        config, Path("database.db"), Path("images"), cpu_option="--FeatureExtraction.use_gpu"
    )
    assert feature[0] == "feature_extractor"
    assert feature[-2:] == ["--FeatureExtraction.use_gpu", "0"]
    assert "--SiftExtraction.max_num_features" in feature

    sequential = build_matcher_arguments(
        config, Path("database.db"), cpu_option="--FeatureMatching.use_gpu"
    )
    assert sequential[0] == "sequential_matcher"
    assert sequential[-2:] == ["--SequentialMatching.overlap", "7"]
    assert ["--FeatureMatching.use_gpu", "0"] == sequential[3:5]

    exhaustive = build_matcher_arguments(
        ReconstructionConfig(matcher="exhaustive"),
        Path("database.db"),
        cpu_option="--SiftMatching.use_gpu",
    )
    assert exhaustive[0] == "exhaustive_matcher"
    assert "--SequentialMatching.overlap" not in exhaustive


def test_primary_model_uses_most_registered_images() -> None:
    image = RegisteredImage(1, (1, 0, 0, 0), (0, 0, 0), 1, "a.jpg")
    small = ParsedModel((), (image,), ())
    large = ParsedModel((), (image, image, image), ())
    selected, _ = choose_primary_model([(Path("0"), small), (Path("1"), large)])
    assert selected == Path("1")


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str]] = []

    def version(self, log_dir: Path) -> str:
        return "COLMAP 4.test"

    def find_option(self, command: str, candidates: list[str], log_dir: Path) -> str | None:
        return candidates[0]

    def select_option(self, command: str, candidates: list[str], log_dir: Path) -> str:
        return candidates[0]

    def run(self, arguments, *, stage: str, log_path: Path, timeout_seconds=None):
        args = list(arguments)
        self.calls.append((args, stage))
        if args[0] == "feature_extractor":
            Path(args[args.index("--database_path") + 1]).write_bytes(b"sqlite")
        elif args[0] == "mapper":
            sparse = Path(args[args.index("--output_path") + 1])
            (sparse / "0").mkdir(parents=True)
            (sparse / "1").mkdir()
        elif args[0] == "model_converter":
            output = Path(args[args.index("--output_path") + 1])
            output_type = args[args.index("--output_type") + 1]
            if output_type == "TXT":
                output.mkdir(parents=True, exist_ok=True)
                count = 3 if output.name == "0" else 4
                (output / "cameras.txt").write_text("1 SIMPLE_RADIAL 640 480 500 320 240 0.1\n")
                image_lines = []
                for index in range(count):
                    image_lines.extend([f"{index + 1} 1 0 0 0 {index} 0 0 1 frame_{index}.jpg", ""])
                (output / "images.txt").write_text("\n".join(image_lines) + "\n")
                (output / "points3D.txt").write_text(
                    "1 0 0 1 255 0 0 0.5 1 0\n2 1 0 1 0 255 0 1.5 1 1\n"
                )
            else:
                output.write_text("ply\n", encoding="utf-8")


def test_mocked_pipeline_generates_manifest_and_selects_primary(tmp_path: Path) -> None:
    scene = make_scene(tmp_path, image_count=4)
    runner = FakeRunner()
    manifest = ColmapBackend(ReconstructionConfig(), runner=runner).reconstruct(scene)
    persisted = json.loads(
        (scene / "metadata" / "reconstruction_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["processing_status"] == "completed"
    assert persisted["metrics"]["registered_images"] == 4
    assert persisted["metrics"]["sparse_point_count"] == 2
    assert persisted["metrics"]["reconstructed_submodels"] == 2
    assert persisted["artifacts"]["primary_model"].endswith("sparse/1")
    assert (scene / persisted["artifacts"]["point_cloud_ply"]).is_file()
    assert (scene / persisted["artifacts"]["camera_poses"]).is_file()
    feature_call = next(call for call, stage in runner.calls if stage == "feature_extraction")
    assert feature_call[-2:] == ["--FeatureExtraction.use_gpu", "0"]


def test_completed_reconstruction_is_not_overwritten(tmp_path: Path) -> None:
    scene = make_scene(tmp_path)
    manifest_path = scene / "metadata" / "reconstruction_manifest.json"
    manifest_path.write_text(json.dumps({"processing_status": "completed"}), encoding="utf-8")
    with pytest.raises(Exception, match="refusing to overwrite"):
        ColmapBackend(ReconstructionConfig(), runner=FakeRunner()).reconstruct(scene)
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["processing_status"] == "completed"


def test_reconstruction_config_profiles_and_limits() -> None:
    config = ReconstructionConfig(profile="cpu_sparse", num_threads=4, max_image_size=1920)
    config.validate()
    assert config.profile == "cpu_sparse"

    config_gpu = ReconstructionConfig(profile="external_gpu_dense")
    config_gpu.validate()
    assert config_gpu.profile == "external_gpu_dense"

    with pytest.raises(ValueError, match="profile must be"):
        ReconstructionConfig(profile="invalid_profile").validate()  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="num_threads"):
        ReconstructionConfig(num_threads=0).validate()

    with pytest.raises(ValueError, match="max_image_size"):
        ReconstructionConfig(max_image_size=-1).validate()


def test_feature_and_matcher_memory_bounded_arguments() -> None:
    config = ReconstructionConfig(
        matcher="sequential",
        num_threads=4,
        max_image_size=2000,
        init_min_tri_angle=8.0,
        abs_pose_min_num_inliers=20,
    )
    feature = build_feature_arguments(
        config,
        Path("database.db"),
        Path("images"),
        cpu_option="--FeatureExtraction.use_gpu",
        thread_option="--FeatureExtraction.num_threads",
        max_image_size_option="--FeatureExtraction.max_image_size",
    )
    assert "--FeatureExtraction.num_threads" in feature
    idx_threads = feature.index("--FeatureExtraction.num_threads")
    assert feature[idx_threads + 1] == "4"
    assert "--FeatureExtraction.max_image_size" in feature
    idx_size = feature.index("--FeatureExtraction.max_image_size")
    assert feature[idx_size + 1] == "2000"

    matcher = build_matcher_arguments(
        config,
        Path("database.db"),
        cpu_option="--FeatureMatching.use_gpu",
        thread_option="--FeatureMatching.num_threads",
        sequential_thread_option="--SequentialMatching.num_threads",
    )
    assert "--FeatureMatching.num_threads" in matcher
    assert "--SequentialMatching.num_threads" in matcher


def test_model_score_reprojection_tiebreaker() -> None:
    image = RegisteredImage(1, (1, 0, 0, 0), (0, 0, 0), 1, "a.jpg")
    from spatialforge.engine.reconstruction.parser import Point3D
    p_good = Point3D(1, (0, 0, 0), (0, 0, 0), 0.5)
    p_poor = Point3D(1, (0, 0, 0), (0, 0, 0), 2.5)

    model_good = ParsedModel((), (image,), (p_good,))
    model_poor = ParsedModel((), (image,), (p_poor,))

    selected, _ = choose_primary_model([(Path("0"), model_poor), (Path("1"), model_good)])
    assert selected == Path("1")

