# Hardware Optimization Report

Date: 28 October 2026

## Detected machine

- CPU: Intel Core i5-1135G7, 4 cores / 8 logical processors.
- Physical memory reported by Windows: 7.73 GiB usable, not 16 GB.
- Graphics: Intel Iris Xe plus NVIDIA MX330 with 2 GB reported adapter memory.
- Installed PyTorch: 2.12.0+cpu; `torch.cuda.is_available()` is false.
- Free C: space during the audit: 6.1 GB.
- COLMAP and FFmpeg were not found on `PATH`.
- No approved Depth Anything ONNX weights are configured.

No packages or models were downloaded for this optimization. An interrupted Trimesh attempt did not install anything. Open3D, OpenVINO, CUDA, cuDNN and model weights remain absent.

## Implemented resource policy

`auto` selects the Fast profile on machines with 10 GB RAM or less. Each profile changes actual analysis and mesh parameters:

| Profile | Analysis width | ORB features | Match-pair ceiling | Photo ceiling | Source MP ceiling | Single-image mesh dimension |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Fast | 640 | 1,200 | 1,500 | 80 | 24 | 224 |
| Balanced | 1,024 | 2,000 | 5,000 | 160 | 40 | 320 |
| Quality | 1,440 | 3,500 | 12,000 | 300 | 64 | 512 |

Every job records the resolved profile and starting physical-memory snapshot. Insufficient headroom stops the job with an explicit error. Full-resolution photographs are decoded one at a time; only compact keypoints/descriptors are retained for graph construction. Large-set pair generation is bounded and uses perceptual-hash retrieval before geometric verification.

Photo-set and single-photo jobs support cooperative cancellation at safe checkpoints. Cancellation cannot interrupt a single native OpenCV DNN call already in progress, but it prevents subsequent geometry/export work. Failed or cancelled jobs remove partial exported frames, mesh, point cloud, depth preview, viewer manifest and quality report.

## Executed measurements

An existing CPU PyTorch runtime test used a `[1, 3, 518, 518]` tensor under `torch.inference_mode()`: 10.774 ms for a small pooling operation and a measured 3.457 MiB RSS increase. This confirms CPU tensor execution only; it is not a Depth Anything performance benchmark.

At the profile check, Windows reported 7,914.8 MB physical memory, 1,344.6 MB available and 83% load. `auto` correctly resolved to Fast.

Automated results:

- Python: 97 passed; one third-party Starlette/httpx deprecation warning.
- Frontend: 34 passed across 17 files.
- TypeScript typecheck: passed.
- Production build: passed.
- Initial JavaScript: 264.32 kB (82.07 kB gzip).
- Lazy viewer chunk: 1,027.62 kB (284.58 kB gzip); the existing Vite >500 kB warning remains.

## Unverified hardware-dependent work

Real Depth Anything inference was not run because no reviewed ONNX weights exist. COLMAP execution was not run because the executable is absent. Dense reconstruction, textured export, Open3D operations, physical accuracy, GPU behavior and real-scene browser performance remain unverified. The existing OpenCV geometry implementation is the active dependency-free CPU path.

