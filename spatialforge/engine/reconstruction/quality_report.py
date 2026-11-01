"""Evidence-based sparse reconstruction assessment without fabricated quality scores."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .parser import ParsedModel


def build_reconstruction_quality_report(
    model: ParsedModel,
    *,
    input_image_names: list[str],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    registered = {image.name for image in model.images}
    unregistered = [name for name in input_image_names if name not in registered]
    evidence: list[str] = []
    recommendations: list[str] = []
    registration = float(metrics.get("registration_percentage", 0))
    if registration < 70:
        evidence.append("Less than 70% of input images registered in the primary sparse model.")
        recommendations.append("Add overlapping bridge views around the unregistered portions of the capture.")
    if int(metrics.get("reconstructed_submodels", 0)) > 1:
        evidence.append("COLMAP produced multiple disconnected sparse submodels.")
        recommendations.append("Recapture transitions between disconnected areas with shared textured landmarks.")
    reprojection = metrics.get("median_reprojection_error_pixels")
    if isinstance(reprojection, (int, float)) and reprojection > 2.0:
        evidence.append("Median reprojection error is above 2 pixels.")
        recommendations.append("Inspect motion blur, reflective surfaces, and camera calibration consistency.")
    return {
        "schema_version": "1.0.0",
        "assessment_basis": "measured COLMAP sparse-model outputs",
        "metrics": metrics,
        "registered_image_names": sorted(registered),
        "unregistered_image_names": unregistered,
        "observations": evidence,
        "recommendations": recommendations,
        "limitations": [
            "This report evaluates sparse SfM consistency, not mesh completeness or photorealism.",
            "Recognizability requires visual inspection and is never inferred from counts alone.",
        ],
    }


def write_reconstruction_quality_report(report: dict[str, Any], path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temporary.replace(output)
    return output
