"""Internal search ordering before shared portfolio publication."""

# mypy: disable-error-code="attr-defined"

from sugarglider.planning.auto_tour.candidate_models import (
    AutoTourCandidate,
)
from sugarglider.planning.auto_tour.models import (
    AutoTourSearchRequest,
    RequestedPlaceFailureReason,
)
from sugarglider.planning.auto_tour.ranking import (
    maximum_auto_tour_distance_m,
)
from sugarglider.planning.auto_tour.search_support import (
    _maximum_distance,
)


def _maximum_rejection_reason(
    request: AutoTourSearchRequest,
) -> RequestedPlaceFailureReason:
    if request.maximum_distance_m is not None:
        return "requested_place_user_maximum_rejected"
    if request.distance_priority == "flexible":
        return "requested_place_server_maximum_rejected"
    return "requested_place_lower_utility_subset"


def _open_tour_key(
    candidate: AutoTourCandidate, request: AutoTourSearchRequest
) -> tuple[object, ...]:
    """Rank endpoint-valid open paths without applying loop-only shape gates."""
    severe_backtracking = (
        candidate.route.analysis.immediate_backtrack.distance_m > 1_000.0
        and candidate.route.analysis.immediate_backtrack.share > 0.10
    )
    if request.distance_priority == "strict":
        return (
            0 if candidate.within_tolerance else 1,
            candidate.target_error_m,
            0
            if candidate.route.summary.distance_m <= _maximum_distance(request)
            else 1,
            1 if severe_backtracking else 0,
            -candidate.selected_must_visit_count,
            -candidate.selected_preferred_place_count,
            candidate.signature,
        )
    nature = candidate.route.analysis.nature
    net_requested_value = (
        candidate.selected_must_visit_count * 5_000.0
        + candidate.selected_preferred_place_count * 1_500.0
        - candidate.poi_excursion_penalty_m_equivalent
    )
    non_poi_backtracking_share = (
        candidate.non_poi_backtracking_m / candidate.route.summary.distance_m
        if candidate.route.summary.distance_m > 0
        else 0.0
    )
    return (
        0 if candidate.route.summary.distance_m <= _maximum_distance(request) else 1,
        1 if severe_backtracking else 0,
        -net_requested_value,
        non_poi_backtracking_share,
        candidate.reverse_progress_share
        if candidate.reverse_progress_share is not None
        else 1.0,
        candidate.route.analysis.repetition.repeated_distance.share,
        candidate.near_parallel_corridor_share
        if candidate.near_parallel_corridor_share is not None
        else 1.0,
        -candidate.total_poi_reward,
        (0, -nature.nature_score) if nature is not None else (1, 0.0),
        candidate.soft_distance_penalty,
        candidate.signature,
    )


def _open_candidate_portfolio(
    candidates: tuple[AutoTourCandidate, ...],
    *,
    request: AutoTourSearchRequest,
    control: AutoTourCandidate,
) -> tuple[AutoTourCandidate, ...]:
    """Reserve coverage, near-target, and direct-control open-route roles."""
    ordered = tuple(
        sorted(candidates, key=lambda value: _open_tour_key(value, request))
    )
    if request.distance_priority != "flexible" or request.candidate_count == 1:
        return ordered[: request.candidate_count]
    selected: list[AutoTourCandidate] = []

    def retain(candidate: AutoTourCandidate | None) -> None:
        if candidate is None or candidate.signature in {
            value.signature for value in selected
        }:
            return
        selected.append(candidate)

    retain(ordered[0] if ordered else None)
    target_maximum = maximum_auto_tour_distance_m(
        request.target_distance_m,
        request.tolerance_m,
        priority="balanced",
        requested_maximum_distance_m=request.maximum_distance_m,
    )
    near_target = tuple(
        candidate
        for candidate in candidates
        if candidate.route.summary.distance_m <= target_maximum
    )
    retain(
        min(
            near_target,
            key=lambda candidate: (
                -candidate.selected_must_visit_count,
                -candidate.selected_preferred_place_count,
                candidate.target_error_m,
                _open_tour_key(candidate, request),
            ),
            default=None,
        )
    )
    retain(control)
    for candidate in ordered:
        if len(selected) >= request.candidate_count:
            break
        retain(candidate)
    return tuple(selected[: request.candidate_count])
