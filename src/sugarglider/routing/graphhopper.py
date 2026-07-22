"""Typed asynchronous adapter for the self-hosted GraphHopper API."""

import logging
from collections.abc import Mapping, Sequence
from hashlib import sha256
from math import isfinite
from typing import Any, cast

import httpx
from shapely import make_valid
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from sugarglider.domain.models import (
    Coordinate,
    GeoJsonPosition,
    PathDetailSegment,
)
from sugarglider.routing.backend import IsochronePolygon, IsochroneResult, RoutedPath
from sugarglider.routing.errors import (
    RoutingError,
    RoutingPointError,
    RoutingProfileUnavailableError,
    RoutingTimeoutError,
    RoutingUnavailableError,
    RoutingUpstreamError,
)
from sugarglider.routing.profiles import (
    ROUTING_PROFILES,
    GraphHopperProfile,
    RoutingProfileId,
    routing_profile,
)

__all__ = [
    "GraphHopperClient",
    "GraphHopperPath",
    "RoutingError",
    "RoutingPointError",
    "RoutingProfileUnavailableError",
    "RoutingTimeoutError",
    "RoutingUnavailableError",
    "RoutingUpstreamError",
]

logger = logging.getLogger(__name__)

type JsonObject = dict[str, object]
type QueryValue = str | int | float | bool

BUILTIN_DETAILS = ("edge_id",)


GraphHopperPath = RoutedPath


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
        self._supported_details: dict[GraphHopperProfile, tuple[str, ...]] = {}
        self._advertised_profiles: frozenset[str] | None = None

    async def info(self) -> JsonObject:
        """Return validated-enough server information for readiness checks."""
        response = await self._request("GET", "/info")
        payload = self._json_object(response)
        profiles = payload.get("profiles")
        if not isinstance(profiles, Sequence) or isinstance(profiles, str):
            raise RoutingUpstreamError("GraphHopper /info omitted profiles")
        self._cache_supported_details(payload)
        return payload

    async def available_profiles(self) -> frozenset[str]:
        """Return the safe set of backend profile names advertised by `/info`."""
        payload = await self.info()
        profiles = cast(Sequence[object], payload["profiles"])
        names: set[str] = set()
        for item in profiles:
            if isinstance(item, str):
                names.add(item)
            elif isinstance(item, Mapping) and isinstance(item.get("name"), str):
                names.add(cast(str, item["name"]))
        self._advertised_profiles = frozenset(names)
        return self._advertised_profiles

    async def ensure_profile_available(self, profile: RoutingProfileId) -> None:
        available = self._advertised_profiles
        if available is None:
            return
        if routing_profile(profile).graphhopper_profile not in available:
            raise RoutingProfileUnavailableError(profile)

    async def is_ready(self, profile: RoutingProfileId = "hike") -> bool:
        """Return whether GraphHopper advertises one resolved public profile."""
        return (
            routing_profile(profile).graphhopper_profile
            in await self.available_profiles()
        )

    async def route(
        self,
        points: tuple[Coordinate, ...],
        profile: RoutingProfileId = "hike",
        *,
        pass_through: bool = False,
    ) -> RoutedPath:
        """Route ordered points, preserving GraphHopper's GeoJSON coordinate order."""
        resolved = routing_profile(profile)
        await self.ensure_profile_available(profile)
        requested_details = list(await self._details_for_route(profile))
        await self.ensure_profile_available(profile)
        payload: JsonObject = {
            "points": [[point.lon, point.lat] for point in points],
            "profile": resolved.graphhopper_profile,
            "points_encoded": False,
            "instructions": False,
            "calc_points": True,
            "elevation": False,
            "snap_preventions": list(resolved.snap_preventions),
            "details": requested_details,
        }
        if pass_through:
            payload["pass_through"] = True
        response = await self._request_with_detail_fallback(
            payload, requested_details, resolved.graphhopper_profile
        )
        return self._parse_route(response, expected_snapped_point_count=len(points))

    async def alternative_routes(
        self,
        start: Coordinate,
        end: Coordinate,
        profile: RoutingProfileId = "hike",
        *,
        max_paths: int = 3,
        max_weight_factor: float = 1.6,
        max_share_factor: float = 0.5,
    ) -> tuple[RoutedPath, ...]:
        """Return distinct GraphHopper alternatives for exactly one routed leg."""
        resolved = routing_profile(profile)
        await self.ensure_profile_available(profile)
        requested_details = list(await self._details_for_route(profile))
        await self.ensure_profile_available(profile)
        payload: JsonObject = {
            "points": [[start.lon, start.lat], [end.lon, end.lat]],
            "profile": resolved.graphhopper_profile,
            "algorithm": "alternative_route",
            "alternative_route.max_paths": max_paths,
            "alternative_route.max_weight_factor": max_weight_factor,
            "alternative_route.max_share_factor": max_share_factor,
            "points_encoded": False,
            "instructions": False,
            "calc_points": True,
            "elevation": False,
            "snap_preventions": list(resolved.snap_preventions),
            "details": requested_details,
        }
        response = await self._request_with_detail_fallback(
            payload, requested_details, resolved.graphhopper_profile
        )
        alternatives = self._parse_routes(
            response,
            expected_snapped_point_count=2,
            require_snapped_points=True,
        )
        distinct: list[RoutedPath] = []
        signatures: set[str] = set()
        for path in alternatives:
            signature = self._path_signature(path)
            if signature not in signatures:
                signatures.add(signature)
                distinct.append(path)
        if not distinct:
            raise RoutingUpstreamError("GraphHopper returned no distinct alternatives")
        return tuple(distinct)

    async def round_trip(
        self,
        start: Coordinate,
        distance_m: float,
        seed: int,
        profile: RoutingProfileId = "hike",
        *,
        heading_degrees: float | None = None,
    ) -> RoutedPath:
        """Ask the local GraphHopper instance for one graph-valid proposal loop."""
        if not isfinite(distance_m) or distance_m <= 0:
            raise ValueError("round-trip distance must be finite and positive")
        if heading_degrees is not None and (
            not isfinite(heading_degrees) or not 0 <= heading_degrees < 360
        ):
            raise ValueError("round-trip heading must be within [0, 360)")
        resolved = routing_profile(profile)
        await self.ensure_profile_available(profile)
        requested_details = list(await self._details_for_route(profile))
        await self.ensure_profile_available(profile)
        payload: JsonObject = {
            "points": [[start.lon, start.lat]],
            "profile": resolved.graphhopper_profile,
            "algorithm": "round_trip",
            "round_trip.distance": distance_m,
            "round_trip.seed": seed,
            "points_encoded": False,
            "instructions": False,
            "calc_points": True,
            "elevation": False,
            "snap_preventions": list(resolved.snap_preventions),
            "details": requested_details,
        }
        if heading_degrees is not None:
            payload["headings"] = [heading_degrees]
        response = await self._request_with_detail_fallback(
            payload, requested_details, resolved.graphhopper_profile
        )
        return self._parse_route(response, expected_snapped_point_count=None)

    async def isochrone(
        self,
        start: Coordinate,
        profile: RoutingProfileId,
        *,
        distance_limit_m: float,
        buckets: int = 1,
        reverse_flow: bool = False,
    ) -> IsochroneResult:
        """Return one validated local reachable envelope from ``/isochrone``."""
        if not isfinite(distance_limit_m) or distance_limit_m <= 0:
            raise ValueError("isochrone distance limit must be finite and positive")
        if buckets < 1:
            raise ValueError("isochrone buckets must be positive")
        await self.ensure_profile_available(profile)
        response = await self._request(
            "GET",
            "/isochrone",
            params={
                "point": f"{start.lat},{start.lon}",
                "profile": routing_profile(profile).graphhopper_profile,
                "distance_limit": distance_limit_m,
                "buckets": buckets,
                "reverse_flow": str(reverse_flow).lower(),
            },
        )
        return self._parse_isochrone(response)

    async def _details_for_route(self, profile: RoutingProfileId) -> tuple[str, ...]:
        resolved = routing_profile(profile)
        cached = self._supported_details.get(resolved.graphhopper_profile)
        if cached is not None:
            return cached
        try:
            await self.info()
        except RoutingError:
            # Detail discovery is an optimization, not a routing prerequisite.
            pass
        return self._supported_details.setdefault(
            resolved.graphhopper_profile,
            (*BUILTIN_DETAILS, *resolved.requested_path_details),
        )

    async def _request_with_detail_fallback(
        self,
        payload: JsonObject,
        requested_details: list[str],
        backend_profile: GraphHopperProfile,
    ) -> httpx.Response:
        """Retry the complete request after removing unsupported path details."""
        while True:
            try:
                return await self._request("POST", "/route", json=payload)
            except RoutingPointError as exc:
                message = str(exc).lower()
                if not any(term in message for term in ("detail", "encoded value")):
                    raise
                unsupported = next(
                    (
                        detail
                        for detail in requested_details
                        if detail.lower() in message
                    ),
                    None,
                )
                if unsupported is not None:
                    requested_details.remove(unsupported)
                elif requested_details != list(BUILTIN_DETAILS):
                    requested_details[:] = BUILTIN_DETAILS
                elif requested_details:
                    requested_details.clear()
                else:
                    raise
                payload["details"] = requested_details.copy()
                self._supported_details[backend_profile] = tuple(requested_details)

    def _cache_supported_details(self, payload: JsonObject) -> None:
        encoded_values = payload.get("encoded_values")
        supported: set[str]
        if isinstance(encoded_values, Mapping):
            supported = {key for key in encoded_values if isinstance(key, str)}
        elif isinstance(encoded_values, Sequence) and not isinstance(
            encoded_values, str
        ):
            supported = {value for value in encoded_values if isinstance(value, str)}
        else:
            return
        for profile in ROUTING_PROFILES:
            self._supported_details[profile.graphhopper_profile] = (
                *BUILTIN_DETAILS,
                *(
                    detail
                    for detail in profile.requested_path_details
                    if detail in supported
                ),
            )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: JsonObject | None = None,
        params: Mapping[str, QueryValue] | None = None,
    ) -> httpx.Response:
        try:
            if self._client is not None:
                response = await self._client.request(
                    method,
                    f"{self._base_url}{path}",
                    json=json,
                    params=params,
                    timeout=self._timeout,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        method,
                        f"{self._base_url}{path}",
                        json=json,
                        params=params,
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

    def _parse_isochrone(self, response: httpx.Response) -> IsochroneResult:
        """Parse Polygon/MultiPolygon GeoJSON, repairing only invalid polygons."""
        payload = self._json_object(response)
        geometry_values = self._isochrone_geometry_values(payload)
        geometries: list[BaseGeometry] = []
        repaired = False
        for value in geometry_values:
            try:
                geometry = shape(cast(dict[str, Any], dict(value)))
            except (AttributeError, TypeError, ValueError) as exc:
                raise RoutingUpstreamError(
                    "GraphHopper isochrone geometry was malformed"
                ) from exc
            if geometry.is_empty or not isinstance(geometry, (Polygon, MultiPolygon)):
                raise RoutingUpstreamError(
                    "GraphHopper isochrone was not non-empty polygonal geometry"
                )
            self._validate_wgs84_polygonal(geometry)
            if not geometry.is_valid:
                # ``make_valid`` is deliberately the only repair path. Polygonal
                # components are retained; arbitrary linework is never promoted.
                repaired_geometry = make_valid(geometry)
                repaired = True
                polygonal_repair = self._polygonal_components(repaired_geometry)
                if (
                    polygonal_repair is None
                    or polygonal_repair.is_empty
                    or not polygonal_repair.is_valid
                ):
                    raise RoutingUpstreamError(
                        "GraphHopper isochrone geometry could not be repaired"
                    )
                geometry = polygonal_repair
            geometries.append(geometry)
        combined = unary_union(geometries)
        polygonal = self._polygonal_components(combined)
        if polygonal is None or polygonal.is_empty or not polygonal.is_valid:
            raise RoutingUpstreamError(
                "GraphHopper isochrone did not contain valid polygonal geometry"
            )
        self._validate_wgs84_polygonal(polygonal)
        polygons = (polygonal,) if isinstance(polygonal, Polygon) else polygonal.geoms
        return IsochroneResult(
            polygons=tuple(
                IsochronePolygon(
                    exterior=tuple(
                        (float(lon), float(lat))
                        for lon, lat, *_rest in polygon.exterior.coords
                    ),
                    holes=tuple(
                        tuple(
                            (float(lon), float(lat)) for lon, lat, *_rest in ring.coords
                        )
                        for ring in polygon.interiors
                    ),
                )
                for polygon in polygons
            ),
            geometry_was_repaired=repaired,
        )

    @staticmethod
    def _isochrone_geometry_values(
        payload: JsonObject,
    ) -> tuple[Mapping[str, object], ...]:
        candidates: object
        if payload.get("type") == "FeatureCollection":
            candidates = payload.get("features")
        elif "polygons" in payload:
            candidates = payload.get("polygons")
        else:
            candidates = [payload]
        if not isinstance(candidates, list) or not candidates:
            raise RoutingUpstreamError("GraphHopper isochrone contained no polygons")
        values: list[Mapping[str, object]] = []
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                raise RoutingUpstreamError(
                    "GraphHopper isochrone feature was malformed"
                )
            geometry = (
                candidate.get("geometry")
                if candidate.get("type") == "Feature"
                else candidate
            )
            if not isinstance(geometry, Mapping):
                raise RoutingUpstreamError(
                    "GraphHopper isochrone geometry was malformed"
                )
            values.append(cast(Mapping[str, object], geometry))
        return tuple(values)

    @staticmethod
    def _polygonal_components(
        geometry: BaseGeometry,
    ) -> Polygon | MultiPolygon | None:
        if isinstance(geometry, (Polygon, MultiPolygon)):
            return geometry
        if isinstance(geometry, GeometryCollection):
            polygons: list[Polygon] = []
            for component in geometry.geoms:
                if isinstance(component, Polygon):
                    polygons.append(component)
                elif isinstance(component, MultiPolygon):
                    polygons.extend(component.geoms)
            if not polygons:
                return None
            combined = unary_union(polygons)
            return combined if isinstance(combined, (Polygon, MultiPolygon)) else None
        return None

    @staticmethod
    def _validate_wgs84_polygonal(geometry: Polygon | MultiPolygon) -> None:
        polygons = (geometry,) if isinstance(geometry, Polygon) else geometry.geoms
        for polygon in polygons:
            rings = (polygon.exterior, *polygon.interiors)
            for ring in rings:
                for coordinate in ring.coords:
                    if len(coordinate) < 2:
                        raise RoutingUpstreamError(
                            "GraphHopper isochrone coordinate was malformed"
                        )
                    lon, lat = float(coordinate[0]), float(coordinate[1])
                    if not (
                        isfinite(lon)
                        and isfinite(lat)
                        and -180 <= lon <= 180
                        and -90 <= lat <= 90
                    ):
                        raise RoutingUpstreamError(
                            "GraphHopper isochrone coordinate was out of bounds"
                        )

    def _parse_route(
        self,
        response: httpx.Response,
        expected_snapped_point_count: int | None,
    ) -> RoutedPath:
        payload = self._json_object(response)
        paths = payload.get("paths")
        if not isinstance(paths, list) or not paths:
            raise RoutingUpstreamError("GraphHopper response contained no paths")
        return self._parse_path(
            paths[0],
            expected_snapped_point_count=expected_snapped_point_count,
            require_snapped_points=False,
        )

    def _parse_routes(
        self,
        response: httpx.Response,
        *,
        expected_snapped_point_count: int | None,
        require_snapped_points: bool,
    ) -> tuple[RoutedPath, ...]:
        payload = self._json_object(response)
        paths = payload.get("paths")
        if not isinstance(paths, list) or not paths:
            raise RoutingUpstreamError("GraphHopper response contained no paths")
        return tuple(
            self._parse_path(
                path,
                expected_snapped_point_count=expected_snapped_point_count,
                require_snapped_points=require_snapped_points,
            )
            for path in paths
        )

    def _parse_path(
        self,
        path: object,
        *,
        expected_snapped_point_count: int | None,
        require_snapped_points: bool,
    ) -> RoutedPath:
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
        if require_snapped_points and snapped is None:
            raise RoutingUpstreamError("GraphHopper path omitted snapped waypoints")
        if (
            snapped is not None
            and expected_snapped_point_count is not None
            and len(snapped) != expected_snapped_point_count
        ):
            raise RoutingUpstreamError(
                "GraphHopper returned incomplete snapped waypoints"
            )

        return RoutedPath(
            distance_m=distance,
            duration_ms=duration,
            ascend_m=ascend,
            descend_m=descend,
            geometry=geometry,
            snapped_points=snapped,
            details=self._parse_details(path.get("details"), len(geometry)),
        )

    @staticmethod
    def _path_signature(path: RoutedPath) -> str:
        edge_segments = path.details.get("edge_id", ())
        edge_values = tuple(
            segment.value
            for segment in edge_segments
            if isinstance(segment.value, int) and not isinstance(segment.value, bool)
        )
        if edge_values:
            source = "edges:" + ",".join(str(value) for value in edge_values)
        else:
            source = "geometry:" + ";".join(
                f"{lon:.6f},{lat:.6f}" for lon, lat in path.geometry
            )
        return sha256(source.encode()).hexdigest()

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
    def _parse_details(
        cls, value: object, geometry_length: int
    ) -> dict[str, tuple[PathDetailSegment, ...]]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise RoutingUpstreamError("GraphHopper path details were malformed")
        parsed: dict[str, tuple[PathDetailSegment, ...]] = {}
        if not all(isinstance(key, str) for key in value):
            raise RoutingUpstreamError("GraphHopper path details were malformed")
        keys = cast(list[str], sorted(value))
        for key in keys:
            segments = value[key]
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
                from_index = cls._integer(segment[0], "detail start")
                to_index = cls._integer(segment[1], "detail end")
                if from_index < 0 or to_index <= from_index:
                    raise RoutingUpstreamError(
                        "GraphHopper path detail interval was invalid"
                    )
                if to_index >= geometry_length:
                    raise RoutingUpstreamError(
                        "GraphHopper path detail interval exceeded geometry"
                    )
                parsed_segments.append(
                    PathDetailSegment(
                        from_index=from_index,
                        to_index=to_index,
                        value=detail_value,
                    )
                )
            parsed_segments.sort(key=lambda item: (item.from_index, item.to_index))
            for previous, current in zip(
                parsed_segments, parsed_segments[1:], strict=False
            ):
                if current.from_index < previous.to_index:
                    raise RoutingUpstreamError(
                        "GraphHopper path detail intervals overlapped"
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
