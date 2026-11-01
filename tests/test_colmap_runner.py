from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from spatialforge.engine.reconstruction.runner import (
    ColmapNotFoundError,
    ColmapProcessError,
    ColmapRunner,
    ColmapTimeoutError,
    resolve_colmap_executable,
)
from spatialforge.engine.reconstruction.base import ReconstructionError


def test_missing_colmap_executable(tmp_path: Path) -> None:
    with pytest.raises(ColmapNotFoundError, match="not found"):
        resolve_colmap_executable(str(tmp_path / "colmap.exe"))


class ProcessStub:
    def __init__(self, returncode: int = 0, output: str = "ok", timeout: bool = False) -> None:
        self.returncode = returncode
        self.output = output
        self.timeout = timeout
        self.pid = 123
        self.calls = 0

    def communicate(self, timeout=None):
        self.calls += 1
        if self.timeout and self.calls == 1:
            raise subprocess.TimeoutExpired("colmap", timeout)
        return self.output, None

    def poll(self):
        return None if self.timeout and self.calls == 1 else self.returncode


def make_runner(tmp_path: Path) -> ColmapRunner:
    executable = tmp_path / "colmap.exe"
    executable.write_bytes(b"fake")
    return ColmapRunner(executable, timeout_seconds=1)


def test_process_failure_writes_log(tmp_path: Path, monkeypatch) -> None:
    runner = make_runner(tmp_path)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: ProcessStub(2, "bad flags"))
    log = tmp_path / "failed.log"
    with pytest.raises(ColmapProcessError, match="exit code 2"):
        runner.run(["feature_extractor"], stage="features", log_path=log)
    assert "bad flags" in log.read_text(encoding="utf-8")


def test_timeout_terminates_and_records_failure(tmp_path: Path, monkeypatch) -> None:
    runner = make_runner(tmp_path)
    process = ProcessStub(timeout=True)
    terminated: list[bool] = []
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(runner, "_terminate_process_tree", lambda process: terminated.append(True))
    log = tmp_path / "timeout.log"
    with pytest.raises(ColmapTimeoutError, match="exceeded"):
        runner.run(["mapper"], stage="mapping", log_path=log)
    assert terminated == [True]
    assert '"timed_out": true' in log.read_text(encoding="utf-8")


def test_runtime_option_detection(tmp_path: Path, monkeypatch) -> None:
    runner = make_runner(tmp_path)
    monkeypatch.setattr(
        runner,
        "help_text",
        lambda command, log_dir: "--FeatureExtraction.use_gpu arg (=1)",
    )
    selected = runner.select_option(
        "feature_extractor",
        ["--FeatureExtraction.use_gpu", "--SiftExtraction.use_gpu"],
        tmp_path,
    )
    assert selected == "--FeatureExtraction.use_gpu"

    with pytest.raises(ReconstructionError, match="does not advertise"):
        runner.select_option("feature_extractor", ["--Unsupported.option"], tmp_path)

    found = runner.find_option(
        "feature_extractor",
        ["--FeatureExtraction.use_gpu"],
        tmp_path,
    )
    assert found == "--FeatureExtraction.use_gpu"

    missing = runner.find_option(
        "feature_extractor",
        ["--Nonexistent.option"],
        tmp_path,
    )
    assert missing is None
