"""Nature-index span validation and projection compatibility import."""

from sugarglider.analysis.projection import LocalMetricProjection

MAX_INDEX_LATITUDE_SPAN_DEGREES = 10.0

__all__ = ["LocalMetricProjection", "validate_regional_latitude_span"]


def validate_regional_latitude_span(south: float, north: float) -> None:
    """Reject extracts too tall for the fixed-latitude regional approximation."""
    if north - south > MAX_INDEX_LATITUDE_SPAN_DEGREES:
        raise ValueError(
            "nature index latitude span exceeds the regional projection limit"
        )
