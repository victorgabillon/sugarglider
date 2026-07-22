"""Immutable activity-specific route-quality policies shared by both planners."""

from dataclasses import dataclass

from sugarglider.domain.analysis import (
    CyclingRouteQuality,
    RunningRouteQuality,
    WalkingRouteQuality,
)
from sugarglider.domain.models import RouteResult
from sugarglider.planning.profiles import RoutingProfileId


@dataclass(frozen=True)
class ProfileQualityPolicy:
    profile_id: RoutingProfileId
    rewards: tuple[tuple[str, float], ...]
    penalties: tuple[tuple[str, float], ...]
    severe_gates: tuple[tuple[str, float], ...]
    metric_order: tuple[str, ...]


PROFILE_QUALITY_POLICIES: tuple[ProfileQualityPolicy, ...] = (
    ProfileQualityPolicy(
        "trail_run",
        (("runnable_surface", 1.8), ("trail_like", 1.0)),
        (
            ("technical_trail", 3.0),
            ("steps", 8.0),
            ("poor_smoothness", 4.0),
            ("major_road", 3.0),
            ("unknown_surface", 0.5),
        ),
        (("steps", 0.08), ("technical_trail", 0.20)),
        (
            "runnable_surface",
            "trail_like",
            "technical_trail",
            "steps",
            "poor_smoothness",
            "major_road",
        ),
    ),
    ProfileQualityPolicy(
        "hike",
        (("trail_like", 1.5), ("official_hiking_network", 0.75)),
        (
            ("major_road", 2.0),
            ("paved", 1.0),
            ("unknown_surface", 0.25),
        ),
        (),
        (
            "trail_like",
            "official_hiking_network",
            "technical_hiking",
            "steps",
            "poor_smoothness",
        ),
    ),
    ProfileQualityPolicy(
        "city_bike",
        (("cycling_network", 1.6), ("cycleway_like", 1.5), ("paved", 0.8)),
        (
            ("rough_surface", 5.0),
            ("track", 2.0),
            ("steps", 12.0),
            ("major_road", 4.0),
            ("unknown_surface", 1.5),
        ),
        (("steps", 0.01), ("rough_surface", 0.20)),
        (
            "cycling_network",
            "cycleway_like",
            "paved",
            "rough_surface",
            "steps",
            "major_road",
        ),
    ),
    ProfileQualityPolicy(
        "gravel_bike",
        (("cycling_network", 1.0), ("suitable_unpaved", 1.8), ("track", 1.0)),
        (
            ("rough_surface", 2.5),
            ("steps", 12.0),
            ("major_road", 3.0),
            ("extreme_mtb", 3.0),
            ("unknown_surface", 0.75),
        ),
        (("steps", 0.01), ("extreme_mtb", 0.15)),
        (
            "suitable_unpaved",
            "track",
            "cycling_network",
            "rough_surface",
            "mtb_rating",
            "steps",
            "major_road",
        ),
    ),
    ProfileQualityPolicy(
        "mountain_bike",
        (("suitable_unpaved", 1.2), ("track", 1.6), ("cycling_network", 0.6)),
        (
            ("steps", 8.0),
            ("major_road", 3.0),
            ("extreme_mtb", 1.5),
            ("unknown_surface", 0.5),
        ),
        (("steps", 0.03), ("extreme_mtb", 0.30)),
        (
            "track",
            "suitable_unpaved",
            "cycling_network",
            "mtb_rating",
            "steps",
            "major_road",
        ),
    ),
    ProfileQualityPolicy(
        "road_bike",
        (("paved", 2.0), ("cycling_network", 0.8), ("cycleway_like", 0.5)),
        (
            ("suitable_unpaved", 3.0),
            ("rough_surface", 8.0),
            ("track", 5.0),
            ("steps", 15.0),
            ("major_road", 2.5),
            ("extreme_mtb", 5.0),
            ("unknown_surface", 5.0),
        ),
        (("steps", 0.005), ("rough_surface", 0.08), ("track", 0.15)),
        (
            "paved",
            "cycling_network",
            "cycleway_like",
            "rough_surface",
            "track",
            "steps",
            "major_road",
        ),
    ),
)
_POLICIES = {policy.profile_id: policy for policy in PROFILE_QUALITY_POLICIES}


def profile_quality_policy(profile_id: RoutingProfileId) -> ProfileQualityPolicy:
    return _POLICIES[profile_id]


def profile_aware_drop_reason(profile_id: RoutingProfileId, reason: str) -> str:
    """Make routeability failures explicit for non-walking profile decisions."""
    if profile_id == "hike":
        return reason
    return {
        "graph_unreachable": "profile_unreachable",
        "approach_snap_too_far": "profile_snap_too_far",
        "no_meaningful_approach": "no_profile_compatible_approach",
    }.get(reason, reason)


def profile_quality_components(
    route: RouteResult,
) -> tuple[float, dict[str, float], bool]:
    """Return penalty-minus-reward, explainable components, and severe gate."""
    policy = profile_quality_policy(route.routing_profile)
    values = _quality_shares(route)
    components: dict[str, float] = {}
    total = 0.0
    for metric, weight in policy.penalties:
        value = values.get(metric, 0.0)
        component = weight * value
        components[f"{metric}_penalty"] = component
        total += component
    for metric, weight in policy.rewards:
        value = values.get(metric, 0.0)
        component = weight * value
        components[f"{metric}_reward"] = component
        total -= component
    severe = any(
        values.get(metric, 0.0) > limit for metric, limit in policy.severe_gates
    )
    return total, components, severe


def _quality_shares(route: RouteResult) -> dict[str, float]:
    analysis = route.analysis
    quality = analysis.activity_quality
    values = {
        "paved": analysis.paved.share,
        "unpaved": analysis.unpaved.share,
        "unknown_surface": analysis.unknown_surface.share,
        "major_road": analysis.major_road.share,
    }
    if isinstance(quality, WalkingRouteQuality):
        values.update(
            trail_like=quality.trail_like.share,
            official_hiking_network=quality.official_hiking_network.share,
            technical_hiking=quality.technical_hiking.share,
            steps=quality.steps.share,
            poor_smoothness=quality.poor_smoothness.share,
        )
    elif isinstance(quality, RunningRouteQuality):
        values.update(
            runnable_surface=quality.runnable_surface.share,
            trail_like=quality.trail_like.share,
            technical_trail=quality.technical_trail.share,
            steps=quality.steps.share,
            poor_smoothness=quality.poor_smoothness.share,
            major_road=quality.major_road.share,
        )
    elif isinstance(quality, CyclingRouteQuality):
        extreme_mtb = sum(
            bucket.share
            for bucket in quality.mtb_rating.buckets
            if (
                isinstance(bucket.value, (int, float))
                and not isinstance(bucket.value, bool)
                and bucket.value >= 4
            )
        )
        values.update(
            cycling_network=quality.cycling_network.share,
            cycleway_like=quality.cycleway_like.share,
            suitable_unpaved=quality.suitable_unpaved.share,
            track=quality.track.share,
            rough_surface=quality.rough_surface.share,
            steps=quality.steps.share,
            major_road=quality.major_road.share,
            extreme_mtb=extreme_mtb,
        )
    return values
