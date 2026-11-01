# Reconstruction and Laptop Transfer Guide

## Laptop 2 prerequisites

Install Python 3.11+, project dependencies and an official COLMAP build. Verify the exact launcher:

```powershell
& "C:\Tools\COLMAP\COLMAP.bat" -h
```

The current development laptop has no COLMAP or FFmpeg installation. Do not interpret its mocked tests as reconstruction validation.

## Sparse reconstruction

```powershell
python scripts\reconstruct_scene.py `
  --scene "datasets\<scene_id>" `
  --backend colmap `
  --matcher sequential `
  --colmap-path "C:\Tools\COLMAP\COLMAP.bat"
```

Inspect `metadata/reconstruction_manifest.json`, every COLMAP log, registration percentage, sparse points and reprojection error. Open the selected native model in COLMAP or MeshLab and visually confirm camera trajectory and recognizable structure.

## Dense reconstruction

```powershell
python scripts\dense_reconstruct.py "datasets\<scene_id>" `
  --colmap-path "C:\Tools\COLMAP\COLMAP.bat" `
  --quality balanced `
  --mesher poisson
```

This runs image undistortion, PatchMatch stereo, depth fusion and mesh generation. Some Windows COLMAP builds require CUDA for PatchMatch. If the installed build cannot run it, preserve the failure log and use the sparse representation for the truthful demo rather than fabricating dense output.

## Coordinate and scale calibration

Create `correspondences.json` with at least three non-collinear source points from the reconstruction and matching viewer-world points. Use metres only when targets were physically measured.

```json
{
  "target_units": "meter",
  "source_points": [[0,0,0], [1,0,0], [0,1,0]],
  "target_points": [[0,0,0], [2,0,0], [0,2,0]]
}
```

```powershell
python scripts\calibrate_scene.py correspondences.json --output calibration.json
```

Review RMS and maximum error. Then assemble a browser scene:

```powershell
python scripts\assemble_scene.py "datasets\<scene_id>" `
  --calibration calibration.json `
  --name "Competition Room" `
  --visual-asset "reconstruction/colmap/dense/fused.ply"
```

Omit `--visual-asset` to use the sparse PLY. The assembler refuses incomplete reconstruction, missing camera poses, unsafe paths, invalid calibration, and existing scene manifests.

## Navigation draft

Only after calibration, create a reviewable draft:

```powershell
python scripts\generate_navigation.py "datasets\<scene_id>\reconstruction\colmap\dense\fused.ply" `
  --output "datasets\<scene_id>\navigation\draft" `
  --resolution 0.20 --clearance 0.30 --unit meter --metric-scale-status known --confirm-y-up
```

The draft is deliberately not activated. Compare it against visible floors, walls and openings before copying corrected grid/collider files into the manifest.

## Transfer

```powershell
python scripts\scene_package.py export "datasets\<scene_id>" "<scene_id>.sfscene"
python scripts\scene_package.py validate "<scene_id>.sfscene"
```

On Laptop 1:

```powershell
python scripts\scene_package.py import "<scene_id>.sfscene" --datasets datasets
```
