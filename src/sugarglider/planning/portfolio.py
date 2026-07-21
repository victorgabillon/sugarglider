"""Shared deterministic candidate deduplication, roles, diversity, and ranks."""

from collections.abc import Callable

from sugarglider.planning.result import CandidateRole, PlanCandidate

ROLE_ORDER: dict[CandidateRole, int] = {
    "harmonious": 0,
    "maximum_requested_coverage": 1,
    "smooth_low_detour": 2,
    "distance_focused": 3,
}


def build_portfolio(
    candidates: tuple[PlanCandidate, ...],
    *,
    limit: int,
    ranking_key: Callable[[PlanCandidate], tuple[object, ...]] | None = None,
) -> tuple[PlanCandidate, ...]:
    """Publish one role-aware deterministic portfolio for either planning mode."""
    if limit < 1:
        raise ValueError("portfolio limit must be positive")
    distinct: dict[str, PlanCandidate] = {}
    for candidate in candidates:
        distinct.setdefault(candidate.id, candidate)
    eligible = tuple(
        candidate
        for candidate in distinct.values()
        if candidate.diagnostics.safety_eligible
    )
    pool = eligible
    key = ranking_key or _default_key
    ordered = tuple(sorted(pool, key=key))
    if not ordered:
        return ()
    roles: dict[str, set[CandidateRole]] = {
        candidate.id: set() for candidate in ordered
    }
    roles[ordered[0].id].add("harmonious")
    maximum_coverage = max(
        candidate.diagnostics.requested_stop_count for candidate in ordered
    )
    if maximum_coverage > 0:
        for candidate in ordered:
            if candidate.diagnostics.requested_stop_count == maximum_coverage:
                roles[candidate.id].add("maximum_requested_coverage")
    smooth = min(
        ordered,
        key=lambda candidate: (
            candidate.diagnostics.immediate_backtracking_m,
            candidate.diagnostics.repeated_distance_m,
            candidate.id,
        ),
    )
    roles[smooth.id].add("smooth_low_detour")
    distance = min(
        ordered,
        key=lambda candidate: (candidate.diagnostics.target_error_m, candidate.id),
    )
    roles[distance.id].add("distance_focused")

    selected: list[PlanCandidate] = []

    def retain(candidate: PlanCandidate) -> None:
        retained_ids = {value.id for value in selected}
        if candidate.id not in retained_ids and len(selected) < limit:
            selected.append(candidate)

    retain(ordered[0])
    for candidate in ordered:
        if candidate.diagnostics.details.get("portfolio_reservation") not in {
            None,
            "none",
        }:
            retain(candidate)
    for role in (
        "maximum_requested_coverage",
        "smooth_low_detour",
        "distance_focused",
    ):
        representative = next(
            (candidate for candidate in ordered if role in roles[candidate.id]), None
        )
        if representative is not None:
            retain(representative)
    for candidate in ordered:
        retain(candidate)
    return tuple(
        candidate.model_copy(
            update={
                "rank": rank,
                "roles": tuple(sorted(roles[candidate.id], key=ROLE_ORDER.__getitem__)),
            }
        )
        for rank, candidate in enumerate(selected, start=1)
    )


def _default_key(candidate: PlanCandidate) -> tuple[object, ...]:
    return (
        0 if candidate.diagnostics.within_tolerance else 1,
        candidate.diagnostics.target_error_m,
        candidate.diagnostics.immediate_backtracking_m,
        candidate.diagnostics.repeated_distance_m,
        candidate.id,
    )
