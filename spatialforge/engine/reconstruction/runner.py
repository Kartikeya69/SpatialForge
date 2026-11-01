"""Safe, logged COLMAP subprocess execution."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from .base import ReconstructionError


class ColmapNotFoundError(ReconstructionError):
    """Raised when the COLMAP CLI is unavailable."""


class ColmapProcessError(ReconstructionError):
    """Raised when a COLMAP command returns a failure."""


class ColmapTimeoutError(ReconstructionError):
    """Raised when a COLMAP stage exceeds its configured timeout."""


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    output: str
    duration_seconds: float


def _normalize_executable(candidate: Path) -> Path:
    resolved = candidate.resolve()
    if resolved.suffix.lower() in {".bat", ".cmd"}:
        direct_exe = resolved.parent / "bin" / "colmap.exe"
        if direct_exe.is_file():
            return direct_exe.resolve()
    return resolved


def resolve_colmap_executable(explicit_path: str | None = None) -> Path:
    if explicit_path:
        candidate = Path(explicit_path).expanduser().resolve()
        if not candidate.is_file():
            raise ColmapNotFoundError(f"COLMAP executable not found: {candidate}")
        return _normalize_executable(candidate)

    env_path = os.getenv("SPATIALFORGE_COLMAP_PATH")
    if env_path:
        candidate = Path(env_path).expanduser().resolve()
        if candidate.is_file():
            return _normalize_executable(candidate)

    discovered = shutil.which("colmap") or shutil.which("colmap.exe") or shutil.which("COLMAP.bat")
    if discovered:
        return _normalize_executable(Path(discovered))

    local_candidates = [
        Path.home() / "Downloads" / "colmap-x64-windows-nocuda" / "bin" / "colmap.exe",
        Path.home() / "Downloads" / "colmap-x64-windows-nocuda" / "COLMAP.bat",
    ]
    for local_candidate in local_candidates:
        if local_candidate.is_file():
            return _normalize_executable(local_candidate)

    raise ColmapNotFoundError(
        "COLMAP was not found on PATH. Install the Windows binary and pass "
        "--colmap-path if it is not on PATH."
    )


class ColmapRunner:
    def __init__(self, executable: str | Path, timeout_seconds: int = 3600) -> None:
        self.executable = Path(executable).resolve()
        if not self.executable.is_file():
            raise ColmapNotFoundError(f"COLMAP executable not found: {self.executable}")
        self.timeout_seconds = timeout_seconds
        self._help_cache: dict[str, str] = {}

    def _base_command(self) -> list[str]:
        if os.name == "nt" and self.executable.suffix.lower() in {".bat", ".cmd"}:
            direct_exe = self.executable.parent / "bin" / "colmap.exe"
            if direct_exe.is_file():
                self.executable = direct_exe
                return [str(direct_exe)]
            command_shell = shutil.which("cmd.exe")
            if not command_shell:
                raise ColmapNotFoundError("cmd.exe is required to run the COLMAP batch wrapper")
            return [command_shell, "/d", "/s", "/c", str(self.executable)]
        return [str(self.executable)]

    def command(self, *arguments: str) -> list[str]:
        return [*self._base_command(), *arguments]

    def run(
        self,
        arguments: Sequence[str],
        *,
        stage: str,
        log_path: Path,
        timeout_seconds: int | None = None,
    ) -> CommandResult:
        import time

        command = self.command(*arguments)
        timeout = timeout_seconds or self.timeout_seconds
        log_path.parent.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        start_new_session = os.name != "nt"

        env = dict(os.environ)
        bin_dir = str(self.executable.parent)
        if bin_dir not in env.get("PATH", ""):
            env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        plugins_dir = self.executable.parent.parent / "plugins"
        if plugins_dir.is_dir() and "QT_PLUGIN_PATH" not in env:
            env["QT_PLUGIN_PATH"] = str(plugins_dir)

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            env=env,
            creationflags=creationflags,
            start_new_session=start_new_session,
        )
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            self._terminate_process_tree(process)
            output, _ = process.communicate()
            duration = time.perf_counter() - started
            self._write_log(log_path, stage, command, -1, duration, output, timed_out=True)
            raise ColmapTimeoutError(f"COLMAP stage '{stage}' exceeded {timeout} seconds") from exc

        duration = time.perf_counter() - started
        self._write_log(log_path, stage, command, process.returncode, duration, output)
        if process.returncode != 0:
            raise ColmapProcessError(
                f"COLMAP stage '{stage}' failed with exit code {process.returncode}. "
                f"See {log_path}"
            )
        return CommandResult(tuple(command), process.returncode, output, duration)

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                check=False,
            )
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    @staticmethod
    def _write_log(
        path: Path,
        stage: str,
        command: Sequence[str],
        returncode: int,
        duration: float,
        output: str,
        *,
        timed_out: bool = False,
    ) -> None:
        header = {
            "timestamp": datetime.now(UTC).isoformat(),
            "stage": stage,
            "command": list(command),
            "returncode": returncode,
            "duration_seconds": round(duration, 6),
            "timed_out": timed_out,
        }
        path.write_text(json.dumps(header) + "\n" + output, encoding="utf-8")

    def version(self, log_dir: Path) -> str:
        result = self.run(["-h"], stage="version", log_path=log_dir / "version.log", timeout_seconds=30)
        for line in result.output.splitlines():
            if "COLMAP" in line.upper() and any(character.isdigit() for character in line):
                return line.strip()
        return "COLMAP version unavailable"

    def help_text(self, command: str, log_dir: Path) -> str:
        if command not in self._help_cache:
            result = self.run(
                [command, "-h"],
                stage=f"help_{command}",
                log_path=log_dir / f"help_{command}.log",
                timeout_seconds=30,
            )
            self._help_cache[command] = result.output
        return self._help_cache[command]

    def find_option(self, command: str, candidates: Sequence[str], log_dir: Path) -> str | None:
        help_text = self.help_text(command, log_dir)
        for candidate in candidates:
            if candidate in help_text:
                return candidate
        return None

    def select_option(self, command: str, candidates: Sequence[str], log_dir: Path) -> str:
        found = self.find_option(command, candidates, log_dir)
        if found is not None:
            return found
        raise ReconstructionError(
            f"Installed COLMAP does not advertise any supported option for {command}: "
            f"{', '.join(candidates)}"
        )
