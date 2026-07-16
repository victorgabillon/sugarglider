"""Typed asynchronous adapter for the self-hosted GraphHopper API."""

import logging
from collections.abc import Mapping, Sequence
from typing import cast

import httpx

from sugarglider.domain.models import (
    Coordinate,
    GeoJsonPosition,
    PathDetailSegment,
)

logger = logging.getLogger(__name__)

type JsonObject = dict[str, object]

REQUESTED_DETAILS = (
    "edge_id",
    "road_class",
    "road_environment",
    "surface",
    "smoothness",
    "track_type",
    "hike_rating",
    "osm_way_id",
)


class RoutingError(Exception):
    """Base class for expected routing failures."""


class RoutingUnavailableError(RoutingError):
    """GraphHopper could not be reached."""


class RoutingTimeoutError(RoutingError):
    """GraphHopper exceeded the configured timeout."""


class RoutingPointError(RoutingError):
    """One or more user points could not be routed."""


class RoutingUpstreamError(RoutingError):
    """GraphHopper returned an invalid or unexpected response."""


class GraphHopperPath:
    """Parsed first path from a GraphHopper response."""

    def __init__(
        self,
        *,
        distance_m: float,
        duration_ms: int,
        ascend_m: float | None,
        descend_m: float | None,
        geometry: tuple[GeoJsonPosition, ...],
        snapped_points: tuple[GeoJsonPosition, ...] | None,
        details: dict[str, tuple[PathDetailSegment, ...]],
    ) -> None:
        self.distance_m = distance_m
        self.duration_ms = duration_ms
        self.ascend_m = ascend_m
        self.descend_m = descend_m
        self.geometry = geometry
        self.snapped_points = snapped_points
        self.details = details


class GraphHopperClient:
    """Call the GraphHopper HTTP API and narrow its JSON at the boundary."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client

    async def info(self) -> JsonObject:
        """Return validated-enough server information for readiness checks."""
        response = await self._request("GET", "/info")
        payload = self._json_object(response)
        profiles = payload.get("profiles")
        if not isinstance(profiles, Sequence) or isinstance(profiles, str):
            raise RoutingUpstreamError("GraphHopper /info omitted profiles")
        return payload

    async def is_ready(self, profile: str = "hike") -> bool:
        """Return whether GraphHopper advertises the requested profile."""
        payload = await self.info()
        profiles = cast(Sequence[object], payload["profiles"])
        for item in profiles:
            if isinstance(item, str) and item == profile:
                return True
            if isinstance(item, Mapping) and item.get("name") == profile:
                return True
        return False

    async def route(
        self, points: tuple[Coordinate, ...], profile: str = "hike"
    ) -> GraphHopperPath:
        """Route ordered points, preserving GraphHopper's GeoJSON coordinate order."""
        payload: JsonObject = {
            "points": [[point.lon, point.lat] for point in points],
            "profile": profile,
            "points_encoded": False,
            "instructions": False,
            "calc_points": True,
            "elevation": False,
            "snap_preventions": ["motorway", "trunk", "ferry"],
            "details": list(REQUESTED_DETAILS),
        }
        try:
            response = await self._request("POST", "/route", json=payload)
        except RoutingPointError as exc:
            # Encoded values vary with a self-hosted import. Optional path details
            # must never make an otherwise valid route fail completely.
            message = str(exc).lower()
            if not any(term in message for term in ("detail", "encoded value")):
                raise
            payload.pop("details")
            response = await self._request("POST", "/route", json=payload)
        return self._parse_route(response, len(points))

    async def _request(
        self, method: str, path: str, *, json: JsonObject | None = None
    ) -> httpx.Response:
        try:
            if self._client is not None:
                response = await self._client.request(
                    method,
                    f"{self._base_url}{path}",
                    json=json,
                    timeout=self._timeout,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        method,
                        f"{self._base_url}{path}",
                        json=json,
                        timeout=self._timeout,
                    )
        except httpx.TimeoutException as exc:
            raise RoutingTimeoutError("GraphHopper request timed out") from exc
        except httpx.RequestError as exc:
            raise RoutingUnavailableError("GraphHopper is unavailable") from exc

        if response.is_success:
            return response

        message = self._error_message(response)
        logger.warning(
            "GraphHopper returned HTTP %s: %s", response.status_code, message
        )
        if response.status_code == 400:
            raise RoutingPointError(message)
        if response.status_code == 504:
            raise RoutingTimeoutError("GraphHopper request timed out")
        if response.status_code in {502, 503}:
            raise RoutingUnavailableError("GraphHopper is unavailable")
        raise RoutingUpstreamError("GraphHopper returned an unexpected HTTP status")

    def _parse_route(
        self, response: httpx.Response, point_count: int
    ) -> GraphHopperPath:
        payload = self._json_object(response)
        paths = payload.get("paths")
        if not isinstance(paths, list) or not paths:
            raise RoutingUpstreamError("GraphHopper response contained no paths")
        path = paths[0]
        if not isinstance(path, Mapping):
            raise RoutingUpstreamError("GraphHopper path was malformed")

        geometry_object = path.get("points")
        geometry = self._parse_geometry(geometry_object, "path geometry")
        distance = self._number(path.get("distance"), "distance")
        duration = self._integer(path.get("time"), "time")
        ascend = self._optional_number(path.get("ascend"), "ascend")
        descend = self._optional_number(path.get("descend"), "descend")

        snapped_object = path.get("snapped_waypoints")
        snapped = (
            self._parse_geometry(snapped_object, "snapped waypoints")
            if snapped_object is not None
            else None
        )
        if snapped is not None and len(snapped) != point_count:
            raise RoutingUpstreamError(
                "GraphHopper returned incomplete snapped waypoints"
            )

        return GraphHopperPath(
            distance_m=distance,
            duration_ms=duration,
            ascend_m=ascend,
            descend_m=descend,
            geometry=geometry,
            snapped_points=snapped,
            details=self._parse_details(path.get("details")),
        )

    @staticmethod
    def _json_object(response: httpx.Response) -> JsonObject:
        try:
            payload: object = response.json()
        except ValueError as exc:
            raise RoutingUpstreamError("GraphHopper returned invalid JSON") from exc
        if not isinstance(payload, dict) or not all(
            isinstance(key, str) for key in payload
        ):
            raise RoutingUpstreamError("GraphHopper returned an invalid JSON object")
        return cast(JsonObject, payload)

    @classmethod
    def _parse_geometry(cls, value: object, label: str) -> tuple[GeoJsonPosition, ...]:
        if not isinstance(value, Mapping) or value.get("type") != "LineString":
            raise RoutingUpstreamError(f"GraphHopper {label} was malformed")
        coordinates = value.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates:
            raise RoutingUpstreamError(f"GraphHopper {label} had no coordinates")
        parsed: list[GeoJsonPosition] = []
        for coordinate in coordinates:
            if not isinstance(coordinate, list) or len(coordinate) < 2:
                raise RoutingUpstreamError(
                    f"GraphHopper {label} had invalid coordinates"
                )
            lon = cls._number(coordinate[0], "longitude")
            lat = cls._number(coordinate[1], "latitude")
            if not -180 <= lon <= 180 or not -90 <= lat <= 90:
                raise RoutingUpstreamError(f"GraphHopper {label} was out of bounds")
            parsed.append((lon, lat))
        return tuple(parsed)

    @classmethod
    def _parse_details(cls, value: object) -> dict[str, tuple[PathDetailSegment, ...]]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise RoutingUpstreamError("GraphHopper path details were malformed")
        parsed: dict[str, tuple[PathDetailSegment, ...]] = {}
        for key, segments in value.items():
            if not isinstance(key, str) or not isinstance(segments, list):
                raise RoutingUpstreamError("GraphHopper path details were malformed")
            parsed_segments: list[PathDetailSegment] = []
            for segment in segments:
                if not isinstance(segment, list) or len(segment) != 3:
                    raise RoutingUpstreamError("GraphHopper path detail was malformed")
                detail_value = segment[2]
                if detail_value is not None and not isinstance(
                    detail_value, (str, int, float, bool)
                ):
                    raise RoutingUpstreamError(
                        "GraphHopper path detail value was malformed"
                    )
                parsed_segments.append(
                    PathDetailSegment(
                        from_index=cls._integer(segment[0], "detail start"),
                        to_index=cls._integer(segment[1], "detail end"),
                        value=detail_value,
                    )
                )
            parsed[key] = tuple(parsed_segments)
        return parsed

    @staticmethod
    def _number(value: object, label: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RoutingUpstreamError(f"GraphHopper {label} was malformed")
        return float(value)

    @staticmethod
    def _integer(value: object, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise RoutingUpstreamError(f"GraphHopper {label} was malformed")
        return value

    @classmethod
    def _optional_number(cls, value: object, label: str) -> float | None:
        return None if value is None else cls._number(value, label)

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload: object = response.json()
        except ValueError:
            return "GraphHopper rejected the routing request"
        if isinstance(payload, Mapping):
            message = payload.get("message")
            if isinstance(message, str) and message:
                return message
            hints = payload.get("hints")
            if isinstance(hints, list):
                for hint in hints:
                    if isinstance(hint, Mapping) and isinstance(
                        hint.get("message"), str
                    ):
                        return cast(str, hint["message"])
        return "GraphHopper rejected the routing request"
