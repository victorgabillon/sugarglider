"""Stable candidate signatures and lightweight edge-set diversity."""

from dataclasses import dataclass
from hashlib import sha256

from sugarglider.domain.endpoints import ResolvedRouteTopology
from sugarglider.domain.models import RouteResult
from sugarglider.planning.result import PlanCandidate

MIN_SIGNATURE_EDGE_COVERAGE = 0.90
MIN_DIVERSITY_EDGE_COVERAGE = 0.80
MAX_EDGE_JACCARD_SIMILARITY = 0.90
GEOMETRY_SIGNATURE_DECIMALS = 6


def edge_id_runs(route: RouteResult) -> tuple[int, ...]:
    """Project known IDs in geometry order and collapse contiguous directed runs."""
    values: list[int | None] = [None] * (len(route.geometry) - 1)
    for segment in route.path_details.get("edge_id", ()):
        if not isinstance(segment.value, int) or isinstance(segment.value, bool):
            continue
        for index in range(segment.from_index, segment.to_index):
            values[index] = segment.value

    runs: list[int] = []
    previous_id: int | None = None
    previous_index: int | None = None
    for index, edge_id in enumerate(values):
        if edge_id is None:
            previous_id = None
            previous_index = None
            continue
        reverses_previous = (
            previous_index is not None
            and route.geometry[previous_index] == route.geometry[index + 1]
            and route.geometry[previous_index + 1] == route.geometry[index]
        )
        if edge_id != previous_id or reverses_previous:
            runs.append(edge_id)
        previous_id = edge_id
        previous_index = index
    return tuple(runs)


def candidate_signature(
    route: RouteResult, *, topology: ResolvedRouteTopology | None = None
) -> str:
    """Hash edge runs when well covered, otherwise geometry rounded to 6 decimals."""
    coverage = route.analysis.repetition.edge_id_coverage.share
    runs = edge_id_runs(route)
    if coverage >= MIN_SIGNATURE_EDGE_COVERAGE and runs:
        source = "edge-runs:" + ",".join(str(edge_id) for edge_id in runs)
        if topology is not None:
            source = f"{topology}:{source}"
        return "edges:" + sha256(source.encode()).hexdigest()
    source = "geometry:" + ";".join(
        f"{lon:.{GEOMETRY_SIGNATURE_DECIMALS}f},{lat:.{GEOMETRY_SIGNATURE_DECIMALS}f}"
        for lon, lat in route.geometry
    )
    if topology is not None:
        source = f"{topology}:{source}"
    return "geometry:" + sha256(source.encode()).hexdigest()


def known_edge_ids(route: RouteResult) -> frozenset[int]:
    return frozenset(edge_id_runs(route))


def jaccard_similarity(left: frozenset[int], right: frozenset[int]) -> float:
    """Return set overlap, considering two empty sets identical."""
    union = left | right
    if not union:
        return 1.0
    return len(left & right) / len(union)


@dataclass(frozen=True)
class DiversitySelection:
    candidates: tuple[PlanCandidate, ...]
    relaxed: bool
    low_edge_coverage: bool


def select_diverse_candidates(
    ranked: tuple[PlanCandidate, ...],
    limit: int,
    *,
    maximum_similarity: float = MAX_EDGE_JACCARD_SIMILARITY,
) -> DiversitySelection:
    """Prefer low-Jaccard candidates, then fill from deferred distinct candidates."""
    selected: list[PlanCandidate] = []
    deferred: list[PlanCandidate] = []
    low_coverage = any(
        candidate.route.analysis.repetition.edge_id_coverage.share
        < MIN_DIVERSITY_EDGE_COVERAGE
        for candidate in ranked
    )
    for candidate in ranked:
        if len(selected) >= limit:
            break
        candidate_edges = known_edge_ids(candidate.route)
        candidate_coverage = candidate.route.analysis.repetition.edge_id_coverage.share
        sufficiently_distinct = all(
            candidate_coverage < MIN_DIVERSITY_EDGE_COVERAGE
            or existing.route.analysis.repetition.edge_id_coverage.share
            < MIN_DIVERSITY_EDGE_COVERAGE
            or jaccard_similarity(candidate_edges, known_edge_ids(existing.route))
            <= maximum_similarity
            for existing in selected
        )
        if sufficiently_distinct:
            selected.append(candidate)
        else:
            deferred.append(candidate)

    relaxed = False
    if len(selected) < limit:
        for candidate in deferred:
            if len(selected) >= limit:
                break
            selected.append(candidate)
            relaxed = True

    reranked = tuple(
        candidate.model_copy(update={"rank": rank})
        for rank, candidate in enumerate(selected, start=1)
    )
    return DiversitySelection(reranked, relaxed, low_coverage)
