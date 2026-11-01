import json
from pathlib import Path

import pytest

from spatialforge.engine.reconstruction.dense import DenseReconstructionConfig, run_dense_reconstruction


class DenseRunner:
    def __init__(self) -> None:
        self.calls = []

    def version(self, logs: Path) -> str:
        return "COLMAP test"

    def run(self, arguments, *, stage, log_path, timeout_seconds=None):
        arguments = list(arguments)
        self.calls.append((stage, arguments))
        if arguments[0] == "image_undistorter":
            Path(arguments[arguments.index("--output_path") + 1]).mkdir(parents=True)
        elif arguments[0] == "stereo_fusion":
            Path(arguments[arguments.index("--output_path") + 1]).write_bytes(b"dense-ply")
        elif arguments[0] in {"poisson_mesher", "delaunay_mesher"}:
            Path(arguments[arguments.index("--output_path") + 1]).write_bytes(b"mesh-ply")


def _sparse_scene(root: Path) -> Path:
    scene = root / "scene_dense_test"
    (scene / "metadata").mkdir(parents=True)
    (scene / "images").mkdir()
    primary = scene / "reconstruction" / "colmap" / "sparse" / "0"
    primary.mkdir(parents=True)
    (scene / "metadata" / "reconstruction_manifest.json").write_text(json.dumps({
        "processing_status": "completed", "artifacts": {"primary_model": "reconstruction/colmap/sparse/0"}
    }), encoding="utf-8")
    return scene


def test_dense_pipeline_runs_colmap_stages_and_persists_artifacts(tmp_path: Path) -> None:
    scene = _sparse_scene(tmp_path)
    runner = DenseRunner()
    result = run_dense_reconstruction(scene, DenseReconstructionConfig(quality="low"), runner=runner)
    assert result["processing_status"] == "completed"
    assert [stage for stage, _ in runner.calls] == ["image_undistortion", "dense_stereo", "depth_fusion", "mesh_generation"]
    assert (scene / result["artifacts"]["dense_point_cloud"]).is_file()


def test_dense_pipeline_requires_completed_sparse_result(tmp_path: Path) -> None:
    scene = _sparse_scene(tmp_path)
    path = scene / "metadata" / "reconstruction_manifest.json"
    path.write_text(json.dumps({"processing_status": "failed"}), encoding="utf-8")
    with pytest.raises(Exception, match="must be completed"):
        run_dense_reconstruction(scene, DenseReconstructionConfig(), runner=DenseRunner())
