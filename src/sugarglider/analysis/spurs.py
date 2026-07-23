"""Deterministic edge-based out-and-back excursion diagnostics."""

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from typing import Literal

from shapely.geometry import LineString, Point

from sugarglider.analysis.projection import LocalMetricProjection
from sugarglider.analysis.route import (
    ProjectedGeometryEdge,
    haversine_distance_m,
    known_edge_id,
    project_geometry_edges,
)
from sugarglider.domain.analysis import (
    RouteSpur,
    RouteSpurAnalysis,
    RouteSpurConfidence,
    RouteSpurReasonCode,
)
from sugarglider.domain.models import GeoJsonPosition, RouteResult

# Progress values come from the same normalized metric edge prefix. This epsilon is
# used only to absorb division noise at the exact normalized bounds, never to conceal
# overlap between route-index intervals.
_PROGRESS_EPSILON = 1e-12


@dataclass(frozen=True)
class SpurDetectionSettings:
    """Conservative immutable thresholds for structural spur evidence."""

    minimum_reversed_edge_distance_m: float = 100.0
    maximum_turnaround_connector_distance_m: float = 100.0
    maximum_branch_coordinate_gap_m: float = 30.0
    minimum_edge_id_coverage: float = 0.90

    def __post_init__(self) -> None:
        distances = (
            self.minimum_reversed_edge_distance_m,
            self.maximum_turnaround_connector_distance_m,
            self.maximum_branch_coordinate_gap_m,
        )
        if any(not isfinite(value) or value < 0 for value in distances):
            raise ValueError("spur distance thresholds must be finite and non-negative")
        if not isfinite(self.minimum_edge_id_coverage) or not (
            0 <= self.minimum_edge_id_coverage <= 1
        ):
            raise ValueError(
                "spur edge-ID coverage threshold must be between zero and one"
            )


@dataclass(frozen=True)
class SpurTraversalAnchor:
    """Planning-neutral deliberate anchor input for stop attribution."""

    id: str
    name: str
    route_progress: float

    def __post_init__(self) -> None:
        if not self.id or not self.name:
            raise ValueError("spur traversal anchors require stable identity and name")
        if not isfinite(self.route_progress) or not 0 <= self.route_progress <= 1:
            raise ValueError(
                "spur traversal anchor progress must be finite and normalized"
            )


@dataclass(frozen=True)
class _DirectedRun:
    edge_id: int
    edge_indices: tuple[int, ...]
    start: GeoJsonPosition
    end: GeoJsonPosition
    distance_m: float
    start_distance_m: float
    end_distance_m: float
    component: int


@dataclass(frozen=True)
class _SpurCandidate:
    start_run: int
    turnaround_start_run: int
    turnaround_end_run: int
    end_run: int
    outbound_runs: frozenset[int]
    return_runs: frozenset[int]


@dataclass(frozen=True)
class _CandidateMetrics:
    start_distance_m: float
    turnaround_distance_m: float
    end_distance_m: float
    outbound_distance_m: float
    return_distance_m: float
    connector_distance_m: float
    total_distance_m: float
    branch_gap_m: float
    confidence: RouteSpurConfidence


@dataclass(frozen=True)
class _NormalizationResult:
    candidates: tuple[_SpurCandidate, ...]
    warnings: tuple[str, ...]


def detect_route_spurs(
    route: RouteResult,
    deliberate_anchors: tuple[SpurTraversalAnchor, ...] = (),
    *,
    topology: Literal["loop", "point_to_point"] | None = None,
    settings: SpurDetectionSettings | None = None,
) -> RouteSpurAnalysis:
    """Detect maximal reversed-edge excursions without routing or ranking effects."""
    resolved = settings or SpurDetectionSettings()
    projection = project_geometry_edges(
        geometry=route.geometry,
        route_distance_m=route.summary.distance_m,
        path_details=route.path_details,
    )
    edges = projection.edges
    coverage = (
        sum(edge.distance_m for edge in edges if known_edge_id(edge) is not None)
        / route.summary.distance_m
        if route.summary.distance_m > 0
        else 0.0
    )
    warnings: set[str] = set()
    if coverage < resolved.minimum_edge_id_coverage:
        warnings.add("spur_edge_id_coverage_insufficient")
    runs = _directed_runs(edges)
    candidates = _find_candidates(runs, resolved)
    normalization = _normalize_candidates(candidates, runs, resolved, coverage)
    warnings.update(normalization.warnings)
    _assert_candidate_portfolio(normalization.candidates, runs)
    spurs = tuple(
        _public_spur(
            candidate,
            runs,
            edges,
            route.summary.distance_m,
            deliberate_anchors,
            coverage,
            topology,
            resolved,
        )
        for candidate in normalization.candidates
    )
    _assert_public_spur_portfolio(spurs)
    return RouteSpurAnalysis(
        spurs=spurs,
        spur_count=len(spurs),
        total_excursion_distance_m=sum(
            spur.total_excursion_distance_m for spur in spurs
        ),
        total_repeated_distance_m=sum(spur.repeated_distance_m for spur in spurs),
        longest_spur_distance_m=max(
            (spur.total_excursion_distance_m for spur in spurs), default=0.0
        ),
        warnings=tuple(sorted(warnings)),
    )


def spur_interval_geometry(spur: RouteSpur) -> tuple[GeoJsonPosition, ...]:
    """Return the exact routed geometry interval retained for map and PR20 use."""
    return spur.geometry


def spur_repair_priority(spur: RouteSpur) -> tuple[float, float, float, str]:
    """Return a deterministic future-repair order without affecting PR19 ranking."""
    return (
        -spur.repeated_distance_m,
        -spur.total_excursion_distance_m,
        spur.start_progress,
        spur.id,
    )


def _directed_runs(
    edges: tuple[ProjectedGeometryEdge, ...],
) -> tuple[_DirectedRun, ...]:
    runs: list[_DirectedRun] = []
    current_id: int | None = None
    current_indices: list[int] = []
    previous: ProjectedGeometryEdge | None = None
    component = 0
    edge_prefix = _edge_prefix(edges)

    def finish() -> None:
        nonlocal current_id, current_indices
        if current_id is None or not current_indices:
            return
        selected = tuple(edges[index] for index in current_indices)
        runs.append(
            _DirectedRun(
                edge_id=current_id,
                edge_indices=tuple(current_indices),
                start=selected[0].start,
                end=selected[-1].end,
                distance_m=sum(edge.distance_m for edge in selected),
                start_distance_m=edge_prefix[current_indices[0]],
                end_distance_m=edge_prefix[current_indices[-1] + 1],
                component=component,
            )
        )
        current_id = None
        current_indices = []

    for index, edge in enumerate(edges):
        edge_id = known_edge_id(edge)
        if edge_id is None:
            finish()
            previous = None
            component += 1
            continue
        reverses_previous = (
            previous is not None
            and previous.start == edge.end
            and previous.end == edge.start
        )
        if current_id != edge_id or reverses_previous:
            finish()
            current_id = edge_id
        current_indices.append(index)
        previous = edge
    finish()
    return tuple(runs)


def _find_candidates(
    runs: tuple[_DirectedRun, ...], settings: SpurDetectionSettings
) -> tuple[_SpurCandidate, ...]:
    positions: dict[int, list[int]] = {}
    found: dict[tuple[int, int], _SpurCandidate] = {}
    for right, run in enumerate(runs):
        prior = positions.setdefault(run.edge_id, [])
        for left in reversed(prior):
            if runs[left].component != run.component:
                break
            connector_distance = run.start_distance_m - runs[left].end_distance_m
            if connector_distance > settings.maximum_turnaround_connector_distance_m:
                break
            if not _runs_reverse(runs[left], run, settings):
                continue
            inner_left = left
            inner_right = right
            outer_left = left
            outer_right = right
            while (
                outer_left > 0
                and outer_right + 1 < len(runs)
                and _runs_reverse(runs[outer_left - 1], runs[outer_right + 1], settings)
            ):
                outer_left -= 1
                outer_right += 1
            outbound = frozenset(range(outer_left, inner_left + 1))
            returning = frozenset(range(inner_right, outer_right + 1))
            reversed_distance = sum(runs[index].distance_m for index in returning)
            if reversed_distance < settings.minimum_reversed_edge_distance_m:
                continue
            found[(outer_left, outer_right)] = _SpurCandidate(
                start_run=outer_left,
                turnaround_start_run=inner_left,
                turnaround_end_run=inner_right,
                end_run=outer_right,
                outbound_runs=outbound,
                return_runs=returning,
            )
        prior.append(right)
    return tuple(
        found[key] for key in sorted(found, key=lambda value: (value[0], -value[1]))
    )


def _merge_candidates(
    candidates: tuple[_SpurCandidate, ...],
    runs: tuple[_DirectedRun, ...],
) -> tuple[_SpurCandidate, ...]:
    """Coalesce only evidence that demonstrably describes one excursion."""
    unique = {
        _candidate_signature(candidate, runs): candidate for candidate in candidates
    }
    pending = tuple(
        sorted(
            unique.values(),
            key=lambda candidate: _candidate_route_order(candidate, runs),
        )
    )
    while pending:
        groups = _merge_groups(pending, runs)
        merged = tuple(
            sorted(
                (_combine_candidate_group(group, runs) for group in groups),
                key=lambda candidate: _candidate_route_order(candidate, runs),
            )
        )
        if tuple(
            _candidate_signature(candidate, runs) for candidate in merged
        ) == tuple(_candidate_signature(candidate, runs) for candidate in pending):
            return merged
        pending = merged
    return ()


def _normalize_candidates(
    candidates: tuple[_SpurCandidate, ...],
    runs: tuple[_DirectedRun, ...],
    settings: SpurDetectionSettings,
    coverage: float,
) -> _NormalizationResult:
    warnings: set[str] = set()
    valid = tuple(
        candidate
        for candidate in candidates
        if _candidate_is_valid(candidate, runs, settings)
    )
    if len(valid) != len(candidates):
        warnings.add("spur_evidence_invalid")
    coalesced = _merge_candidates(valid, runs)
    selected = _maximum_value_non_overlapping_portfolio(
        coalesced, runs, coverage, settings
    )
    if len(selected) != len(coalesced):
        warnings.add("overlapping_spur_evidence_pruned")
    return _NormalizationResult(
        candidates=tuple(
            sorted(
                selected,
                key=lambda candidate: _candidate_route_order(candidate, runs),
            )
        ),
        warnings=tuple(sorted(warnings)),
    )


def _merge_groups(
    candidates: tuple[_SpurCandidate, ...],
    runs: tuple[_DirectedRun, ...],
) -> tuple[tuple[_SpurCandidate, ...], ...]:
    parents = list(range(len(candidates)))

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = root(left)
        right_root = root(right)
        if left_root != right_root:
            parents[max(left_root, right_root)] = min(left_root, right_root)

    for left_index, left in enumerate(candidates):
        for right_index in range(left_index + 1, len(candidates)):
            right = candidates[right_index]
            if _candidates_describe_one_excursion(left, right, runs):
                union(left_index, right_index)
    grouped: dict[int, list[_SpurCandidate]] = {}
    for index, candidate in enumerate(candidates):
        grouped.setdefault(root(index), []).append(candidate)
    return tuple(
        tuple(
            sorted(
                group,
                key=lambda candidate: _candidate_route_order(candidate, runs),
            )
        )
        for _, group in sorted(grouped.items())
    )


def _candidates_describe_one_excursion(
    left: _SpurCandidate,
    right: _SpurCandidate,
    runs: tuple[_DirectedRun, ...],
) -> bool:
    return (
        _candidates_overlap(left, right, runs)
        and bool(left.outbound_runs & right.outbound_runs)
        and bool(left.return_runs & right.return_runs)
    )


def _combine_candidate_group(
    candidates: tuple[_SpurCandidate, ...],
    runs: tuple[_DirectedRun, ...],
) -> _SpurCandidate:
    if len(candidates) == 1:
        return candidates[0]
    outbound = frozenset(
        run_index for candidate in candidates for run_index in candidate.outbound_runs
    )
    returning = frozenset(
        run_index for candidate in candidates for run_index in candidate.return_runs
    )
    if outbound and returning and max(outbound) < min(returning):
        turnaround_start = max(outbound)
        turnaround_end = min(returning)
    else:
        dominant = min(
            candidates,
            key=lambda candidate: (
                -_candidate_repeated_distance(candidate, runs),
                -_candidate_excursion_distance(candidate, runs),
                _candidate_signature(candidate, runs),
            ),
        )
        turnaround_start = dominant.turnaround_start_run
        turnaround_end = dominant.turnaround_end_run
    return _SpurCandidate(
        start_run=min(candidate.start_run for candidate in candidates),
        turnaround_start_run=turnaround_start,
        turnaround_end_run=turnaround_end,
        end_run=max(candidate.end_run for candidate in candidates),
        outbound_runs=outbound,
        return_runs=returning,
    )


def _maximum_value_non_overlapping_portfolio(
    candidates: tuple[_SpurCandidate, ...],
    runs: tuple[_DirectedRun, ...],
    coverage: float,
    settings: SpurDetectionSettings,
) -> tuple[_SpurCandidate, ...]:
    ordered = tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                _candidate_end_edge(candidate, runs),
                _candidate_start_edge(candidate, runs),
                _candidate_signature(candidate, runs),
            ),
        )
    )
    portfolios: list[tuple[_SpurCandidate, ...]] = [()]
    for index, candidate in enumerate(ordered):
        compatible_count = 0
        for prior_index in range(index - 1, -1, -1):
            if _candidate_end_edge(ordered[prior_index], runs) < _candidate_start_edge(
                candidate, runs
            ):
                compatible_count = prior_index + 1
                break
        included = (*portfolios[compatible_count], candidate)
        excluded = portfolios[-1]
        portfolios.append(
            included
            if _portfolio_is_better(included, excluded, runs, coverage, settings)
            else excluded
        )
    return portfolios[-1]


def _portfolio_is_better(
    left: tuple[_SpurCandidate, ...],
    right: tuple[_SpurCandidate, ...],
    runs: tuple[_DirectedRun, ...],
    coverage: float,
    settings: SpurDetectionSettings,
) -> bool:
    left_value = _portfolio_value(left, runs, coverage, settings)
    right_value = _portfolio_value(right, runs, coverage, settings)
    if left_value != right_value:
        return left_value > right_value
    left_signatures = tuple(
        _candidate_signature(candidate, runs)
        for candidate in sorted(
            left, key=lambda candidate: _candidate_route_order(candidate, runs)
        )
    )
    right_signatures = tuple(
        _candidate_signature(candidate, runs)
        for candidate in sorted(
            right, key=lambda candidate: _candidate_route_order(candidate, runs)
        )
    )
    return left_signatures < right_signatures


def _portfolio_value(
    candidates: tuple[_SpurCandidate, ...],
    runs: tuple[_DirectedRun, ...],
    coverage: float,
    settings: SpurDetectionSettings,
) -> tuple[float, int, float]:
    unique_return_runs = frozenset(
        run_index for candidate in candidates for run_index in candidate.return_runs
    )
    repeated_distance = sum(runs[index].distance_m for index in unique_return_runs)
    metrics = tuple(
        _candidate_metrics(candidate, runs, coverage, settings)
        for candidate in candidates
    )
    confidence = sum(
        {"low": 1, "medium": 2, "high": 3}[metric.confidence] for metric in metrics
    )
    excursion_distance = sum(metric.total_distance_m for metric in metrics)
    return repeated_distance, confidence, excursion_distance


def _public_spur(
    candidate: _SpurCandidate,
    runs: tuple[_DirectedRun, ...],
    edges: tuple[ProjectedGeometryEdge, ...],
    route_distance_m: float,
    deliberate_anchors: tuple[SpurTraversalAnchor, ...],
    coverage: float,
    topology: Literal["loop", "point_to_point"] | None,
    settings: SpurDetectionSettings,
) -> RouteSpur:
    start_edge_index = runs[candidate.start_run].edge_indices[0]
    end_edge_index = runs[candidate.end_run].edge_indices[-1]
    edge_prefix = _edge_prefix(edges)
    metrics = _candidate_metrics(candidate, runs, coverage, settings)
    geometry = (
        edges[start_edge_index].start,
        *(edge.end for edge in edges[start_edge_index : end_edge_index + 1]),
    )
    start_progress = _normalized_progress(metrics.start_distance_m, route_distance_m)
    turnaround_progress = _normalized_progress(
        metrics.turnaround_distance_m, route_distance_m
    )
    end_progress = _normalized_progress(metrics.end_distance_m, route_distance_m)
    if turnaround_progress < start_progress:
        if start_progress - turnaround_progress > _PROGRESS_EPSILON:
            raise AssertionError("spur turnaround precedes its route-index interval")
        turnaround_progress = start_progress
    if turnaround_progress > end_progress:
        if turnaround_progress - end_progress > _PROGRESS_EPSILON:
            raise AssertionError("spur turnaround follows its route-index interval")
        turnaround_progress = end_progress
    if not (0 <= start_progress <= turnaround_progress <= end_progress <= 1):
        raise AssertionError("spur progress conversion violated traversal order")
    start_coordinate = geometry[0]
    end_coordinate = geometry[-1]
    turnaround_coordinate = _coordinate_at_distance(
        edges, edge_prefix, metrics.turnaround_distance_m
    )
    included = tuple(
        anchor
        for anchor in sorted(
            deliberate_anchors, key=lambda value: (value.route_progress, value.id)
        )
        if start_progress <= anchor.route_progress <= end_progress
    )
    reasons: list[RouteSpurReasonCode] = ["reversed_edge_sequence"]
    reasons.append(
        "exact_corridor_return"
        if metrics.branch_gap_m <= 1.0
        else "approximate_corridor_return"
    )
    if metrics.connector_distance_m > 1e-6:
        reasons.append("turnaround_connector_present")
    if included:
        reasons.append("contains_deliberate_stop")
    if coverage < settings.minimum_edge_id_coverage:
        reasons.append("incomplete_edge_coverage")
    near_endpoint = start_progress <= 0.02 or end_progress >= 0.98
    if near_endpoint:
        reasons.append("near_route_endpoint")
    if topology == "loop" and near_endpoint:
        reasons.append("loop_closure_overlap")
    identifier = _spur_id(candidate, runs)
    return RouteSpur(
        id=identifier,
        kind=(
            "immediate_out_and_back"
            if metrics.connector_distance_m <= 1e-6
            else "repeated_corridor_excursion"
        ),
        start_progress=start_progress,
        turnaround_progress=turnaround_progress,
        end_progress=end_progress,
        start_coordinate=start_coordinate,
        turnaround_coordinate=turnaround_coordinate,
        end_coordinate=end_coordinate,
        geometry=geometry,
        outbound_distance_m=metrics.outbound_distance_m,
        return_distance_m=metrics.return_distance_m,
        repeated_distance_m=metrics.return_distance_m,
        total_excursion_distance_m=metrics.total_distance_m,
        turnaround_connector_distance_m=metrics.connector_distance_m,
        maximum_separation_m=_maximum_separation(geometry),
        deliberate_stop_ids=tuple(anchor.id for anchor in included),
        deliberate_stop_names=tuple(anchor.name for anchor in included),
        confidence=metrics.confidence,
        reason_codes=tuple(reasons),
    )


def _candidate_metrics(
    candidate: _SpurCandidate,
    runs: tuple[_DirectedRun, ...],
    coverage: float,
    settings: SpurDetectionSettings,
) -> _CandidateMetrics:
    start_distance = runs[candidate.start_run].start_distance_m
    end_distance = runs[candidate.end_run].end_distance_m
    interval_distance = max(0.0, end_distance - start_distance)
    return_distance = min(
        interval_distance,
        _candidate_repeated_distance(candidate, runs),
    )
    outbound_distance = min(
        max(0.0, interval_distance - return_distance),
        sum(
            runs[index].distance_m
            for index in candidate.outbound_runs - candidate.return_runs
        ),
    )
    connector_distance = max(
        0.0, interval_distance - outbound_distance - return_distance
    )
    branch_gap = haversine_distance_m(
        runs[candidate.start_run].start,
        runs[candidate.end_run].end,
    )
    confidence: RouteSpurConfidence
    if coverage < settings.minimum_edge_id_coverage:
        confidence = "low"
    elif return_distance >= 500.0 and connector_distance <= 10.0 and branch_gap <= 5.0:
        confidence = "high"
    else:
        confidence = "medium"
    turnaround_distance = (
        runs[candidate.turnaround_start_run].end_distance_m
        + runs[candidate.turnaround_end_run].start_distance_m
    ) / 2
    return _CandidateMetrics(
        start_distance_m=start_distance,
        turnaround_distance_m=turnaround_distance,
        end_distance_m=end_distance,
        outbound_distance_m=outbound_distance,
        return_distance_m=return_distance,
        connector_distance_m=connector_distance,
        total_distance_m=interval_distance,
        branch_gap_m=branch_gap,
        confidence=confidence,
    )


def _candidate_is_valid(
    candidate: _SpurCandidate,
    runs: tuple[_DirectedRun, ...],
    settings: SpurDetectionSettings,
) -> bool:
    run_count = len(runs)
    indices = (
        candidate.start_run,
        candidate.turnaround_start_run,
        candidate.turnaround_end_run,
        candidate.end_run,
        *candidate.outbound_runs,
        *candidate.return_runs,
    )
    if not indices or any(index < 0 or index >= run_count for index in indices):
        return False
    if not (
        candidate.start_run
        <= candidate.turnaround_start_run
        < candidate.turnaround_end_run
        <= candidate.end_run
    ):
        return False
    if not candidate.outbound_runs or not candidate.return_runs:
        return False
    interval = range(candidate.start_run, candidate.end_run + 1)
    interval_indices = frozenset(interval)
    if not (
        candidate.outbound_runs <= interval_indices
        and candidate.return_runs <= interval_indices
    ):
        return False
    if candidate.outbound_runs & candidate.return_runs:
        return False
    if max(candidate.outbound_runs) >= min(candidate.return_runs):
        return False
    component = runs[candidate.start_run].component
    if any(runs[index].component != component for index in interval):
        return False
    return (
        _candidate_repeated_distance(candidate, runs)
        >= settings.minimum_reversed_edge_distance_m
    )


def _candidate_start_edge(
    candidate: _SpurCandidate, runs: tuple[_DirectedRun, ...]
) -> int:
    return runs[candidate.start_run].edge_indices[0]


def _candidate_end_edge(
    candidate: _SpurCandidate, runs: tuple[_DirectedRun, ...]
) -> int:
    return runs[candidate.end_run].edge_indices[-1]


def _candidate_route_order(
    candidate: _SpurCandidate,
    runs: tuple[_DirectedRun, ...],
) -> tuple[int, int, tuple[int, ...]]:
    return (
        _candidate_start_edge(candidate, runs),
        -_candidate_end_edge(candidate, runs),
        _candidate_signature(candidate, runs),
    )


def _candidate_signature(
    candidate: _SpurCandidate,
    runs: tuple[_DirectedRun, ...],
) -> tuple[int, ...]:
    return (
        _candidate_start_edge(candidate, runs),
        candidate.turnaround_start_run,
        candidate.turnaround_end_run,
        _candidate_end_edge(candidate, runs),
        -1,
        *sorted(candidate.outbound_runs),
        -2,
        *sorted(candidate.return_runs),
    )


def _candidate_repeated_distance(
    candidate: _SpurCandidate,
    runs: tuple[_DirectedRun, ...],
) -> float:
    return sum(runs[index].distance_m for index in candidate.return_runs)


def _candidate_excursion_distance(
    candidate: _SpurCandidate,
    runs: tuple[_DirectedRun, ...],
) -> float:
    return max(
        0.0,
        runs[candidate.end_run].end_distance_m
        - runs[candidate.start_run].start_distance_m,
    )


def _candidates_overlap(
    left: _SpurCandidate,
    right: _SpurCandidate,
    runs: tuple[_DirectedRun, ...],
) -> bool:
    return not (
        _candidate_end_edge(left, runs) < _candidate_start_edge(right, runs)
        or _candidate_end_edge(right, runs) < _candidate_start_edge(left, runs)
    )


def _assert_candidate_portfolio(
    candidates: tuple[_SpurCandidate, ...],
    runs: tuple[_DirectedRun, ...],
) -> None:
    starts = tuple(_candidate_start_edge(candidate, runs) for candidate in candidates)
    if starts != tuple(sorted(starts)):
        raise AssertionError("spur candidates must follow route-index order")
    if any(
        _candidate_end_edge(earlier, runs) >= _candidate_start_edge(later, runs)
        for earlier, later in zip(candidates, candidates[1:], strict=False)
    ):
        raise AssertionError("spur candidates must not overlap in route-index space")
    seen_return_runs: set[int] = set()
    for candidate in candidates:
        overlap = seen_return_runs & candidate.return_runs
        if overlap:
            raise AssertionError(
                "spur repeated-distance evidence must not double count"
            )
        seen_return_runs.update(candidate.return_runs)


def _assert_public_spur_portfolio(spurs: tuple[RouteSpur, ...]) -> None:
    if any(
        earlier.end_progress > later.start_progress
        for earlier, later in zip(spurs, spurs[1:], strict=False)
    ):
        raise AssertionError("public spur progress intervals must not overlap")


def _normalized_progress(distance_m: float, route_distance_m: float) -> float:
    if route_distance_m <= 0:
        if abs(distance_m) <= _PROGRESS_EPSILON:
            return 0.0
        raise AssertionError("positive spur progress requires positive route distance")
    progress = distance_m / route_distance_m
    if progress < -_PROGRESS_EPSILON or progress > 1 + _PROGRESS_EPSILON:
        raise AssertionError("spur distance lies outside authoritative route distance")
    if progress < 0:
        return 0.0
    if progress > 1:
        return 1.0
    return progress


def _runs_reverse(
    earlier: _DirectedRun,
    later: _DirectedRun,
    settings: SpurDetectionSettings,
) -> bool:
    return (
        earlier.component == later.component
        and earlier.edge_id == later.edge_id
        and haversine_distance_m(earlier.start, later.end)
        <= settings.maximum_branch_coordinate_gap_m
        and haversine_distance_m(earlier.end, later.start)
        <= settings.maximum_branch_coordinate_gap_m
    )


def _edge_prefix(edges: tuple[ProjectedGeometryEdge, ...]) -> tuple[float, ...]:
    values = [0.0]
    for edge in edges:
        values.append(values[-1] + edge.distance_m)
    return tuple(values)


def _coordinate_at_distance(
    edges: tuple[ProjectedGeometryEdge, ...],
    prefix: tuple[float, ...],
    distance_m: float,
) -> GeoJsonPosition:
    if not edges:
        raise ValueError("spur coordinate mapping requires route edges")
    bounded = min(max(distance_m, 0.0), prefix[-1])
    for index, edge in enumerate(edges):
        if bounded > prefix[index + 1] and index + 1 < len(edges):
            continue
        if edge.distance_m <= 0:
            return edge.end
        ratio = (bounded - prefix[index]) / edge.distance_m
        return (
            edge.start[0] + (edge.end[0] - edge.start[0]) * ratio,
            edge.start[1] + (edge.end[1] - edge.start[1]) * ratio,
        )
    return edges[-1].end


def _maximum_separation(geometry: tuple[GeoJsonPosition, ...]) -> float:
    projection = LocalMetricProjection(geometry[0][1])
    projected = tuple(projection.project_position(position) for position in geometry)
    branch = projected[0]
    rejoin = projected[-1]
    corridor: Point | LineString = (
        Point(branch) if branch == rejoin else LineString((branch, rejoin))
    )
    return max(Point(position).distance(corridor) for position in projected)


def _spur_id(candidate: _SpurCandidate, runs: tuple[_DirectedRun, ...]) -> str:
    structure = ";".join(
        (
            f"{index}:{runs[index].edge_id}:"
            f"{runs[index].start[0]:.7f},{runs[index].start[1]:.7f}:"
            f"{runs[index].end[0]:.7f},{runs[index].end[1]:.7f}"
        )
        for index in range(candidate.start_run, candidate.end_run + 1)
    )
    evidence = ",".join(str(value) for value in _candidate_signature(candidate, runs))
    return f"spur-{sha256(f'{structure}|{evidence}'.encode()).hexdigest()[:16]}"
