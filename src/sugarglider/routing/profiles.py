"""Canonical immutable public routing-profile registry and catalog models."""

from typing import Literal

from pydantic import ConfigDict, field_validator

from sugarglider.domain.models import (
    ImmutableModel,
)
from sugarglider.domain.models import (
    RoutingProfileId as RoutingProfileId,
)

type GraphHopperProfile = Literal[
    "hike", "trail_run", "bike", "gravel_bike", "mtb", "racingbike"
]
type ActivityKind = Literal["walking", "running", "cycling"]
type AccessMode = Literal["foot", "bicycle"]
type SnapPrevention = Literal[
    "motorway",
    "trunk",
    "ferry",
    "tunnel",
    "bridge",
    "ford",
]
type QualityMetricId = Literal[
    "distance",
    "repetition",
    "immediate_backtracking",
    "surface",
    "major_road",
    "trail_like",
    "hiking_network",
    "technical_hiking",
    "runnable_surface",
    "technical_trail",
    "steps",
    "poor_smoothness",
    "cycling_network",
    "cycleway_like",
    "suitable_unpaved",
    "track",
    "rough_surface",
    "mtb_rating",
    "nature",
    "loop_geometry",
]

COMMON_DETAILS = (
    "osm_way_id",
    "road_class",
    "road_environment",
    "surface",
    "smoothness",
    "track_type",
    "car_access",
)
FOOT_DETAILS = (
    "foot_access",
    "foot_average_speed",
    "foot_priority",
    "foot_network",
    "foot_road_access",
    "hike_rating",
)
BICYCLE_DETAILS = (
    "bike_access",
    "bike_average_speed",
    "bike_priority",
    "bike_network",
    "bike_road_access",
    "mtb_rating",
)
SNAP_PREVENTION_ORDER: tuple[SnapPrevention, ...] = (
    "motorway",
    "trunk",
    "ferry",
    "tunnel",
    "bridge",
    "ford",
)


class RoutingProfile(ImmutableModel):
    """One public activity and its internal GraphHopper routing policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: RoutingProfileId
    graphhopper_profile: GraphHopperProfile
    activity_kind: ActivityKind
    access_mode: AccessMode
    display_name: str
    short_description: str
    icon_key: str
    allowed_quality_metrics: tuple[QualityMetricId, ...]
    requested_path_details: tuple[str, ...]
    snap_preventions: tuple[SnapPrevention, ...]
    supports_auto_tour: bool = True
    supports_waypoint_route: bool = True
    supports_loop: bool = True
    supports_point_to_point: bool = True
    elevation_aware: bool = False

    @field_validator("snap_preventions")
    @classmethod
    def _validate_snap_preventions(
        cls, value: tuple[SnapPrevention, ...]
    ) -> tuple[SnapPrevention, ...]:
        """Reject duplicate or non-canonical packaged GraphHopper options."""
        if len(value) != len(set(value)):
            raise ValueError("snap preventions must be unique")
        order = {
            prevention: index for index, prevention in enumerate(SNAP_PREVENTION_ORDER)
        }
        if value != tuple(sorted(value, key=order.__getitem__)):
            raise ValueError("snap preventions must use canonical GraphHopper order")
        return value


class RoutingProfileCapabilities(ImmutableModel):
    supports_auto_tour: bool
    supports_waypoint_route: bool
    supports_loop: bool
    supports_point_to_point: bool
    elevation_aware: bool


class PublicRoutingProfile(ImmutableModel):
    id: RoutingProfileId
    activity_kind: ActivityKind
    access_mode: AccessMode
    display_name: str
    short_description: str
    icon_key: str
    quality_metrics: tuple[QualityMetricId, ...]
    capabilities: RoutingProfileCapabilities


class RoutingProfileStatus(ImmutableModel):
    profile: PublicRoutingProfile
    available: bool
    warnings: tuple[str, ...] = ()


class RoutingProfileCatalog(ImmutableModel):
    schema_version: Literal[1] = 1
    profiles: tuple[RoutingProfileStatus, ...]


_COMMON_METRICS: tuple[QualityMetricId, ...] = (
    "distance",
    "repetition",
    "immediate_backtracking",
    "surface",
    "major_road",
    "nature",
    "loop_geometry",
)
_DEFAULT_SNAP_PREVENTIONS: tuple[SnapPrevention, ...] = (
    "motorway",
    "trunk",
    "ferry",
)


def _profile(
    profile_id: RoutingProfileId,
    backend: GraphHopperProfile,
    activity: ActivityKind,
    access: AccessMode,
    name: str,
    description: str,
    icon: str,
    metrics: tuple[QualityMetricId, ...],
) -> RoutingProfile:
    details = FOOT_DETAILS if access == "foot" else BICYCLE_DETAILS
    return RoutingProfile(
        id=profile_id,
        graphhopper_profile=backend,
        activity_kind=activity,
        access_mode=access,
        display_name=name,
        short_description=description,
        icon_key=icon,
        allowed_quality_metrics=(*_COMMON_METRICS, *metrics),
        requested_path_details=(*COMMON_DETAILS, *details),
        snap_preventions=_DEFAULT_SNAP_PREVENTIONS,
    )


ROUTING_PROFILES: tuple[RoutingProfile, ...] = (
    _profile(
        "trail_run",
        "trail_run",
        "running",
        "foot",
        "Trail run",
        "Runnable paths and moderate unpaved trails with lower technicality.",
        "trail-run",
        (
            "runnable_surface",
            "trail_like",
            "technical_trail",
            "steps",
            "poor_smoothness",
        ),
    ),
    _profile(
        "hike",
        "hike",
        "walking",
        "foot",
        "Hike",
        "Walking routes that favor trails, hiking networks and mapped nature.",
        "hike",
        (
            "trail_like",
            "hiking_network",
            "technical_hiking",
            "steps",
            "poor_smoothness",
        ),
    ),
    _profile(
        "city_bike",
        "bike",
        "cycling",
        "bicycle",
        "City bike",
        "Cycleways and smoother paved connections for everyday cycling.",
        "city-bike",
        ("cycling_network", "cycleway_like", "rough_surface", "steps"),
    ),
    _profile(
        "gravel_bike",
        "gravel_bike",
        "cycling",
        "bicycle",
        "Gravel bike",
        "Coherent mixed-surface routes using suitable gravel and quiet connectors.",
        "gravel-bike",
        (
            "cycling_network",
            "suitable_unpaved",
            "track",
            "rough_surface",
            "steps",
            "mtb_rating",
        ),
    ),
    _profile(
        "mountain_bike",
        "mtb",
        "cycling",
        "bicycle",
        "Mountain bike",
        "Off-road tracks and suitable trails with technicality kept visible.",
        "mountain-bike",
        (
            "cycling_network",
            "suitable_unpaved",
            "track",
            "rough_surface",
            "steps",
            "mtb_rating",
        ),
    ),
    _profile(
        "road_bike",
        "racingbike",
        "cycling",
        "bicycle",
        "Road bike",
        "Paved, smoother road-cycling routes with rough terrain strongly discouraged.",
        "road-bike",
        ("cycling_network", "cycleway_like", "rough_surface", "steps", "mtb_rating"),
    ),
)
_PROFILES = {profile.id: profile for profile in ROUTING_PROFILES}


def routing_profile(profile_id: RoutingProfileId) -> RoutingProfile:
    """Resolve one already validated public profile ID."""
    return _PROFILES[profile_id]


def public_profile(profile: RoutingProfile) -> PublicRoutingProfile:
    return PublicRoutingProfile(
        id=profile.id,
        activity_kind=profile.activity_kind,
        access_mode=profile.access_mode,
        display_name=profile.display_name,
        short_description=profile.short_description,
        icon_key=profile.icon_key,
        quality_metrics=profile.allowed_quality_metrics,
        capabilities=RoutingProfileCapabilities(
            supports_auto_tour=profile.supports_auto_tour,
            supports_waypoint_route=profile.supports_waypoint_route,
            supports_loop=profile.supports_loop,
            supports_point_to_point=profile.supports_point_to_point,
            elevation_aware=profile.elevation_aware,
        ),
    )


def routing_profile_catalog(
    available_backend_profiles: frozenset[str], *, upstream_warning: bool = False
) -> RoutingProfileCatalog:
    return RoutingProfileCatalog(
        profiles=tuple(
            RoutingProfileStatus(
                profile=public_profile(profile),
                available=profile.graphhopper_profile in available_backend_profiles,
                warnings=(
                    ("routing_backend_unavailable",)
                    if upstream_warning
                    else ()
                    if profile.graphhopper_profile in available_backend_profiles
                    else ("routing_profile_not_loaded",)
                ),
            )
            for profile in ROUTING_PROFILES
        )
    )
