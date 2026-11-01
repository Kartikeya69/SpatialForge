import pytest

import spatialforge.engine.processing_profiles as profiles


def test_auto_profile_uses_fast_on_eight_gigabyte_machine(monkeypatch) -> None:
    monkeypatch.setattr(profiles, "memory_snapshot", lambda: {"total_mb": 8192.0, "available_mb": 2048.0, "load_percent": 75.0})
    selected = profiles.resolve_processing_profile("auto")
    assert selected.name == "fast"
    assert selected.geometry_max_dimension == 224
    assert selected.max_photo_count == 80


def test_memory_guard_reports_required_and_available_ram(monkeypatch) -> None:
    monkeypatch.setattr(profiles, "memory_snapshot", lambda: {"total_mb": 8192.0, "available_mb": 64.0, "load_percent": 99.0})
    with pytest.raises(MemoryError, match="64 MB"):
        profiles.validate_memory_headroom(profiles.PROFILES["fast"])


def test_resolve_reconstruction_profile_profiles() -> None:
    from spatialforge.engine.reconstruction.base import ReconstructionConfig, resolve_reconstruction_profile

    base = ReconstructionConfig()
    fast = resolve_reconstruction_profile(base, "fast")
    assert fast.profile == "cpu_fast"
    assert fast.max_num_features == 4096
    assert fast.max_image_size == 1280
    assert fast.num_threads <= 4

    quality = resolve_reconstruction_profile(base, "quality")
    assert quality.profile == "cpu_quality"
    assert quality.max_num_features == 12288
    assert quality.max_image_size == 2000

    balanced = resolve_reconstruction_profile(base, "balanced")
    assert balanced.profile == "cpu_sparse"
    assert balanced.max_num_features == 8192
