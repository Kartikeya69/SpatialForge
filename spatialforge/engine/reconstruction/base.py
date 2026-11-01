"""Backend contracts and shared reconstruction configuration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal


class ReconstructionError(RuntimeError):
    """Raised when reconstruction cannot safely complete."""


class SceneValidationError(ReconstructionError):
    """Raised when a capture scene is not valid reconstruction input."""


@dataclass(frozen=True)
class ReconstructionConfig:
    backend: str = "colmap"
    colmap_path: str | None = None
    profile: Literal["cpu_sparse", "external_gpu_dense", "cpu_fast", "cpu_balanced", "cpu_quality"] = "cpu_sparse"
    matcher: Literal["auto", "sequential", "exhaustive", "vocab_tree"] = "auto"
    vocab_tree_path: str | None = None
    max_exhaustive_images: int = 80
    camera_model: str = "SIMPLE_RADIAL"
    single_camera: bool = True
    max_num_features: int = 8192
    max_image_size: int = 2000
    num_threads: int = 4
    init_min_tri_angle: float = 8.0
    abs_pose_min_num_inliers: int = 20
    sequential_overlap: int = 10
    timeout_seconds: int = 3600
    minimum_images: int = 3

    def validate(self) -> None:
        if self.backend != "colmap":
            raise ValueError("Only the 'colmap' reconstruction backend is currently supported")
        if self.profile not in {"cpu_sparse", "external_gpu_dense", "cpu_fast", "cpu_balanced", "cpu_quality"}:
            raise ValueError("profile must be 'cpu_sparse', 'external_gpu_dense', 'cpu_fast', 'cpu_balanced', or 'cpu_quality'")
        if self.matcher not in {"auto", "sequential", "exhaustive", "vocab_tree"}:
            raise ValueError("matcher must be 'auto', 'sequential', 'exhaustive', or 'vocab_tree'")
        if self.matcher == "vocab_tree" and not self.vocab_tree_path:
            raise ValueError("vocab_tree matching requires vocab_tree_path")
        if self.max_exhaustive_images < 3:
            raise ValueError("max_exhaustive_images cannot be less than 3")
        if not self.camera_model or not self.camera_model.replace("_", "").isalnum():
            raise ValueError("camera_model must be a COLMAP camera model name")
        if self.max_num_features <= 0:
            raise ValueError("max_num_features must be greater than zero")
        if self.max_image_size <= 0:
            raise ValueError("max_image_size must be greater than zero")
        if self.num_threads <= 0:
            raise ValueError("num_threads must be greater than zero")
        if self.init_min_tri_angle <= 0.0:
            raise ValueError("init_min_tri_angle must be greater than zero")
        if self.abs_pose_min_num_inliers <= 0:
            raise ValueError("abs_pose_min_num_inliers must be greater than zero")
        if self.sequential_overlap <= 0:
            raise ValueError("sequential_overlap must be greater than zero")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if self.minimum_images < 3:
            raise ValueError("minimum_images cannot be less than 3")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_reconstruction_profile(base_config: ReconstructionConfig, profile_name: str | None = None) -> ReconstructionConfig:
    """Derives CPU-first reconstruction parameters tailored for Intel Iris/UHD integrated GPUs."""
    clean = (profile_name or base_config.profile).strip().lower()
    if clean in {"fast", "cpu_fast"}:
        return ReconstructionConfig(
            backend=base_config.backend,
            colmap_path=base_config.colmap_path,
            profile="cpu_fast",
            matcher="sequential",
            vocab_tree_path=base_config.vocab_tree_path,
            max_exhaustive_images=base_config.max_exhaustive_images,
            camera_model=base_config.camera_model,
            single_camera=base_config.single_camera,
            max_num_features=4096,
            max_image_size=1280,
            num_threads=min(4, base_config.num_threads),
            init_min_tri_angle=base_config.init_min_tri_angle,
            abs_pose_min_num_inliers=base_config.abs_pose_min_num_inliers,
            sequential_overlap=8,
            timeout_seconds=base_config.timeout_seconds,
            minimum_images=base_config.minimum_images,
        )
    if clean in {"quality", "cpu_quality", "high"}:
        return ReconstructionConfig(
            backend=base_config.backend,
            colmap_path=base_config.colmap_path,
            profile="cpu_quality",
            matcher=base_config.matcher,
            vocab_tree_path=base_config.vocab_tree_path,
            max_exhaustive_images=base_config.max_exhaustive_images,
            camera_model=base_config.camera_model,
            single_camera=base_config.single_camera,
            max_num_features=12288,
            max_image_size=2000,
            num_threads=min(4, base_config.num_threads),
            init_min_tri_angle=base_config.init_min_tri_angle,
            abs_pose_min_num_inliers=base_config.abs_pose_min_num_inliers,
            sequential_overlap=14,
            timeout_seconds=base_config.timeout_seconds,
            minimum_images=base_config.minimum_images,
        )
    # Balanced (default)
    return ReconstructionConfig(
        backend=base_config.backend,
        colmap_path=base_config.colmap_path,
        profile="cpu_sparse",
        matcher=base_config.matcher,
        vocab_tree_path=base_config.vocab_tree_path,
        max_exhaustive_images=base_config.max_exhaustive_images,
        camera_model=base_config.camera_model,
        single_camera=base_config.single_camera,
        max_num_features=8192,
        max_image_size=1600,
        num_threads=min(4, base_config.num_threads),
        init_min_tri_angle=base_config.init_min_tri_angle,
        abs_pose_min_num_inliers=base_config.abs_pose_min_num_inliers,
        sequential_overlap=10,
        timeout_seconds=base_config.timeout_seconds,
        minimum_images=base_config.minimum_images,
    )


@dataclass(frozen=True)
class SceneInput:
    scene_id: str
    scene_dir: Path
    image_dir: Path
    images: tuple[Path, ...]
    capture_manifest: dict[str, Any]


class ReconstructionBackend(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def reconstruct(self, scene_dir: str | Path) -> dict[str, Any]:
        raise NotImplementedError
