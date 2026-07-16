"""Fixed explainable PR3 scoring and deterministic ranking."""

from dataclasses import dataclass

from sugarglider.domain.generation import CandidateScore, GeneratedCandidate
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
) -> tuple[GeneratedCandidate, ...]:
    """Rank tolerance first, then score, absolute error, and stable signature."""
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            0 if candidate.within_tolerance else 1,
            candidate.score.total,
            candidate.target_error_m,
            candidate.signature,
        ),
    )
    return tuple(
        candidate.model_copy(update={"rank": rank})
        for rank, candidate in enumerate(ordered, start=1)
    )
