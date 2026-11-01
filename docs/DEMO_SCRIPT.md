# SpatialForge 3–5 Minute Demonstration Script

This is a recording plan, not evidence that a video has been recorded.

## Shot list and narration

**0:00–0:25 — Problem and room**  
Show the real room and smartphone. “Indoor maps are expensive to produce and rarely connect reconstruction, walkthrough and navigation. SpatialForge builds a reusable digital twin from ordinary capture.”

**0:25–0:55 — Capture**  
Show a slow perimeter recording with overlap and measured landmarks. Explain parallax, blur avoidance and consistent lens choice.

**0:55–1:25 — Quality and reconstruction**  
Show the actual readiness report, accepted frames and live/recorded COLMAP logs. Display registered-image ratio, sparse points, reprojection error and processing time. Do not use synthetic metrics.

**1:25–1:55 — Reconstruction inspection**  
Show the genuine COLMAP/MeshLab model and camera trajectory. If dense output succeeded, show it and label the method. If not, explicitly present the sparse result and limitation.

**1:55–2:35 — Browser digital twin**  
Import the checksummed scene package, select the real scene, switch representations, enter Walk mode and demonstrate mouse look/WASD. Show alignment with recognizable features.

**2:35–3:15 — Spatial intelligence**  
Use the reviewed navigation scene or clearly labeled synthetic demo. Search a POI, render an obstacle-aware route, show minimap progress and deviate to trigger recomputation. Never imply synthetic geometry came from the room.

**3:15–3:45 — Architecture**  
Show the capture → COLMAP → calibration → package → FastAPI → Three.js pipeline and the two-laptop transfer contract.

**3:45–4:15 — Results and honesty**  
Summarize actual measured results and limitations. Mention unvalidated dense, splat, mobile or AR features as future work rather than completed outcomes.

## Recording checklist

- Capture terminal commands and outputs at readable resolution.
- Blur private paths or identifiers if necessary.
- Keep the real scene and “Synthetic demonstration” label visible when switching.
- Record one continuous successful walkthrough plus short fallback clips.
- Export at 1080p and verify audio before submission.
