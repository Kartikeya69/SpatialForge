# Dependency and Licensing Notes

## Runtime dependencies

Python dependencies are declared in `pyproject.toml`: FastAPI, NumPy, OpenCV, python-multipart, PyYAML and Uvicorn. Development adds pytest and httpx. Frontend dependencies and exact installed resolutions are declared by `frontend/package.json` and `frontend/package-lock.json`.

COLMAP is an optional external executable used on the reconstruction laptop. FFmpeg may be used externally for video conversion but is not invoked by the current Python pipeline. Dense COLMAP hardware requirements depend on the selected build. Gaussian Splat tooling has not been selected or installed.

For a release, generate and review dependency notices from the actual locked environment. Do not copy license text from an unverified third-party source.

## Project license

No project `LICENSE` file is present in this workspace. The owner must choose and approve a project license before public distribution. SpatialForge code should not be described as open source until that license has been added. This is intentionally documented rather than silently assigning a license on the owner's behalf.
