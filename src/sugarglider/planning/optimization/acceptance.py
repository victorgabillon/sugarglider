"""Structural and deterministic annealing acceptance for feasible states."""

from __future__ import annotations

from math import exp
from random import Random

from sugarglider.planning.optimization.models import (
    GlobalOptimizationSettings,
    TourObjective,
)
from sugarglider.planning.optimization.objective import (
    acceptance_energy,
    objective_improves,
)


def structurally_qualifies(
    source: TourObjective,
    candidate: TourObjective,
    settings: GlobalOptimizationSettings,
) -> bool:
    """Apply the public 500 m / min(5%, 2 km) structural acceptance signal."""
    if not candidate.hard_feasible:
        return False
    if (
        candidate.reached_requested < source.reached_requested
        or candidate.approximated_requested > source.approximated_requested
        or candidate.dropped_requested > source.dropped_requested
    ):
        return False
    improvement = max(
        source.opposite_direction_reuse_m - candidate.opposite_direction_reuse_m,
        source.total_repeated_distance_m - candidate.total_repeated_distance_m,
        source.immediate_backtracking_m - candidate.immediate_backtracking_m,
    )
    maximum_extra = min(
        source.distance_m * settings.maximum_extra_distance_share,
        settings.maximum_extra_distance_m,
    )
    return (
        improvement + 1e-6 >= settings.minimum_structural_improvement_m
        and candidate.distance_m - source.distance_m <= maximum_extra + 1e-6
    )


def accept_state(
    current: TourObjective,
    proposed: TourObjective,
    *,
    iteration: int,
    settings: GlobalOptimizationSettings,
    rng: Random,
) -> bool:
    """Use deterministic-seed simulated annealing over the typed objective."""
    if not proposed.hard_feasible:
        return False
    if objective_improves(proposed, current):
        return True
    progress = min(1.0, iteration / settings.maximum_iterations)
    temperature = max(1.0, 50_000.0 * (1.0 - progress))
    delta = acceptance_energy(proposed) - acceptance_energy(current)
    if delta <= 0:
        return True
    probability = exp(-min(delta / temperature, 700.0))
    return rng.random() < probability
