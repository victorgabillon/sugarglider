"""Build-only coverage checks; a header is evidence, not an OSM quality guarantee."""

from math import isfinite

import osmium

type Bounds = tuple[float, float, float, float]


def validate_bounds(bounds: Bounds) -> Bounds:
    west, south, east, north = bounds
    if not all(isfinite(value) for value in bounds) or not (
        -180 <= west < east <= 180 and -85.051129 <= south < north <= 85.051129
    ):
        raise ValueError("invalid regional bounds")
    return bounds


def require_header_coverage(header: osmium.osm.Box, bounds: Bounds) -> Bounds:
    validate_bounds(bounds)
    if not header.valid():
        raise ValueError("source coverage cannot be proven: missing OSM header bounds")
    source = (
        header.bottom_left.lon,
        header.bottom_left.lat,
        header.top_right.lon,
        header.top_right.lat,
    )
    west, south, east, north = bounds
    if not all(isfinite(value) for value in source) or not (
        -180 <= source[0] <= west < east <= source[2] <= 180
        and -90 <= source[1] <= south < north <= source[3] <= 90
    ):
        raise ValueError("source header bounds do not cover the requested region")
    return source
