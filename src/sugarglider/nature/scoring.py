"""Explainable bounded score for mapped environmental context."""

from dataclasses import dataclass

from sugarglider.domain.analysis import (
    NatureScoreBreakdown,
    NatureWeightedComponent,
)


@dataclass(frozen=True)
class NatureScoringWeights:
    woodland: float = 1.00
    open_natural: float = 0.85
    agriculture: float = 0.30
    park_or_protected: float = 0.20
    near_water: float = 0.15
    urban: float = 1.00
    unknown: float = 0.10


DEFAULT_NATURE_SCORING_WEIGHTS = NatureScoringWeights()
NATURE_SCORE_BASE = 50.0
NATURE_SCORE_SCALE = 50.0


def score_nature(
    *,
    woodland_share: float,
    open_natural_share: float,
    agriculture_share: float,
    park_or_protected_share: float,
    near_water_share: float,
    urban_share: float,
    unknown_share: float,
    weights: NatureScoringWeights = DEFAULT_NATURE_SCORING_WEIGHTS,
) -> NatureScoreBreakdown:
    """Score mapped context from a neutral 50, exposing every signed component."""

    def reward(weight: float, share: float) -> NatureWeightedComponent:
        return NatureWeightedComponent(
            weight=weight,
            share=share,
            points=NATURE_SCORE_SCALE * weight * share,
        )

    def penalty(weight: float, share: float) -> NatureWeightedComponent:
        return NatureWeightedComponent(
            weight=weight,
            share=share,
            points=-NATURE_SCORE_SCALE * weight * share,
        )

    woodland = reward(weights.woodland, woodland_share)
    open_natural = reward(weights.open_natural, open_natural_share)
    agriculture = reward(weights.agriculture, agriculture_share)
    park = reward(weights.park_or_protected, park_or_protected_share)
    near_water = reward(weights.near_water, near_water_share)
    urban = penalty(weights.urban, urban_share)
    unknown = penalty(weights.unknown, unknown_share)
    components = (
        woodland,
        open_natural,
        agriculture,
        park,
        near_water,
        urban,
        unknown,
    )
    raw_score = NATURE_SCORE_BASE + sum(component.points for component in components)
    final_score = min(100.0, max(0.0, raw_score))
    return NatureScoreBreakdown(
        base_score=NATURE_SCORE_BASE,
        woodland_reward=woodland,
        open_natural_reward=open_natural,
        agriculture_reward=agriculture,
        park_or_protected_reward=park,
        near_water_reward=near_water,
        urban_penalty=urban,
        unknown_penalty=unknown,
        raw_score=raw_score,
        final_score=final_score,
    )
