"""Immutable internal values for bounded spur-closure search."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from sugarglider.domain.analysis import RouteSpur
from sugarglider.domain.models import Coordinate, RouteResult
from sugarglider.planning.models import RouteTopology
from sugarglider.planning.profiles import RoutingProfileId
from sugarglider.routing.backend import RoutedPath

type RepairAnchorKind = Literal["routing_hint", "deliberate", "exact"]
type RejoinSource = Literal[
    "first_after_spur", "distance_sample", "deliberate_anchor", "routing_point"
]
type SpurRepairRejection = Literal[
    "exact_constraints",
    "profile_incompatibility",
    "explicit_maximum",
    "trivial_improvement",
    "worse_total_repetition",
]


@dataclass(frozen=True)
class SpurRepairDiagnosticSummary:
    """Safe aggregate facts for one bounded request-level refinement lane."""

    source_candidates_considered: int = 0
    spurs_considered: int = 0
    rejoin_candidates_generated: int = 0
    connector_route_attempts: int = 0
    connector_routes_succeeded: int = 0
    connector_route_failures: int = 0
    rejected_inbound_overlap: int = 0
    reconstruction_attempts: int = 0
    reconstruction_failures: int = 0
    rejected_exact_constraints: int = 0
    rejected_profile_incompatibility: int = 0
    rejected_explicit_maximum: int = 0
    rejected_trivial_improvement: int = 0
    rejected_worse_total_repetition: int = 0
    accepted_repair_drafts: int = 0
    repair_candidates_submitted_to_portfolio: int = 0
    repair_drafts_rejected_after_acceptance: int = 0
    published_repair_candidates: int = 0
    portfolio_excluded_repair_candidates: int = 0
    budget_exhausted: bool = False

    def as_dict(self) -> dict[str, int | bool]:
        return {
            "source_candidates_considered": self.source_candidates_considered,
            "spurs_considered": self.spurs_considered,
            "rejoin_candidates_generated": self.rejoin_candidates_generated,
            "connector_route_attempts": self.connector_route_attempts,
            "connector_routes_succeeded": self.connector_routes_succeeded,
            "connector_route_failures": self.connector_route_failures,
            "rejected_inbound_overlap": self.rejected_inbound_overlap,
            "reconstruction_attempts": self.reconstruction_attempts,
            "reconstruction_failures": self.reconstruction_failures,
            "rejected_exact_constraints": self.rejected_exact_constraints,
            "rejected_profile_incompatibility": (self.rejected_profile_incompatibility),
            "rejected_explicit_maximum": self.rejected_explicit_maximum,
            "rejected_trivial_improvement": self.rejected_trivial_improvement,
            "rejected_worse_total_repetition": (self.rejected_worse_total_repetition),
            "accepted_repair_drafts": self.accepted_repair_drafts,
            "repair_candidates_submitted_to_portfolio": (
                self.repair_candidates_submitted_to_portfolio
            ),
            "repair_drafts_rejected_after_acceptance": (
                self.repair_drafts_rejected_after_acceptance
            ),
            "published_repair_candidates": self.published_repair_candidates,
            "portfolio_excluded_repair_candidates": (
                self.portfolio_excluded_repair_candidates
            ),
            "budget_exhausted": self.budget_exhausted,
        }


@dataclass
class SpurRepairDiagnosticAccumulator:
    """Mutable typed counters owned by one planning request."""

    source_candidates_considered: int = 0
    spurs_considered: int = 0
    rejoin_candidates_generated: int = 0
    connector_route_attempts: int = 0
    connector_routes_succeeded: int = 0
    connector_route_failures: int = 0
    rejected_inbound_overlap: int = 0
    reconstruction_attempts: int = 0
    reconstruction_failures: int = 0
    rejected_exact_constraints: int = 0
    rejected_profile_incompatibility: int = 0
    rejected_explicit_maximum: int = 0
    rejected_trivial_improvement: int = 0
    rejected_worse_total_repetition: int = 0
    accepted_repair_drafts: int = 0
    repair_candidates_submitted_to_portfolio: int = 0
    repair_drafts_rejected_after_acceptance: int = 0
    published_repair_candidates: int = 0
    portfolio_excluded_repair_candidates: int = 0
    budget_exhausted: bool = False

    def reject(self, reason: SpurRepairRejection) -> None:
        if reason == "exact_constraints":
            self.rejected_exact_constraints += 1
        elif reason == "profile_incompatibility":
            self.rejected_profile_incompatibility += 1
        elif reason == "explicit_maximum":
            self.rejected_explicit_maximum += 1
        elif reason == "trivial_improvement":
            self.rejected_trivial_improvement += 1
        else:
            self.rejected_worse_total_repetition += 1

    def snapshot(self) -> SpurRepairDiagnosticSummary:
        return SpurRepairDiagnosticSummary(
            source_candidates_considered=self.source_candidates_considered,
            spurs_considered=self.spurs_considered,
            rejoin_candidates_generated=self.rejoin_candidates_generated,
            connector_route_attempts=self.connector_route_attempts,
            connector_routes_succeeded=self.connector_routes_succeeded,
            connector_route_failures=self.connector_route_failures,
            rejected_inbound_overlap=self.rejected_inbound_overlap,
            reconstruction_attempts=self.reconstruction_attempts,
            reconstruction_failures=self.reconstruction_failures,
            rejected_exact_constraints=self.rejected_exact_constraints,
            rejected_profile_incompatibility=self.rejected_profile_incompatibility,
            rejected_explicit_maximum=self.rejected_explicit_maximum,
            rejected_trivial_improvement=self.rejected_trivial_improvement,
            rejected_worse_total_repetition=self.rejected_worse_total_repetition,
            accepted_repair_drafts=self.accepted_repair_drafts,
            repair_candidates_submitted_to_portfolio=(
                self.repair_candidates_submitted_to_portfolio
            ),
            repair_drafts_rejected_after_acceptance=(
                self.repair_drafts_rejected_after_acceptance
            ),
            published_repair_candidates=self.published_repair_candidates,
            portfolio_excluded_repair_candidates=(
                self.portfolio_excluded_repair_candidates
            ),
            budget_exhausted=self.budget_exhausted,
        )


@dataclass(frozen=True)
class SpurClosureSettings:
    """Strict deterministic bounds and structural acceptance thresholds."""

    maximum_source_candidates: int = 2
    maximum_spurs_per_candidate: int = 2
    maximum_rejoins_per_spur: int = 8
    maximum_connector_alternatives: int = 3
    maximum_attempts_per_candidate: int = 16
    maximum_inbound_overlap_share: float = 0.30
    maximum_shared_distance_near_turnaround_m: float = 100.0
    minimum_repeated_distance_improvement_m: float = 150.0
    rejoin_distances_m: tuple[float, ...] = (250.0, 500.0, 1_000.0, 2_000.0, 4_000.0)

    def __post_init__(self) -> None:
        integer_bounds = (
            self.maximum_source_candidates,
            self.maximum_spurs_per_candidate,
            self.maximum_rejoins_per_spur,
            self.maximum_connector_alternatives,
            self.maximum_attempts_per_candidate,
        )
        if any(value < 1 for value in integer_bounds):
            raise ValueError("spur-closure bounds must be positive")
        if self.maximum_source_candidates > 2:
            raise ValueError("spur closure may consider at most two source candidates")
        if self.maximum_spurs_per_candidate > 2:
            raise ValueError(
                "spur closure may consider at most two spurs per candidate"
            )
        if self.maximum_rejoins_per_spur > 8:
            raise ValueError("spur closure may consider at most eight rejoins")
        if self.maximum_connector_alternatives > 3:
            raise ValueError("spur closure may request at most three alternatives")
        if self.maximum_attempts_per_candidate > 16:
            raise ValueError("spur closure may make at most sixteen attempts")
        if not 0 <= self.maximum_inbound_overlap_share <= 0.30:
            raise ValueError("inbound overlap share must be between zero and 0.30")
        distances = (
            self.maximum_shared_distance_near_turnaround_m,
            self.minimum_repeated_distance_improvement_m,
            *self.rejoin_distances_m,
        )
        if any(not isfinite(value) or value < 0 for value in distances):
            raise ValueError("spur-closure distances must be finite and non-negative")
        if self.maximum_shared_distance_near_turnaround_m > 100:
            raise ValueError("shared turnaround allowance may not exceed 100 metres")
        if self.minimum_repeated_distance_improvement_m < 150:
            raise ValueError("spur closure requires at least 150 metres of improvement")
        if tuple(sorted(set(self.rejoin_distances_m))) != self.rejoin_distances_m:
            raise ValueError("rejoin distances must be unique and increasing")


@dataclass(frozen=True)
class RepairAnchor:
    """One source routing hint or deliberate constraint located on the route."""

    id: str
    coordinate: Coordinate
    route_progress: float
    kind: RepairAnchorKind

    def __post_init__(self) -> None:
        if not self.id or not isfinite(self.route_progress):
            raise ValueError("repair anchors require identity and finite progress")
        if not 0 <= self.route_progress <= 1:
            raise ValueError("repair anchor progress must be normalized")

    @property
    def mandatory(self) -> bool:
        return self.kind in {"deliberate", "exact"}


@dataclass(frozen=True)
class SpurRepairSource:
    """One graph-valid source candidate and its ordered planning intent."""

    source_candidate_id: str
    route: RouteResult
    routed_path: RoutedPath
    routing_points: tuple[Coordinate, ...]
    anchors: tuple[RepairAnchor, ...]
    topology: RouteTopology
    profile: RoutingProfileId
    maximum_distance_m: float | None = None


@dataclass(frozen=True)
class RejoinCandidate:
    coordinate: Coordinate
    source_progress: float
    source_kind: RejoinSource
    distance_after_spur_m: float
    stable_id: str


@dataclass(frozen=True)
class SpurClosureDiagnostics:
    source_candidate_id: str
    targeted_spur_id: str
    rejoin_source: RejoinSource
    rejoin_progress: float
    connector_distance_m: float
    inbound_overlap_m: float
    inbound_overlap_share: float
    source_spur_repeated_distance_m: float
    resulting_spur_repeated_distance_m: float
    repeated_distance_improvement_m: float
    immediate_backtracking_improvement_m: float
    repair_attempt_count: int
    targeted_spur_still_present: bool

    def metadata(self) -> tuple[tuple[str, str], ...]:
        """Return safe public candidate-detail values without graph edge IDs."""
        return (
            ("source_candidate_id", self.source_candidate_id),
            ("targeted_spur_id", self.targeted_spur_id),
            ("rejoin_source", self.rejoin_source),
            ("rejoin_progress", f"{self.rejoin_progress:.6f}"),
            ("connector_distance_m", f"{self.connector_distance_m:.3f}"),
            ("inbound_overlap_m", f"{self.inbound_overlap_m:.3f}"),
            ("inbound_overlap_share", f"{self.inbound_overlap_share:.6f}"),
            (
                "source_spur_repeated_distance_m",
                f"{self.source_spur_repeated_distance_m:.3f}",
            ),
            (
                "resulting_spur_repeated_distance_m",
                f"{self.resulting_spur_repeated_distance_m:.3f}",
            ),
            (
                "repeated_distance_improvement_m",
                f"{self.repeated_distance_improvement_m:.3f}",
            ),
            (
                "immediate_backtracking_improvement_m",
                f"{self.immediate_backtracking_improvement_m:.3f}",
            ),
            ("repair_attempt_count", str(self.repair_attempt_count)),
            (
                "targeted_spur_still_present",
                str(self.targeted_spur_still_present).lower(),
            ),
        )


@dataclass(frozen=True)
class SpurClosureDraft:
    path: RoutedPath
    route: RouteResult
    routing_points: tuple[Coordinate, ...]
    diagnostics: SpurClosureDiagnostics


@dataclass(frozen=True)
class SpurClosureResult:
    drafts: tuple[SpurClosureDraft, ...]
    attempts: int
    warnings: tuple[str, ...]
    diagnostics: SpurRepairDiagnosticSummary


@dataclass(frozen=True)
class _SupportedSpur:
    spur: RouteSpur
    inbound_edge_ids: frozenset[int]
    inbound_distance_m: float
