"""Memory-bounded processing profiles with no optional runtime dependencies."""

from __future__ import annotations

import ctypes
import os
from dataclasses import asdict, dataclass
from typing import Literal

ProcessingProfileName = Literal["auto", "fast", "balanced", "quality"]


@dataclass(frozen=True)
class ProcessingProfile:
    name: Literal["fast", "balanced", "quality"]
    analysis_width: int
    orb_features: int
    max_match_pairs: int
    max_photo_count: int
    max_source_megapixels: float
    geometry_max_dimension: int
    minimum_available_memory_mb: int

    def to_dict(self) -> dict[str, int | float | str]:
        return asdict(self)


PROFILES = {
    "fast": ProcessingProfile("fast", 640, 1200, 1500, 80, 24.0, 224, 128),
    "balanced": ProcessingProfile("balanced", 1024, 2000, 5000, 160, 40.0, 320, 768),
    "quality": ProcessingProfile("quality", 1440, 3500, 12000, 300, 64.0, 512, 1536),
}


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_ulong),
        ("memory_load", ctypes.c_ulong),
        ("total_physical", ctypes.c_ulonglong),
        ("available_physical", ctypes.c_ulonglong),
        ("total_page_file", ctypes.c_ulonglong),
        ("available_page_file", ctypes.c_ulonglong),
        ("total_virtual", ctypes.c_ulonglong),
        ("available_virtual", ctypes.c_ulonglong),
        ("available_extended_virtual", ctypes.c_ulonglong),
    ]


def memory_snapshot() -> dict[str, float] | None:
    """Return physical memory totals on Windows without adding psutil as a dependency."""
    if os.name != "nt":
        return None
    status = _MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return {
        "total_mb": round(status.total_physical / 1024 / 1024, 1),
        "available_mb": round(status.available_physical / 1024 / 1024, 1),
        "load_percent": float(status.memory_load),
    }


def resolve_processing_profile(name: ProcessingProfileName = "auto") -> ProcessingProfile:
    if name != "auto":
        try:
            return PROFILES[name]
        except KeyError as exc:
            raise ValueError("profile must be auto, fast, balanced, or quality") from exc
    snapshot = memory_snapshot()
    if snapshot is None or snapshot["total_mb"] <= 10 * 1024:
        return PROFILES["fast"]
    if snapshot["total_mb"] <= 20 * 1024:
        return PROFILES["balanced"]
    return PROFILES["quality"]


def validate_memory_headroom(profile: ProcessingProfile) -> dict[str, float] | None:
    snapshot = memory_snapshot()
    if snapshot is not None and snapshot["available_mb"] < profile.minimum_available_memory_mb:
        raise MemoryError(
            f"The {profile.name} profile needs at least {profile.minimum_available_memory_mb} MB "
            f"available RAM before starting; Windows currently reports {snapshot['available_mb']:.0f} MB. "
            "Close other applications or select a lower profile."
        )
    return snapshot


class ProcessingCancelled(RuntimeError):
    """Raised when a cooperative cancellation request reaches a safe checkpoint."""
