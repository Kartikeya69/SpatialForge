# Deployment Guide

## Local production check

```powershell
python -m pip install -e ".[dev]"
cd frontend
npm ci
npm run typecheck
npm test
npm run build
```

Run the API from the repository root:

```powershell
$env:SPATIALFORGE_DATASET_ROOT="datasets"
$env:SPATIALFORGE_CORS_ORIGINS="https://viewer.example.org"
python -m uvicorn spatialforge.api.main:app --host 0.0.0.0 --port 8000
```

Serve `frontend/dist` through a static server or reverse proxy and route `/api` to FastAPI. Large scene assets should be served with TLS, compression where appropriate, correct MIME types and proxy timeouts suitable for the expected asset size. Do not expose arbitrary filesystem directories; the scene API only serves declared manifest assets.

## Required production decisions

- Choose an actual hosting provider and domain.
- Choose persistent storage for scenes and POI writes.
- Set a strict CORS allow-list; do not use `*` with credentials.
- Put request-size, rate and authentication controls in front of authoring endpoints.
- Back up datasets and package archives.
- Validate a public URL from an external browser before claiming deployment.

No public deployment was created during this local task because no hosting target or credentials were supplied.
