"""Validate and summarize a canonical plan result for selected-candidate export."""

from collections.abc import Mapping, Sequence


class PlanSummaryError(ValueError):
    """The generated response is not the canonical result shape an export needs."""


def prepare_candidate_request(
    document: object,
) -> tuple[str, dict[str, object]]:
    result = _mapping(document, "plan result")
    if result.get("schema_version") != 1:
        raise PlanSummaryError("plan result must use schema_version 1")
    kind = _string(result.get("kind"), "plan result kind")
    candidates = _sequence(result.get("candidates"), "plan result candidates")
    if not candidates:
        raise PlanSummaryError("canonical plan returned no candidate")
    candidate = _mapping(candidates[0], "rank-one candidate")
    if candidate.get("rank") != 1:
        raise PlanSummaryError("first canonical candidate must have rank 1")
    candidate_id = _string(candidate.get("id"), "candidate id")
    roles = tuple(
        _string(value, "candidate role")
        for value in _sequence(candidate.get("roles"), "candidate roles")
    )
    route = _mapping(candidate.get("route"), "candidate route")
    summary = _mapping(route.get("summary"), "route summary")
    distance_m = _number(summary.get("distance_m"), "route distance")
    geometry = _sequence(route.get("geometry"), "route geometry")
    if len(geometry) < 2:
        raise PlanSummaryError(
            "candidate route geometry must contain at least 2 points"
        )
    analysis = _mapping(route.get("analysis"), "route analysis")
    spurs = _mapping(analysis.get("spurs"), "route spur analysis")
    spur_count = _integer(spurs.get("spur_count"), "spur count")
    spur_repeated_m = _number(
        spurs.get("total_repeated_distance_m"),
        "spur repeated distance",
    )
    diagnostics = _mapping(candidate.get("diagnostics"), "candidate diagnostics")
    if diagnostics.get("safety_eligible") is not True:
        raise PlanSummaryError("rank-one candidate is not safety eligible")
    details = _mapping(diagnostics.get("details"), "candidate diagnostic details")
    construction = _string(
        details.get("construction"),
        "candidate construction",
    )
    reached = len(_sequence(candidate.get("reached_stops"), "reached stops"))
    approximated = len(
        _sequence(candidate.get("approximated_stops"), "approximated stops")
    )
    dropped = len(_sequence(candidate.get("dropped_stops"), "dropped stops"))
    values = [
        f"{kind} candidate {candidate_id}: {distance_m:.1f} m",
        f"roles={','.join(roles) or 'none'}",
        f"outcomes={reached} reached/{approximated} approximated/{dropped} dropped",
        f"spurs={spur_count}; spur_repeated={spur_repeated_m:.1f} m",
        f"construction={construction}",
    ]
    if construction == "edge_aware_global_optimization":
        opposite_improvement = _detail_number(
            details.get("opposite_direction_improvement_m"),
            "global-optimization opposite-direction improvement",
        )
        repeated_improvement = _detail_number(
            details.get("repeated_distance_improvement_m"),
            "global-optimization repeated-distance improvement",
        )
        backtracking_improvement = _detail_number(
            details.get("backtracking_improvement_m"),
            "global-optimization backtracking improvement",
        )
        values.append(
            "global_improvement="
            f"{opposite_improvement:.1f} m opposite-direction/"
            f"{repeated_improvement:.1f} m repeated/"
            f"{backtracking_improvement:.1f} m immediate backtracking"
        )
    search_diagnostics = result.get("search_diagnostics")
    if isinstance(search_diagnostics, Mapping):
        search_details = search_diagnostics.get("details")
        if isinstance(search_details, Mapping):
            optimization = search_details.get("global_optimization")
            if isinstance(optimization, Mapping):
                sources = _integer(
                    optimization.get("source_states"),
                    "global-optimization sources",
                )
                accepted = _integer(
                    optimization.get("accepted_moves"),
                    "global-optimization accepted moves",
                )
                iterations = _integer(
                    optimization.get("iterations"),
                    "global-optimization iterations",
                )
                published = _integer(
                    optimization.get("published_candidates"),
                    "global-optimization published candidates",
                )
                evaluations = _integer(
                    optimization.get("complete_evaluations"),
                    "global-optimization complete evaluations",
                )
                exhausted = _boolean(
                    optimization.get("budget_exhausted"),
                    "global-optimization budget status",
                )
                values.append(
                    "global_optimization="
                    f"{sources} sources/"
                    f"{iterations} iterations/"
                    f"{accepted} accepted moves/"
                    f"{evaluations} complete evaluations/"
                    f"{published} published/"
                    f" budget_exhausted={exhausted}"
                )
    return "; ".join(values), {
        "schema_version": 1,
        "candidate": dict(candidate),
    }


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PlanSummaryError(f"{name} must be an object")
    return value


def _sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PlanSummaryError(f"{name} must be an array")
    return value


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise PlanSummaryError(f"{name} must be a non-empty string")
    return value


def _number(value: object, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise PlanSummaryError(f"{name} must be numeric")
    return float(value)


def _integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PlanSummaryError(f"{name} must be a non-negative integer")
    return value


def _boolean(value: object, name: str) -> str:
    if not isinstance(value, bool):
        raise PlanSummaryError(f"{name} must be boolean")
    return str(value).lower()


def _detail_number(value: object, name: str) -> float:
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            pass
    return _number(value, name)
