# Universal Reconstruction Test Results

Date: 27 October 2026

## Baseline

Before this implementation round:

- Python: 80 passed.
- Frontend: 33 passed across 17 files.

## Locally verified components

- Multi-file photo upload and job creation.
- EXIF orientation correction.
- Photo resolution, blur and duplicate evaluation.
- COLMAP-ready normalized image inventory generation.
- Existing video upload and frame-processing regression coverage.
- Missing depth-model failure persistence with actionable setup text.
- Relative-depth validation.
- Colored 2.5D point generation and PLY export.
- Single-photo scene manifest generation with arbitrary units and navigation disabled.
- Universal three-mode dashboard, actual upload progress plumbing and input-mode limitation labels.
- Viewer policy that starts non-navigable scenes in orbit and disables Walk.

## External validation status

No genuine user capture was provided during this round. COLMAP is not installed on this laptop, and no licensed depth-model weights were supplied. Therefore:

- Genuine multi-photo COLMAP reconstruction: **not executed**.
- Genuine video COLMAP reconstruction: **not executed**.
- Genuine single-photo neural depth inference: **not executed**.
- Real reconstructed asset inspection: **not executed**.

These are external-data/dependency blockers, not simulated passes. Automated geometry tests use isolated generated inputs and an injected deterministic depth array; those fixtures never enter production discovery.

## Final regression results

- Python: **89 passed**, with one third-party Starlette/httpx deprecation warning.
- Frontend: **34 passed across 17 files**.
- TypeScript typecheck: passed.
- Vite production build: passed; 620 modules transformed.
- Initial JavaScript: 262.35 kB, 81.59 kB gzip.
- Lazy Three.js viewer chunk: 1,027.19 kB, 284.48 kB gzip; Vite's size advisory remains.
