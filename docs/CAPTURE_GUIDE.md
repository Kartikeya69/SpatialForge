# Smartphone Capture Guide

## Before recording

- Use the main wide camera without digital zoom; keep one lens throughout.
- Prefer 1080p, 30 fps, stable exposure and landscape orientation.
- Clean the lens and enable good, even room lighting.
- Avoid mirrors, moving people, blank walls and changing exposure where practical.
- Measure three visible, non-collinear landmarks for later calibration.

## Recording pattern

Record 60–90 seconds. Walk slowly around the perimeter and furniture while translating the phone; pure rotation does not provide enough parallax. Keep 60–80% visual overlap between nearby views. Cover corners, doors, floor-wall boundaries, textured objects and both sides of major obstacles. Avoid rapid pans and walking blur.

## Process and assess

```powershell
python scripts\process_capture.py --input room.mp4 --output datasets --sample-fps 2.5
python scripts\analyze_capture.py datasets\<scene_id> --write
```

Read `metadata/capture_readiness.json`. Blocking overlap or image-count findings should trigger a recapture rather than progressively weakening quality thresholds. `spatial_coverage_status` remains unknown until COLMAP registers cameras; the report is a capture heuristic, not reconstruction proof.

## Minimum competition evidence

Preserve the original video, capture manifest, readiness report, accepted JPEGs and capture logs. Record the room and a few measured landmarks on camera for the demo. Never label the deterministic synthetic scene or generated fixtures as real capture evidence.
