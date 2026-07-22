"""Strict canonical schema-version-1 planning requests."""

from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, TypeAdapter, model_validator

from sugarglider.domain.models import Coordinate, ImmutableModel
from sugarglider.planning.profiles import RoutingProfileId

type PlanKind = Literal["auto_tour", "waypoint_route"]
type RouteTopology = Literal["loop", "point_to_point"]
type DistancePriority = Literal["flexible", "balanced", "strict"]
type WaypointOrder = Literal["fixed", "optimize"]
type RequestedStopImportance = Literal["must_visit", "prefer"]
type PreferenceLevel = Literal["off", "prefer"]
type DirectionPreference = Literal["any", "clockwise", "counterclockwise"]
type PathSelection = Literal["shortest", "low_overlap"]
type ConstraintStrength = Literal["exact", "approach", "best_effort"]


class CanonicalModel(ImmutableModel):
    """Canonical public objects reject every unknown or obsolete field."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class DistanceObjective(CanonicalModel):
    target_m: Annotated[float, Field(ge=1_000, le=200_000)]
    tolerance_m: Annotated[float, Field(ge=100, le=10_000)]
    maximum_m: Annotated[float, Field(gt=0, le=200_000)] | None
    priority: DistancePriority

    @model_validator(mode="after")
    def validate_limits(self) -> Self:
        if self.priority == "strict" and self.maximum_m is None:
            raise ValueError("maximum_m is required for strict plans")
        if self.maximum_m is not None and self.maximum_m < self.target_m:
            raise ValueError("maximum_m must not be below target_m")
        if (
            self.priority == "strict"
            and self.maximum_m is not None
            and self.maximum_m < self.target_m + self.tolerance_m
        ):
            raise ValueError(
                "strict maximum_m must contain the complete target tolerance"
            )
        return self


class CommonPreferences(CanonicalModel):
    """Preferences implemented by both planning modes."""

    nature: PreferenceLevel = "prefer"
    path_selection: PathSelection = "low_overlap"


class AutoTourPreferences(CommonPreferences):
    """POI and route-shape preferences implemented by Auto Tour."""

    scenic: PreferenceLevel = "prefer"
    drinking_water: PreferenceLevel = "prefer"
    loop_geometry: PreferenceLevel = "prefer"
    direction: DirectionPreference = "any"


class WaypointPreferences(CommonPreferences):
    """Preferences implemented by ordered Waypoint Route generation."""

    loop_geometry: PreferenceLevel = "off"


class RequestedStop(CanonicalModel):
    id: Annotated[str, Field(min_length=1, max_length=240)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    semantic_coordinate: Coordinate
    importance: RequestedStopImportance
    constraint_strength: Literal["approach", "best_effort"] = "approach"
    osm_reference: Annotated[str, Field(min_length=1, max_length=80)] | None = None
    access_search_radius_m: Annotated[float, Field(ge=25, le=2_000)] = 500.0
    maximum_best_effort_distance_m: Annotated[float, Field(gt=0, le=2_000)] | None = (
        None
    )
    approach_override: Coordinate | None = None

    @model_validator(mode="after")
    def validate_best_effort_limit(self) -> Self:
        if (
            self.constraint_strength == "approach"
            and self.maximum_best_effort_distance_m is not None
        ):
            raise ValueError(
                "maximum_best_effort_distance_m is only valid for best_effort"
            )
        return self


class ExactWaypoint(CanonicalModel):
    """One explicitly hard interior coordinate."""

    id: Annotated[str, Field(min_length=1, max_length=240)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    coordinate: Coordinate


class RouteWaypoint(CanonicalModel):
    """One identified interior point with an explicit routing contract."""

    id: Annotated[str, Field(min_length=1, max_length=240)]
    name: Annotated[str, Field(min_length=1, max_length=200)]
    coordinate: Coordinate
    constraint_strength: ConstraintStrength = "exact"
    access_search_radius_m: Annotated[float, Field(ge=25, le=2_000)] = 500.0
    maximum_best_effort_distance_m: Annotated[float, Field(gt=0, le=2_000)] | None = (
        None
    )
    approach_override: Coordinate | None = None

    @model_validator(mode="after")
    def validate_strength_options(self) -> Self:
        if (
            self.constraint_strength != "best_effort"
            and self.maximum_best_effort_distance_m is not None
        ):
            raise ValueError(
                "maximum_best_effort_distance_m is only valid for best_effort"
            )
        if self.constraint_strength == "exact" and self.approach_override is not None:
            raise ValueError("exact waypoints cannot define an approach override")
        return self


class PlanRequestBase(CanonicalModel):
    schema_version: Literal[1]
    kind: PlanKind
    name: Annotated[str, Field(min_length=1, max_length=200)]
    topology: RouteTopology
    start: Coordinate
    end: Coordinate | None = None
    routing_profile: RoutingProfileId
    candidate_count: Annotated[int, Field(ge=1, le=5)]
    seed: int
    distance_objective: DistanceObjective

    @model_validator(mode="after")
    def validate_explicit_endpoints(self) -> Self:
        if self.topology == "loop":
            if self.end is not None:
                raise ValueError("loop plans must omit end")
        elif self.end is None:
            raise ValueError("point-to-point plans require end")
        elif (self.start.lat, self.start.lon) == (self.end.lat, self.end.lon):
            raise ValueError("point-to-point start and end must differ")
        return self

    @property
    def effective_end(self) -> Coordinate:
        if self.topology == "loop":
            return self.start
        assert self.end is not None
        return self.end


class AutoTourPlanRequest(PlanRequestBase):
    kind: Literal["auto_tour"]
    preferences: AutoTourPreferences
    hard_waypoints: Annotated[tuple[ExactWaypoint, ...], Field(max_length=6)] = ()
    requested_stops: Annotated[tuple[RequestedStop, ...], Field(max_length=30)] = ()
    preferred_discovered_poi_ids: Annotated[tuple[str, ...], Field(max_length=8)] = ()
    free_poi_spur_physical_m: Annotated[float, Field(ge=0, le=1_000)] = 200.0

    @model_validator(mode="after")
    def validate_stable_collections(self) -> Self:
        if self.topology == "point_to_point":
            if self.preferences.direction != "any":
                raise ValueError(
                    "point-to-point Auto Tour does not support loop direction"
                )
            if self.preferences.loop_geometry != "off":
                raise ValueError(
                    "point-to-point Auto Tour does not support loop geometry"
                )
        waypoint_keys = tuple(
            (point.coordinate.lat, point.coordinate.lon)
            for point in self.hard_waypoints
        )
        if len(waypoint_keys) != len(set(waypoint_keys)):
            raise ValueError("hard_waypoints must be unique")
        waypoint_ids = tuple(point.id for point in self.hard_waypoints)
        if len(waypoint_ids) != len(set(waypoint_ids)):
            raise ValueError("hard waypoint IDs must be unique")
        stop_ids = tuple(stop.id for stop in self.requested_stops)
        if len(stop_ids) != len(set(stop_ids)):
            raise ValueError("requested stop IDs must be unique")
        if len(self.preferred_discovered_poi_ids) != len(
            set(self.preferred_discovered_poi_ids)
        ):
            raise ValueError("preferred discovered POI IDs must be unique")
        return self


class WaypointPlanRequest(PlanRequestBase):
    kind: Literal["waypoint_route"]
    preferences: WaypointPreferences
    waypoints: Annotated[tuple[RouteWaypoint, ...], Field(max_length=30)] = ()
    waypoint_order: WaypointOrder

    @model_validator(mode="after")
    def validate_waypoints(self) -> Self:
        if self.topology == "loop" and not self.waypoints:
            raise ValueError("loop Waypoint Route requires an interior waypoint")
        if (
            self.topology == "point_to_point"
            and self.preferences.loop_geometry != "off"
        ):
            raise ValueError(
                "point-to-point Waypoint Route does not support loop geometry"
            )
        keys = tuple(
            (point.coordinate.lat, point.coordinate.lon) for point in self.waypoints
        )
        if len(keys) != len(set(keys)):
            raise ValueError("waypoints must be unique")
        waypoint_ids = tuple(point.id for point in self.waypoints)
        if len(waypoint_ids) != len(set(waypoint_ids)):
            raise ValueError("waypoint IDs must be unique")
        endpoint_keys = {(self.start.lat, self.start.lon)}
        if self.end is not None:
            endpoint_keys.add((self.end.lat, self.end.lon))
        if endpoint_keys.intersection(keys):
            raise ValueError("waypoints must not duplicate plan endpoints")
        return self


type PlanRequest = Annotated[
    AutoTourPlanRequest | WaypointPlanRequest,
    Field(discriminator="kind"),
]
PLAN_REQUEST_ADAPTER: TypeAdapter[PlanRequest] = TypeAdapter(PlanRequest)
