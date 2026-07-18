"""Small deterministic equirectangular metric projection for regional extracts."""

from dataclasses import dataclass
from math import cos, degrees, isfinite, radians

from shapely.affinity import affine_transform
from shapely.geometry import LineString, MultiPolygon, Polygon

from sugarglider.analysis.route import EARTH_RADIUS_M
from sugarglider.domain.models import GeoJsonPosition

MAX_INDEX_LATITUDE_SPAN_DEGREES = 10.0


@dataclass(frozen=True)
class LocalMetricProjection:
    """Project WGS84 to local metres at one latitude; not globally equal-area."""

    reference_latitude: float

    def __post_init__(self) -> None:
        if (
            not isfinite(self.reference_latitude)
            or not -90 <= self.reference_latitude <= 90
        ):
            raise ValueError("reference latitude must be finite and within WGS84")
        if abs(cos(radians(self.reference_latitude))) < 1e-12:
            raise ValueError("reference latitude is too close to a pole")

    @property
    def longitude_scale(self) -> float:
        return EARTH_RADIUS_M * cos(radians(self.reference_latitude))

    def project_position(self, position: GeoJsonPosition) -> tuple[float, float]:
        lon, lat = position
        if not isfinite(lon) or not -180 <= lon <= 180:
            raise ValueError("longitude must be finite and within WGS84")
        if not isfinite(lat) or not -90 <= lat <= 90:
            raise ValueError("latitude must be finite and within WGS84")
        return (self.longitude_scale * radians(lon), EARTH_RADIUS_M * radians(lat))

    def unproject_position(self, position: tuple[float, float]) -> GeoJsonPosition:
        x, y = position
        return (degrees(x / self.longitude_scale), degrees(y / EARTH_RADIUS_M))

    def project_line(self, positions: tuple[GeoJsonPosition, ...]) -> LineString:
        return LineString(
            tuple(self.project_position(position) for position in positions)
        )

    def project_polygon(
        self, geometry: Polygon | MultiPolygon
    ) -> Polygon | MultiPolygon:
        projected = affine_transform(
            geometry,
            (
                self.longitude_scale * radians(1),
                0,
                0,
                EARTH_RADIUS_M * radians(1),
                0,
                0,
            ),
        )
        return projected


def validate_regional_latitude_span(south: float, north: float) -> None:
    """Reject extracts too tall for the fixed-latitude regional approximation."""
    if north - south > MAX_INDEX_LATITUDE_SPAN_DEGREES:
        raise ValueError(
            "nature index latitude span exceeds the regional projection limit"
        )
