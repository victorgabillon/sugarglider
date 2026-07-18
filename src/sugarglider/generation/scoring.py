"""Fixed explainable PR3 scoring and deterministic ranking."""

from dataclasses import dataclass

from sugarglider.domain.generation import (
    CandidateScore,
    GeneratedCandidate,
    LoopGeometryPreference,
    NaturePreference,
)
from sugarglider.domain.models import RouteResult


@dataclass(frozen=True)
class ScoringWeights:
    distance_error: float = 10.0
    repetition: float = 3.0
    major_road: float = 2.0
    paved: float = 1.0
    unknown_surface: float = 0.25
    trail_like: float = 1.5
    hiking_network: float = 0.75


PR3_SCORING_WEIGHTS = ScoringWeights()
NATURAL_IMPROVEMENT_EPSILON = 1e-12


def score_route(
    route: RouteResult,
    target_distance_m: float,
    weights: ScoringWeights = PR3_SCORING_WEIGHTS,
) -> CandidateScore:
    """Return weighted penalties and positive reward magnitudes subtracted in total."""
    distance_error_ratio = (
        abs(route.summary.distance_m - target_distance_m) / target_distance_m
    )
    repetition_penalty = (
        weights.repetition * route.analysis.repetition.repeated_distance.share
    )
    major_road_penalty = weights.major_road * route.analysis.major_road.share
    paved_penalty = weights.paved * route.analysis.paved.share
    unknown_surface_penalty = (
        weights.unknown_surface * route.analysis.unknown_surface.share
    )
    trail_like_reward = weights.trail_like * route.analysis.trail_like.share
    hiking_network_reward = (
        weights.hiking_network * route.analysis.official_hiking_network.share
    )
    total = (
        weights.distance_error * distance_error_ratio
        + repetition_penalty
        + major_road_penalty
        + paved_penalty
        + unknown_surface_penalty
        - trail_like_reward
        - hiking_network_reward
    )
    return CandidateScore(
        total=total,
        distance_error_ratio=distance_error_ratio,
        repetition_penalty=repetition_penalty,
        major_road_penalty=major_road_penalty,
        paved_penalty=paved_penalty,
        unknown_surface_penalty=unknown_surface_penalty,
        trail_like_reward=trail_like_reward,
        hiking_network_reward=hiking_network_reward,
    )


def rank_candidates(
    candidates: tuple[GeneratedCandidate, ...],
    nature_preference: NaturePreference = "off",
    loop_geometry_preference: LoopGeometryPreference = "off",
) -> tuple[GeneratedCandidate, ...]:
    """Rank natural loops within tolerance and keep distance pressure outside it."""

    if nature_preference == "off" and loop_geometry_preference == "off":

        def ranking_key(candidate: GeneratedCandidate) -> tuple[object, ...]:
            backtrack = candidate.route.analysis.immediate_backtrack.share
            repetition = candidate.route.analysis.repetition.repeated_distance.share
            if candidate.within_tolerance:
                return (
                    0,
                    backtrack,
                    repetition,
                    candidate.score.total,
                    candidate.target_error_m,
                    candidate.signature,
                )
            return (
                1,
                candidate.score.distance_error_ratio,
                backtrack,
                repetition,
                candidate.score.total,
                candidate.target_error_m,
                candidate.signature,
            )

    else:

        def ranking_key(candidate: GeneratedCandidate) -> tuple[object, ...]:
            backtrack = candidate.route.analysis.immediate_backtrack.share
            repetition = candidate.route.analysis.repetition.repeated_distance.share
            geometry = (
                (_loop_geometry_ranking_key(candidate),)
                if loop_geometry_preference == "prefer"
                else ()
            )
            nature = (
                (_nature_ranking_key(candidate),)
                if nature_preference == "prefer"
                else ()
            )
            if candidate.within_tolerance:
                return (
                    0,
                    backtrack,
                    repetition,
                    *geometry,
                    *nature,
                    candidate.score.total,
                    candidate.target_error_m,
                    candidate.signature,
                )
            return (
                1,
                candidate.score.distance_error_ratio,
                backtrack,
                repetition,
                *geometry,
                *nature,
                candidate.score.total,
                candidate.signature,
            )

    ordered = sorted(
        candidates,
        key=ranking_key,
    )
    return tuple(
        candidate.model_copy(update={"rank": rank})
        for rank, candidate in enumerate(ordered, start=1)
    )


def rank_low_overlap_candidates(
    candidates: tuple[GeneratedCandidate, ...],
    nature_preference: NaturePreference = "off",
    loop_geometry_preference: LoopGeometryPreference = "off",
) -> tuple[GeneratedCandidate, ...]:
    """Rank tolerance first, then exact repeated distance and backtracking."""
    if nature_preference == "off" and loop_geometry_preference == "off":
        ordered = sorted(
            candidates,
            key=lambda candidate: (
                0 if candidate.within_tolerance else 1,
                candidate.route.analysis.repetition.repeated_distance.share,
                candidate.route.analysis.immediate_backtrack.share,
                candidate.score.total,
                candidate.target_error_m,
                candidate.signature,
            ),
        )
    else:

        def ranking_key(candidate: GeneratedCandidate) -> tuple[object, ...]:
            geometry = (
                (_loop_geometry_ranking_key(candidate),)
                if loop_geometry_preference == "prefer"
                else ()
            )
            nature = (
                (_nature_ranking_key(candidate),)
                if nature_preference == "prefer"
                else ()
            )
            return (
                0 if candidate.within_tolerance else 1,
                (
                    candidate.score.distance_error_ratio
                    if not candidate.within_tolerance
                    else 0.0
                ),
                candidate.route.analysis.repetition.repeated_distance.share,
                candidate.route.analysis.immediate_backtrack.share,
                *geometry,
                *nature,
                candidate.score.total,
                candidate.target_error_m,
                candidate.signature,
            )

        ordered = sorted(
            candidates,
            key=ranking_key,
        )
    return tuple(
        candidate.model_copy(update={"rank": rank})
        for rank, candidate in enumerate(ordered, start=1)
    )


def _nature_ranking_key(candidate: GeneratedCandidate) -> tuple[int, float]:
    """Sort known scores high-to-low and keep unknown distinct from numeric zero."""
    nature = candidate.route.analysis.nature
    if nature is None:
        return (1, 0.0)
    return (0, -nature.nature_score)


def _loop_geometry_ranking_key(
    candidate: GeneratedCandidate,
) -> tuple[int, float]:
    """Sort known penalties low-to-high and keep unknown distinct from zero."""
    geometry = candidate.route.analysis.loop_geometry
    if geometry is None:
        return (1, 0.0)
    return (0, geometry.penalty_breakdown.total)


def is_natural_improvement(
    refined: GeneratedCandidate,
    source: GeneratedCandidate,
    *,
    epsilon: float = NATURAL_IMPROVEMENT_EPSILON,
) -> bool:
    """Return whether refinement lowers repetition without raising backtracking."""
    refined_repetition = refined.route.analysis.repetition.repeated_distance.share
    source_repetition = source.route.analysis.repetition.repeated_distance.share
    refined_backtrack = refined.route.analysis.immediate_backtrack.share
    source_backtrack = source.route.analysis.immediate_backtrack.share
    return (
        refined_repetition < source_repetition - epsilon
        and refined_backtrack <= source_backtrack + epsilon
    )
