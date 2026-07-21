"""Routing-profile identities and immutable backend capabilities."""

from typing import Literal

from pydantic import ConfigDict

from sugarglider.domain.models import ImmutableModel

type RoutingProfileId = Literal["hike"]
type GraphHopperProfile = Literal["hike"]
type ActivityKind = Literal["walking"]
type QualityMetricId = Literal[
    "distance",
    "repetition",
    "immediate_backtracking",
    "surface",
    "trail_like",
    "hiking_network",
    "nature",
    "loop_geometry",
]


class RoutingProfile(ImmutableModel):
    """One public activity mapped explicitly to a configured routing backend."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: RoutingProfileId
    graphhopper_profile: GraphHopperProfile
    activity_kind: ActivityKind
    allowed_quality_metrics: tuple[QualityMetricId, ...]


HIKE_PROFILE = RoutingProfile(
    id="hike",
    graphhopper_profile="hike",
    activity_kind="walking",
    allowed_quality_metrics=(
        "distance",
        "repetition",
        "immediate_backtracking",
        "surface",
        "trail_like",
        "hiking_network",
        "nature",
        "loop_geometry",
    ),
)

_PROFILES: dict[RoutingProfileId, RoutingProfile] = {"hike": HIKE_PROFILE}


def routing_profile(profile_id: RoutingProfileId) -> RoutingProfile:
    """Resolve a validated public ID without leaking backend strings to callers."""
    return _PROFILES[profile_id]
