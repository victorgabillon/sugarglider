"""Immutable internal models for edge-aware complete-tour optimization."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from sugarglider.analysis.route import CanonicalEdgeTraversal
from sugarglider.domain.models import Coordinate, GeoJsonPosition, RouteResult
from sugarglider.planning.models import (
    ConstraintStrength,
    DistancePriority,
    RouteTopology,
)
from sugarglider.planning.profiles import RoutingProfileId
from sugarglider.pois.models import PoiApproachCandidate
from sugarglider.routing.backend import RoutedPath

type OptimizationAnchorKind = Literal["exact", "fixed", "soft"]
type OptimizationOperatorKind = Literal[
    "path_option",
    "relocate",
    "swap",
    "two_opt",
    "alternate_approach",
    "spur_rejoin",
    "ruin_recreate",
]
type PathOptionSourceKind = Literal[
    "source_leg",
    "shortest",
    "alternative",
    "spur_connector",
    "avoidance_connector",
    "guide_connector",
    "relocation_connector",
    "lazy_move_leg",
]
type RejoinSource = Literal[
    "first_after_spur",
    "distance_sample",
    "semantic_anchor",
    "mandatory_boundary",
]
type SpurFinalReason = Literal[
    "unsupported_spur",
    "no_downstream_rejoin",
    "no_connector_path",
    "inbound_corridor_reused",
    "reconstruction_failed",
    "no_targeted_improvement",
    "coverage_regression",
    "profile_regression",
    "explicit_maximum",
    "archive_dominated",
    "portfolio_excluded",
    "published",
    "ordinary_paths_reused_corridor",
    "avoidance_unsupported",
    "avoidance_no_path",
    "avoidance_paths_reused_corridor",
    "guide_points_unrouteable",
    "guide_paths_reused_corridor",
    "no_viable_connector",
    "ordinary_no_material_repair",
    "avoidance_no_material_repair",
    "guide_no_material_repair",
]
type ConnectorGenerationStrategy = Literal[
    "ordinary_alternative",
    "custom_model_corridor_avoidance",
    "guide_point_left",
    "guide_point_right",
]


@dataclass(frozen=True)
class GlobalOptimizationSettings:
    """Validated hard bounds for one request-scoped global search."""

    maximum_initial_states: int = 8
    maximum_path_options_per_directed_pair: int = 3
    maximum_uncached_global_optimizer_calls: int = 64
    maximum_parallel_graphhopper_requests: int = 4
    maximum_negative_cache_entries: int = 128
    maximum_candidate_successors_per_anchor: int = 8
    maximum_spur_rejoin_positions: int = 8
    maximum_relocation_targets_per_stop: int = 4
    maximum_iterations: int = 500
    maximum_no_improvement_iterations: int = 120
    pareto_archive_size: int = 12
    complete_evaluation_limit: int = 24
    optimizer_cpu_time_limit_s: float = 1.5
    optimizer_total_wall_time_limit_s: float = 4.0
    minimum_structural_improvement_m: float = 500.0
    maximum_extra_distance_share: float = 0.05
    maximum_extra_distance_m: float = 2_000.0
    maximum_sources_for_structural_seeding: int = 2
    maximum_spurs_per_source: int = 3
    maximum_connector_options_per_rejoin: int = 3
    maximum_structural_seeds_retained: int = 8
    maximum_inbound_overlap_share: float = 0.30
    maximum_shared_distance_near_turnaround_m: float = 100.0
    rejoin_distances_m: tuple[float, ...] = (
        250.0,
        500.0,
        1_000.0,
        2_000.0,
        4_000.0,
    )
    corridor_buffer_width_m: float = 25.0
    corridor_simplification_m: float = 5.0
    maximum_corridor_polygon_vertices: int = 80
    avoidance_priority_multiplier: float = 0.02
    maximum_avoidance_requests_per_target: int = 4
    maximum_guide_candidates_per_rejoin: int = 4
    maximum_guide_route_attempts_per_target: int = 6
    maximum_repairs_per_composed_state: int = 3
    maximum_structural_combinations_per_source: int = 12
    maximum_composed_states_retained: int = 6
    maximum_actions_per_structural_target: int = 2
    maximum_structural_actions_per_source: int = 6
    maximum_guide_snap_distance_m: float = 100.0
    maximum_guide_connector_detour_factor: float = 3.0
    guide_lateral_offsets_m: tuple[float, ...] = (150.0, 300.0, 600.0)
    guide_forward_shares: tuple[float, ...] = (0.33, 0.50, 0.67)

    def __post_init__(self) -> None:
        bounded = (
            (self.maximum_initial_states, 1, 8),
            (self.maximum_path_options_per_directed_pair, 1, 3),
            (self.maximum_uncached_global_optimizer_calls, 0, 64),
            (self.maximum_parallel_graphhopper_requests, 1, 4),
            (self.maximum_negative_cache_entries, 0, 128),
            (self.maximum_candidate_successors_per_anchor, 1, 8),
            (self.maximum_spur_rejoin_positions, 1, 10),
            (self.maximum_relocation_targets_per_stop, 1, 4),
            (self.maximum_iterations, 1, 500),
            (self.maximum_no_improvement_iterations, 1, 120),
            (self.pareto_archive_size, 1, 12),
            (self.complete_evaluation_limit, 1, 24),
            (self.maximum_sources_for_structural_seeding, 1, 2),
            (self.maximum_spurs_per_source, 1, 3),
            (self.maximum_connector_options_per_rejoin, 1, 3),
            (self.maximum_structural_seeds_retained, 1, 8),
            (self.maximum_corridor_polygon_vertices, 4, 80),
            (self.maximum_avoidance_requests_per_target, 0, 4),
            (self.maximum_guide_candidates_per_rejoin, 1, 4),
            (self.maximum_guide_route_attempts_per_target, 0, 6),
            (self.maximum_repairs_per_composed_state, 2, 3),
            (self.maximum_structural_combinations_per_source, 1, 12),
            (self.maximum_composed_states_retained, 1, 6),
            (self.maximum_actions_per_structural_target, 1, 2),
            (self.maximum_structural_actions_per_source, 2, 6),
        )
        if any(not minimum <= value <= maximum for value, minimum, maximum in bounded):
            raise ValueError("global-optimization integer bounds are invalid")
        finite_values = (
            self.optimizer_cpu_time_limit_s,
            self.optimizer_total_wall_time_limit_s,
            self.minimum_structural_improvement_m,
            self.maximum_extra_distance_share,
            self.maximum_extra_distance_m,
            self.maximum_inbound_overlap_share,
            self.maximum_shared_distance_near_turnaround_m,
            *self.rejoin_distances_m,
            self.corridor_buffer_width_m,
            self.corridor_simplification_m,
            self.avoidance_priority_multiplier,
            self.maximum_guide_snap_distance_m,
            self.maximum_guide_connector_detour_factor,
            *self.guide_lateral_offsets_m,
            *self.guide_forward_shares,
        )
        if any(not isfinite(value) or value < 0 for value in finite_values):
            raise ValueError("global-optimization numeric bounds must be finite")
        if self.optimizer_cpu_time_limit_s <= 0:
            raise ValueError("optimizer CPU limit must be positive")
        if self.optimizer_total_wall_time_limit_s <= 0:
            raise ValueError("optimizer wall-time limit must be positive")
        if self.maximum_extra_distance_share > 0.05:
            raise ValueError("extra-distance share may not exceed five percent")
        if self.maximum_extra_distance_m > 2_000:
            raise ValueError("extra-distance allowance may not exceed two kilometres")
        if self.maximum_spur_rejoin_positions > 8:
            raise ValueError("structural seeding may consider at most eight rejoins")
        if self.maximum_inbound_overlap_share > 0.30:
            raise ValueError("inbound overlap share may not exceed 30 percent")
        if self.maximum_shared_distance_near_turnaround_m > 100:
            raise ValueError("turnaround overlap allowance may not exceed 100 metres")
        if tuple(sorted(set(self.rejoin_distances_m))) != self.rejoin_distances_m:
            raise ValueError("rejoin distances must be unique and increasing")
        if not 0 < self.avoidance_priority_multiplier <= 1:
            raise ValueError("avoidance priority multiplier must be within (0, 1]")
        if self.corridor_buffer_width_m > 50:
            raise ValueError("corridor buffer may not exceed 50 metres")
        if self.corridor_simplification_m > 10:
            raise ValueError("corridor simplification may not exceed 10 metres")
        if self.maximum_guide_connector_detour_factor < 1:
            raise ValueError("guide connector detour factor must be at least one")
        if any(not 0 < share < 1 for share in self.guide_forward_shares):
            raise ValueError("guide forward shares must be within (0, 1)")
        if len(self.guide_lateral_offsets_m) != len(self.guide_forward_shares):
            raise ValueError("guide offsets and forward shares must align")
        if tuple(sorted(set(self.guide_lateral_offsets_m))) != (
            self.guide_lateral_offsets_m
        ):
            raise ValueError("guide lateral offsets must be unique and increasing")
        if tuple(sorted(set(self.guide_forward_shares))) != self.guide_forward_shares:
            raise ValueError("guide forward shares must be unique and increasing")


@dataclass(frozen=True)
class OptimizationAnchor:
    """One semantic or structural route anchor with immutable identity."""

    id: str
    name: str
    coordinate: Coordinate
    semantic_coordinate: Coordinate
    kind: OptimizationAnchorKind
    source_progress: float
    exact_window: int
    constraint_strength: ConstraintStrength | None = None
    outcome: Literal["reached", "approximated"] | None = None
    selected_approach: PoiApproachCandidate | None = None
    approach_options: tuple[PoiApproachCandidate, ...] = ()
    maximum_semantic_distance_m: float | None = None
    requested: bool = False
    discovered: bool = False
    containing_spur_ids: tuple[str, ...] = ()
    containing_spur_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id or not self.name:
            raise ValueError("optimization anchors require identity and name")
        if not 0 <= self.source_progress <= 1 or self.exact_window < 0:
            raise ValueError("optimization anchor progress/window is invalid")
        if self.kind == "soft":
            if (
                self.constraint_strength not in {"approach", "best_effort"}
                or self.outcome is None
                or self.selected_approach is None
                or self.maximum_semantic_distance_m is None
            ):
                raise ValueError("soft optimization anchors need routing semantics")
        elif (
            self.outcome is not None
            or self.selected_approach is not None
            or self.approach_options
            or self.maximum_semantic_distance_m is not None
        ):
            raise ValueError("non-soft optimization anchors cannot carry approaches")
        if self.requested and self.discovered:
            raise ValueError("an anchor cannot be requested and discovered")

    @property
    def movable(self) -> bool:
        return self.kind == "soft"


@dataclass(frozen=True)
class PathOption:
    """One GraphHopper-authoritative directed path between two anchors."""

    id: str
    from_anchor_id: str
    to_anchor_id: str
    from_coordinate: Coordinate
    to_coordinate: Coordinate
    routing_profile: RoutingProfileId
    routed_path: RoutedPath
    directed_edges: tuple[CanonicalEdgeTraversal, ...]
    undirected_edge_keys: tuple[int, ...]
    distance_m: float
    path_detail_quality: tuple[tuple[str, float], ...]
    severe_profile_incompatibility: bool
    warnings: tuple[str, ...]
    source_kind: PathOptionSourceKind

    def __post_init__(self) -> None:
        if not self.id or self.distance_m < 0 or not isfinite(self.distance_m):
            raise ValueError("path options require finite identity and distance")
        if self.distance_m != self.routed_path.distance_m:
            raise ValueError("path-option distance must match its routed path")
        if self.undirected_edge_keys != tuple(
            traversal.physical_edge_key for traversal in self.directed_edges
        ):
            raise ValueError("path-option edge keys must match directed traversals")


@dataclass(frozen=True)
class AppliedSpurRepair:
    """One materially validated semantic-leg replacement."""

    target_stable_id: str
    spur_id: str
    stop_ids: tuple[str, ...]
    stop_names: tuple[str, ...]
    containing_leg_index: int
    start_progress: float
    turnaround_progress: float
    end_progress: float
    source_repeated_distance_m: float
    resulting_repeated_distance_m: float
    improvement_m: float
    generation_strategy: ConnectorGenerationStrategy
    replacement_path_option_id: str

    def __post_init__(self) -> None:
        if not self.target_stable_id or not self.replacement_path_option_id:
            raise ValueError("applied spur repairs require stable identities")
        if self.containing_leg_index < 0:
            raise ValueError("applied spur repair leg index must be non-negative")
        if not (
            0
            <= self.start_progress
            <= self.turnaround_progress
            <= self.end_progress
            <= 1
        ):
            raise ValueError("applied spur repair progress interval is invalid")
        if (
            self.source_repeated_distance_m < 0
            or self.resulting_repeated_distance_m < 0
            or self.improvement_m <= 0
            or not all(
                isfinite(value)
                for value in (
                    self.source_repeated_distance_m,
                    self.resulting_repeated_distance_m,
                    self.improvement_m,
                )
            )
        ):
            raise ValueError("applied spur repair measurements are invalid")
        if (
            abs(
                self.source_repeated_distance_m
                - self.resulting_repeated_distance_m
                - self.improvement_m
            )
            > 1e-6
        ):
            raise ValueError("applied spur repair improvement must match its residual")

    def ordering_key(self) -> tuple[int, float, str]:
        return (
            self.containing_leg_index,
            self.start_progress,
            self.target_stable_id,
        )


@dataclass(frozen=True)
class EdgeUsage:
    """Aggregated use of one physical GraphHopper edge in both directions."""

    physical_edge_key: int
    forward_runs: int
    reverse_runs: int
    forward_distance_m: float
    reverse_distance_m: float


@dataclass(frozen=True)
class EdgeReuseComponents:
    """Fast route-wide edge and return metrics used by the typed objective."""

    total_repeated_distance_m: float
    same_direction_reuse_m: float
    opposite_direction_reuse_m: float
    immediate_return_distance_m: float
    targeted_spur_repetition_m: float
    edge_usage: tuple[EdgeUsage, ...]


@dataclass(frozen=True)
class TourObjective:
    """Lexicographic complete-tour objective; no opaque composite score."""

    hard_feasible: bool
    reached_requested: int
    approximated_requested: int
    dropped_requested: int
    priority_weighted_coverage: int
    opposite_direction_reuse_m: float
    analyzed_total_spur_repetition_m: float | None
    total_repeated_distance_m: float
    same_direction_reuse_m: float
    immediate_backtracking_m: float
    profile_penalty: float
    nature_utility: float
    distance_m: float
    distance_error_m: float

    def lexicographic_key(self) -> tuple[object, ...]:
        return (
            0 if self.hard_feasible else 1,
            -self.priority_weighted_coverage,
            -self.reached_requested,
            self.approximated_requested,
            self.dropped_requested,
            self.opposite_direction_reuse_m,
            self.total_repeated_distance_m,
            self.same_direction_reuse_m,
            self.immediate_backtracking_m,
            self.profile_penalty,
            -self.nature_utility,
            self.distance_error_m,
            self.distance_m,
        )


@dataclass(frozen=True)
class TourOptimizationState:
    """One complete graph-valid candidate solution in the global search."""

    source_candidate_id: str
    topology: RouteTopology
    routing_profile: RoutingProfileId
    anchors: tuple[OptimizationAnchor, ...]
    ordered_anchor_ids: tuple[str, ...]
    selected_target_by_anchor: tuple[tuple[str, str], ...]
    selected_path_option_by_leg: tuple[str, ...]
    path_options: tuple[PathOption, ...]
    exact_window_by_anchor: tuple[tuple[str, int], ...]
    visited_requested_stop_ids: frozenset[str]
    visited_discovered_poi_ids: frozenset[str]
    edge_usage: tuple[EdgeUsage, ...]
    objective_components: TourObjective
    complete_path: RoutedPath
    stable_signature: str
    last_operator: OptimizationOperatorKind | None = None
    applied_spur_repairs: tuple[AppliedSpurRepair, ...] = ()

    def __post_init__(self) -> None:
        if self.ordered_anchor_ids != tuple(anchor.id for anchor in self.anchors):
            raise ValueError("state anchor IDs must follow complete anchor order")
        if len(self.selected_path_option_by_leg) != max(0, len(self.anchors) - 1):
            raise ValueError("state must select exactly one path option per leg")
        if len(self.path_options) != len(self.selected_path_option_by_leg):
            raise ValueError("state path options and selected IDs must align")
        if any(
            option.from_anchor_id != left.id
            or option.to_anchor_id != right.id
            or option.id != selected_id
            for (left, right), option, selected_id in zip(
                zip(self.anchors, self.anchors[1:], strict=False),
                self.path_options,
                self.selected_path_option_by_leg,
                strict=True,
            )
        ):
            raise ValueError("state path options must match semantic leg identity")
        if len(self.ordered_anchor_ids) != len(set(self.ordered_anchor_ids)):
            raise ValueError("optimization state anchor IDs must be unique")
        if self.applied_spur_repairs != tuple(
            sorted(self.applied_spur_repairs, key=AppliedSpurRepair.ordering_key)
        ):
            raise ValueError("applied spur repairs must be canonically ordered")
        target_ids = tuple(
            repair.target_stable_id for repair in self.applied_spur_repairs
        )
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("applied spur repair target IDs must be unique")
        spur_ids = tuple(
            repair.spur_id for repair in self.applied_spur_repairs if repair.spur_id
        )
        if len(spur_ids) != len(set(spur_ids)):
            raise ValueError("applied spur repair IDs must be unique")


@dataclass(frozen=True)
class StructuralRepairAction:
    """Reusable routed replacement and its validated single-repair state."""

    repair: AppliedSpurRepair
    replacement_option: PathOption
    resulting_single_state: TourOptimizationState
    stable_signature: str

    def __post_init__(self) -> None:
        if (
            self.replacement_option.id != self.repair.replacement_path_option_id
            or self.repair not in self.resulting_single_state.applied_spur_repairs
            or not self.stable_signature
        ):
            raise ValueError("structural repair action components must agree")


@dataclass(frozen=True)
class OptimizationSource:
    """One finalized source candidate translated by a planner adapter."""

    source_candidate_id: str
    route: RouteResult
    routed_path: RoutedPath
    anchors: tuple[OptimizationAnchor, ...]
    topology: RouteTopology
    routing_profile: RoutingProfileId
    target_distance_m: float
    tolerance_m: float
    distance_priority: DistancePriority
    maximum_distance_m: float | None
    reached_requested_ids: frozenset[str]
    approximated_requested_ids: frozenset[str]
    dropped_requested_ids: frozenset[str]

    def __post_init__(self) -> None:
        if not self.anchors:
            raise ValueError("optimization sources require at least one anchor")
        if len({anchor.id for anchor in self.anchors}) != len(self.anchors):
            raise ValueError("optimization source anchor IDs must be unique")


@dataclass(frozen=True)
class OptimizationMove:
    """One bounded semantic neighborhood proposal."""

    operator: OptimizationOperatorKind
    anchors: tuple[OptimizationAnchor, ...]
    forced_path_option_by_leg: tuple[tuple[int, str], ...] = ()
    changed_anchor_ids: tuple[str, ...] = ()
    applied_spur_repair: AppliedSpurRepair | None = None
    path_request_leg_index: int | None = None


@dataclass(frozen=True)
class OptimizationDraft:
    """One promising archive state ready for planner-specific rebuilding."""

    source_candidate_id: str
    path: RoutedPath
    route: RouteResult
    anchors: tuple[OptimizationAnchor, ...]
    routing_points: tuple[Coordinate, ...]
    selected_approaches: tuple[tuple[str, PoiApproachCandidate], ...]
    operator: OptimizationOperatorKind
    source_objective: TourObjective
    resulting_objective: TourObjective
    applied_spur_repairs: tuple[AppliedSpurRepair, ...]
    stable_signature: str

    def metadata(self) -> tuple[tuple[str, str], ...]:
        opposite_improvement = (
            self.source_objective.opposite_direction_reuse_m
            - self.resulting_objective.opposite_direction_reuse_m
        )
        repetition_improvement = (
            self.source_objective.total_repeated_distance_m
            - self.resulting_objective.total_repeated_distance_m
        )
        backtracking_improvement = (
            self.source_objective.immediate_backtracking_m
            - self.resulting_objective.immediate_backtracking_m
        )
        distance_change = (
            self.resulting_objective.distance_m - self.source_objective.distance_m
        )
        applied_improvement = sum(
            value.improvement_m for value in self.applied_spur_repairs
        )
        return (
            ("source_candidate_id", self.source_candidate_id),
            ("optimization_operator", self.operator),
            (
                "applied_spur_target_ids",
                repr(tuple(value.spur_id for value in self.applied_spur_repairs)),
            ),
            (
                "applied_spur_names",
                repr(
                    tuple(
                        name
                        for value in self.applied_spur_repairs
                        for name in value.stop_names
                    )
                ),
            ),
            (
                "applied_spur_improvement_m",
                f"{applied_improvement:.3f}",
            ),
            (
                "source_opposite_direction_reuse_m",
                f"{self.source_objective.opposite_direction_reuse_m:.3f}",
            ),
            (
                "resulting_opposite_direction_reuse_m",
                f"{self.resulting_objective.opposite_direction_reuse_m:.3f}",
            ),
            (
                "opposite_direction_improvement_m",
                f"{opposite_improvement:.3f}",
            ),
            (
                "source_repeated_distance_m",
                f"{self.source_objective.total_repeated_distance_m:.3f}",
            ),
            (
                "resulting_repeated_distance_m",
                f"{self.resulting_objective.total_repeated_distance_m:.3f}",
            ),
            (
                "repeated_distance_improvement_m",
                f"{repetition_improvement:.3f}",
            ),
            (
                "source_backtracking_distance_m",
                f"{self.source_objective.immediate_backtracking_m:.3f}",
            ),
            (
                "resulting_backtracking_distance_m",
                f"{self.resulting_objective.immediate_backtracking_m:.3f}",
            ),
            (
                "backtracking_improvement_m",
                f"{backtracking_improvement:.3f}",
            ),
            (
                "distance_change_m",
                f"{distance_change:.3f}",
            ),
        )


@dataclass(frozen=True)
class OptimizationResult:
    drafts: tuple[OptimizationDraft, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SpurOptimizationTarget:
    """One edge-supported final-route spur selected for structural repair."""

    source_candidate_id: str
    spur_id: str
    stop_ids: tuple[str, ...]
    stop_names: tuple[str, ...]
    start_progress: float
    turnaround_progress: float
    end_progress: float
    turnaround_coordinate: Coordinate
    original_rejoin_coordinate: Coordinate
    repeated_distance_m: float
    inbound_edge_keys: frozenset[int]
    inbound_traversals: tuple[CanonicalEdgeTraversal, ...]
    inbound_geometry: tuple[GeoJsonPosition, ...]
    inbound_distance_m: float
    containing_leg_start_index: int
    containing_leg_end_index: int
    next_mandatory_progress: float
    stable_id: str


@dataclass(frozen=True)
class RejoinPosition:
    """One private downstream route position, never a semantic stop."""

    coordinate: Coordinate
    source_progress: float
    source_kind: RejoinSource
    distance_after_spur_m: float
    stable_id: str


@dataclass(frozen=True)
class InboundCorridorEvidence:
    """Ordered inbound route evidence with a private avoidable remainder."""

    targeted_spur_id: str
    turnaround_coordinate: Coordinate
    inbound_traversals: tuple[CanonicalEdgeTraversal, ...]
    inbound_distance_m: float
    allowed_stem_distance_m: float
    avoid_geometry: tuple[GeoJsonPosition, ...]
    avoid_distance_m: float
    stable_id: str


@dataclass(frozen=True)
class ConnectorGenerationAttempt:
    """One private bounded connector strategy result."""

    target_id: str
    rejoin_id: str
    strategy: ConnectorGenerationStrategy
    path_options: tuple[PathOption, ...]
    rejected_overlap: int


@dataclass(frozen=True)
class InboundOverlapMeasurement:
    inbound_distance_m: float
    raw_overlap_m: float
    allowed_stem_m: float
    charged_overlap_m: float
    overlap_share: float


def _optional_metres(value: float | None) -> str:
    return "unknown" if value is None else f"{value:.3f}"
