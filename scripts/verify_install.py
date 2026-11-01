"""Verify the SpatialForge local development environment and dependencies."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def check_imports() -> dict[str, tuple[bool, str]]:
    modules = [
        "fastapi",
        "uvicorn",
        "cv2",
        "numpy",
        "PIL",
        "yaml",
        "multipart",
        "pytest",
        "spatialforge",
    ]
    results: dict[str, tuple[bool, str]] = {}
    for mod_name in modules:
        try:
            mod = __import__(mod_name)
            version = getattr(mod, "__version__", "installed")
            results[mod_name] = (True, str(version))
        except Exception as exc:
            results[mod_name] = (False, str(exc))
    return results


def main() -> int:
    print("=" * 60)
    print("SpatialForge Environment & Dependency Verification")
    print("=" * 60)

    # 1. Python runtime
    print("\n[1] Python Environment")
    py_version = sys.version.split()[0]
    print(f"  Python executable: {sys.executable}")
    print(f"  Python version:    {py_version}")
    is_py_compatible = sys.version_info >= (3, 11)
    if not is_py_compatible:
        print("  [ERROR] Python 3.11+ is required.")
    else:
        print("  [OK] Python version satisfies >= 3.11 requirement.")

    # 2. Required imports
    print("\n[2] Required Python Package Imports")
    import_results = check_imports()
    all_imports_ok = True
    for mod_name, (ok, info) in import_results.items():
        status = "[OK]" if ok else "[FAILED]"
        print(f"  {status} {mod_name:<15} : {info}")
        if not ok:
            all_imports_ok = False

    # 3. OpenCV build details
    print("\n[3] OpenCV Build Details")
    try:
        import cv2
        print(f"  OpenCV version:    {cv2.__version__}")
        print(f"  DNN module:        Available ({hasattr(cv2, 'dnn')})")
        print(f"  VideoCapture:      Available ({hasattr(cv2, 'VideoCapture')})")
    except Exception as exc:
        print(f"  [ERROR] Could not inspect OpenCV: {exc}")

    # 4. Config and dataset paths
    print("\n[4] Config & Dataset Paths")
    capture_cfg = PROJECT_ROOT / "configs" / "capture.yaml"
    reconstruction_cfg = PROJECT_ROOT / "configs" / "reconstruction.yaml"
    datasets_dir = PROJECT_ROOT / "datasets"

    print(f"  Capture config:        {capture_cfg} ({'Found' if capture_cfg.is_file() else 'Missing'})")
    print(f"  Reconstruction config: {reconstruction_cfg} ({'Found' if reconstruction_cfg.is_file() else 'Missing'})")
    print(f"  Dataset directory:     {datasets_dir} ({'Found' if datasets_dir.is_dir() else 'Missing'})")

    # 5. AI Depth Model Configuration Status
    print("\n[5] AI Depth Model Status (Single-Photo Mode)")
    local_default_model = PROJECT_ROOT / "models" / "depth_anything_v2_small.onnx"
    depth_model_env = os.getenv("SPATIALFORGE_DEPTH_MODEL") or (str(local_default_model) if local_default_model.is_file() else None)
    if depth_model_env:
        model_path = Path(depth_model_env).expanduser().resolve()
        if model_path.is_file():
            print(f"  [CONFIGURED] Depth Model = {model_path} (exists, {round(model_path.stat().st_size / 1024 / 1024, 2)} MB)")
            try:
                from spatialforge.engine.reconstruction.single_image import DepthAnythingV2Onnx
                est = DepthAnythingV2Onnx(model_path)
                print("  [OK] Depth Anything V2 model verified and loadable for CPU inference.")
            except Exception as exc:
                print(f"  [WARNING] Could not load depth model: {exc}")
        else:
            print(f"  [WARNING] SPATIALFORGE_DEPTH_MODEL = {model_path} (file not found)")
    else:
        print("  [UNCONFIGURED] SPATIALFORGE_DEPTH_MODEL environment variable is not set.")
        print("                 Single-photo relative-depth inference requires an official, license-reviewed")
        print("                 Depth Anything V2 ONNX model file. To configure, set:")
        print(r'                 $env:SPATIALFORGE_DEPTH_MODEL = "C:\path\to\reviewed-model.onnx"')

    # 6. External Tools: COLMAP, Vocab Tree & FFmpeg
    print("\n[6] External Tools Availability (CPU Multi-View Reconstruction)")
    try:
        from spatialforge.engine.reconstruction.runner import resolve_colmap_executable
        resolved_colmap = resolve_colmap_executable()
        print(f"  [CONFIGURED] COLMAP executable: {resolved_colmap} (Ready for CPU reconstruction)")
    except Exception as exc:
        print(f"  [UNAVAILABLE] COLMAP executable: {exc}")

    vocab_tree = PROJECT_ROOT / "models" / "vocab_tree_flickr100K_words32K.bin"
    if vocab_tree.is_file():
        print(f"  [CONFIGURED] Vocab Tree:        {vocab_tree} ({round(vocab_tree.stat().st_size / 1024 / 1024, 2)} MB, ready for large photo sets)")
    else:
        print("  [OPTIONAL]   Vocab Tree:        Not downloaded (Exhaustive matching used for sets <= 80 images)")

    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        print(f"  FFmpeg CLI:        {ffmpeg_path} (Found on PATH)")
    else:
        print("  FFmpeg CLI:        Not found on PATH (Not required; OpenCV VideoCapture handles video ingestion)")

    # 7. Hardware & Local Processing Status
    print("\n[7] Processing Architecture & Local Hardware Status")
    print("  PyTorch:           Not installed / not imported (Repository is intentionally lightweight)")
    print("  Open3D:            Not installed / not imported")
    print("  Trimesh:           Not installed / not imported")
    print("  OpenCV DNN Target: CPU-only execution (cv2.dnn.DNN_TARGET_CPU)")
    print("  CUDA / GPU:        Disabled locally; Dense CUDA reconstruction and Gaussian Splatting")
    print("                     are external-GPU workflows and not run on this machine.")

    # 8. Summary
    print("\n" + "=" * 60)
    if is_py_compatible and all_imports_ok:
        print("Status: LOCAL DEVELOPMENT ENVIRONMENT VERIFIED SUCCESSFULLY")
        print("=" * 60)
        return 0
    else:
        print("Status: VERIFICATION FAILED - Review errors above")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
