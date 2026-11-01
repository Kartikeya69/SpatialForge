"""Quality metrics derived from parsed sparse reconstructions."""

from __future__ import annotations

from statistics import mean, median
from typing import Any

from .parser import ParsedModel


def compute_reconstruction_metrics(
    model: ParsedModel,
    *,
    total_input_images: int,
    submodel_count: int,
) -> dict[str, Any]:
    registered = len(model.images)
    errors = [point.reprojection_error for point in model.points]
    track_lengths = [point.track_length for point in model.points if point.track_length > 0]
    metrics: dict[str, Any] = {
        "total_input_images": total_input_images,
        "registered_images": registered,
        "registration_percentage": round(registered / total_input_images * 100, 3)
        if total_input_images
        else 0.0,
        "sparse_point_count": len(model.points),
        "reconstructed_submodels": submodel_count,
    }
    if errors:
        metrics["mean_reprojection_error_pixels"] = round(mean(errors), 6)
        metrics["median_reprojection_error_pixels"] = round(median(errors), 6)
        metrics["maximum_reprojection_error_pixels"] = round(max(errors), 6)
    if track_lengths:
        metrics["mean_track_length"] = round(mean(track_lengths), 4)
        metrics["median_track_length"] = round(median(track_lengths), 4)
    return metrics
