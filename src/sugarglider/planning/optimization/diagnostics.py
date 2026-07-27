"""Safe request-level diagnostics for global tour optimization."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from math import isfinite
from typing import Any

from sugarglider.planning.optimization.models import (
    ConnectorGenerationStrategy,
    OptimizationOperatorKind,
    SpurFinalReason,
    SpurOptimizationTarget,
)

OPERATORS: tuple[OptimizationOperatorKind, ...] = (
    "path_option",
    "relocate",
    "swap",
    "two_opt",
    "alternate_approach",
    "spur_rejoin",
    "ruin_recreate",
)


@dataclass
class _SpurAccumulator:
    stable_id: str
    source_candidate_id: str
    spur_id: str
    names: tuple[str, ...]
    source_repeated_distance_m: float = 0.0
    rejoin_positions_generated: int = 0
    connector_requests: int = 0
    connector_paths_returned: int = 0
    rejected_inbound_overlap: int = 0
    ordinary_connector_paths: int = 0
    ordinary_rejected_overlap: int = 0
    ordinary_overlap_viable_connectors: int = 0
    ordinary_reconstructed_states: int = 0
    ordinary_nonmaterial_states: int = 0
    ordinary_qualifying_states: int = 0
    ordinary_best_improvement_m: float = 0.0
    avoidance_supported: bool = False
    avoidance_requests: int = 0
    avoidance_paths_returned: int = 0
    avoidance_rejected_overlap: int = 0
    avoidance_overlap_viable_connectors: int = 0
    avoidance_reconstructed_states: int = 0
    avoidance_nonmaterial_states: int = 0
    avoidance_qualifying_states: int = 0
    avoidance_best_improvement_m: float = 0.0
    guide_candidates_generated: int = 0
    guide_route_attempts: int = 0
    guide_paths_returned: int = 0
    guide_rejected_snap: int = 0
    guide_rejected_overlap: int = 0
    guide_overlap_viable_connectors: int = 0
    guide_reconstructed_states: int = 0
    guide_nonmaterial_states: int = 0
    guide_qualifying_states: int = 0
    guide_best_improvement_m: float = 0.0
    viable_connectors: int = 0
    states_reconstructed: int = 0
    states_targeted_improvement: int = 0
    best_targeted_improvement_m: float = 0.0
    best_distance_change_m: float = 0.0
    complete_states_evaluated: int = 0
    rejected_no_path: int = 0
    rejected_infeasible: int = 0
    rejected_coverage: int = 0
    rejected_profile: int = 0
    rejected_distance: int = 0
    complete_states_improved: int = 0
    archived_states: int = 0
    published_states: int = 0
    final_reason: SpurFinalReason = "unsupported_spur"

    def safe_dict(self) -> dict[str, Any]:
        return {
            "stop_names": self.names,
            "source_repeated_distance_m": self.source_repeated_distance_m,
            "rejoin_positions_generated": self.rejoin_positions_generated,
            "connector_requests": self.connector_requests,
            "connector_paths_returned": self.connector_paths_returned,
            "rejected_inbound_overlap": self.rejected_inbound_overlap,
            "ordinary_connector_paths": self.ordinary_connector_paths,
            "ordinary_rejected_overlap": self.ordinary_rejected_overlap,
            "ordinary_overlap_viable_connectors": (
                self.ordinary_overlap_viable_connectors
            ),
            "ordinary_reconstructed_states": self.ordinary_reconstructed_states,
            "ordinary_nonmaterial_states": self.ordinary_nonmaterial_states,
            "ordinary_qualifying_states": self.ordinary_qualifying_states,
            "ordinary_best_improvement_m": self.ordinary_best_improvement_m,
            "avoidance_supported": self.avoidance_supported,
            "avoidance_requests": self.avoidance_requests,
            "avoidance_paths_returned": self.avoidance_paths_returned,
            "avoidance_rejected_overlap": self.avoidance_rejected_overlap,
            "avoidance_overlap_viable_connectors": (
                self.avoidance_overlap_viable_connectors
            ),
            "avoidance_reconstructed_states": self.avoidance_reconstructed_states,
            "avoidance_nonmaterial_states": self.avoidance_nonmaterial_states,
            "avoidance_qualifying_states": self.avoidance_qualifying_states,
            "avoidance_best_improvement_m": self.avoidance_best_improvement_m,
            "guide_candidates_generated": self.guide_candidates_generated,
            "guide_route_attempts": self.guide_route_attempts,
            "guide_paths_returned": self.guide_paths_returned,
            "guide_rejected_snap": self.guide_rejected_snap,
            "guide_rejected_overlap": self.guide_rejected_overlap,
            "guide_overlap_viable_connectors": self.guide_overlap_viable_connectors,
            "guide_reconstructed_states": self.guide_reconstructed_states,
            "guide_nonmaterial_states": self.guide_nonmaterial_states,
            "guide_qualifying_states": self.guide_qualifying_states,
            "guide_best_improvement_m": self.guide_best_improvement_m,
            "viable_connectors": self.viable_connectors,
            "states_reconstructed": self.states_reconstructed,
            "states_targeted_improvement": self.states_targeted_improvement,
            "best_targeted_improvement_m": self.best_targeted_improvement_m,
            "best_distance_change_m": self.best_distance_change_m,
            "complete_states_evaluated": self.complete_states_evaluated,
            "rejected_no_path": self.rejected_no_path,
            "rejected_infeasible": self.rejected_infeasible,
            "rejected_coverage": self.rejected_coverage,
            "rejected_profile": self.rejected_profile,
            "rejected_distance": self.rejected_distance,
            "complete_states_improved": self.complete_states_improved,
            "archived_states": self.archived_states,
            "published_states": self.published_states,
            "final_reason": self.final_reason,
        }


@dataclass
class GlobalOptimizationDiagnostics:
    """Mutable counters owned by one planning request and snapshotted once."""

    graphhopper_call_limit: int
    complete_evaluation_limit: int
    source_states: int = 0
    initial_states: int = 0
    unique_path_options: int = 0
    lazy_path_requests: int = 0
    lazy_paths_returned: int = 0
    negative_path_results: int = 0
    graphhopper_calls_used: int = 0
    graphhopper_cache_hits: int = 0
    graphhopper_negative_cache_hits: int = 0
    iterations: int = 0
    proposals_generated: int = 0
    descriptors_selected: int = 0
    path_requests: int = 0
    states_reconstructed: int = 0
    operator_attempts: dict[OptimizationOperatorKind, int] = field(
        default_factory=lambda: {operator: 0 for operator in OPERATORS}
    )
    operator_acceptances: dict[OptimizationOperatorKind, int] = field(
        default_factory=lambda: {operator: 0 for operator in OPERATORS}
    )
    operator_best_improvements: dict[OptimizationOperatorKind, int] = field(
        default_factory=lambda: {operator: 0 for operator in OPERATORS}
    )
    accepted_moves: int = 0
    improving_moves: int = 0
    states_pruned_infeasible: int = 0
    states_pruned_coverage: int = 0
    states_pruned_profile: int = 0
    states_pruned_distance_maximum: int = 0
    complete_evaluations: int = 0
    feasible_evaluated_candidates: int = 0
    archive_candidates: int = 0
    published_candidates: int = 0
    single_repair_actions: int = 0
    composition_actions_considered: int = 0
    composition_pairs_considered: int = 0
    composition_triples_considered: int = 0
    composition_incompatible_same_leg: int = 0
    composition_incompatible_overlap: int = 0
    composition_states_built: int = 0
    composition_states_rejected_hard: int = 0
    composition_states_rejected_target_loss: int = 0
    composition_states_qualifying: int = 0
    composition_states_archived: int = 0
    composition_states_evaluated: int = 0
    composition_states_published: int = 0
    best_composed_target_count: int = 0
    best_composed_targeted_improvement_m: float = 0.0
    best_opposite_direction_improvement_m: float = 0.0
    best_repetition_improvement_m: float = 0.0
    best_backtracking_improvement_m: float = 0.0
    best_distance_change_m: float = 0.0
    time_limit_reached: bool = False
    budget_exhausted: bool = False
    wall_time_ms: float = 0.0
    routing_wait_time_ms: float = 0.0
    optimization_cpu_time_ms: float = 0.0
    _spurs: dict[str, _SpurAccumulator] = field(default_factory=dict)

    def register_spur_target(
        self, target: SpurOptimizationTarget, *, rejoin_positions: int
    ) -> None:
        value = self._spurs.setdefault(
            target.stable_id,
            _SpurAccumulator(
                stable_id=target.stable_id,
                source_candidate_id=target.source_candidate_id,
                spur_id=target.spur_id,
                names=target.stop_names,
                source_repeated_distance_m=target.repeated_distance_m,
            ),
        )
        value.rejoin_positions_generated = rejoin_positions
        value.final_reason = (
            "no_downstream_rejoin" if rejoin_positions == 0 else "no_connector_path"
        )

    def record_spur_connectors(
        self, stable_id: str, *, returned: int, rejected_overlap: int = 0
    ) -> None:
        value = self._spurs[stable_id]
        value.connector_requests += 1
        value.connector_paths_returned += returned
        value.rejected_inbound_overlap += rejected_overlap
        value.ordinary_connector_paths += returned
        value.ordinary_rejected_overlap += rejected_overlap
        if returned == rejected_overlap and returned > 0:
            value.final_reason = "ordinary_paths_reused_corridor"

    def record_avoidance(
        self,
        stable_id: str,
        *,
        supported: bool,
        requested: bool,
        returned: int,
        rejected_overlap: int,
    ) -> None:
        value = self._spurs[stable_id]
        value.avoidance_supported = supported
        value.avoidance_requests += int(requested)
        value.avoidance_paths_returned += returned
        value.avoidance_rejected_overlap += rejected_overlap
        value.connector_requests += int(requested)
        value.connector_paths_returned += returned
        value.rejected_inbound_overlap += rejected_overlap
        if not supported:
            value.final_reason = "avoidance_unsupported"
        elif requested and returned == 0:
            value.final_reason = "avoidance_no_path"
        elif returned == rejected_overlap:
            value.final_reason = "avoidance_paths_reused_corridor"

    def record_avoidance_capability(self, stable_id: str, supported: bool) -> None:
        self._spurs[stable_id].avoidance_supported = supported

    def record_guides(
        self,
        stable_id: str,
        *,
        generated: int = 0,
        attempts: int = 0,
        returned: int = 0,
        rejected_snap: int = 0,
        rejected_overlap: int = 0,
    ) -> None:
        value = self._spurs[stable_id]
        value.guide_candidates_generated += generated
        value.guide_route_attempts += attempts
        value.guide_paths_returned += returned
        value.guide_rejected_snap += rejected_snap
        value.guide_rejected_overlap += rejected_overlap
        value.connector_requests += attempts
        value.connector_paths_returned += returned
        value.rejected_inbound_overlap += rejected_overlap
        if attempts and returned == 0:
            value.final_reason = "guide_points_unrouteable"
        elif returned and returned == rejected_overlap:
            value.final_reason = "guide_paths_reused_corridor"

    def record_connector_strategy_evaluation(
        self,
        stable_id: str,
        strategy: ConnectorGenerationStrategy,
        *,
        overlap_viable: int,
        reconstructed: int,
        nonmaterial: int,
        qualifying: int,
        best_improvement_m: float,
        best_distance_change_m: float,
    ) -> None:
        """Record actual reconstructed outcomes, not generation viability alone."""
        value = self._spurs[stable_id]
        if strategy == "ordinary_alternative":
            value.ordinary_overlap_viable_connectors += overlap_viable
            value.ordinary_reconstructed_states += reconstructed
            value.ordinary_nonmaterial_states += nonmaterial
            value.ordinary_qualifying_states += qualifying
            value.ordinary_best_improvement_m = max(
                value.ordinary_best_improvement_m, best_improvement_m
            )
        elif strategy == "custom_model_corridor_avoidance":
            value.avoidance_overlap_viable_connectors += overlap_viable
            value.avoidance_reconstructed_states += reconstructed
            value.avoidance_nonmaterial_states += nonmaterial
            value.avoidance_qualifying_states += qualifying
            value.avoidance_best_improvement_m = max(
                value.avoidance_best_improvement_m, best_improvement_m
            )
        else:
            value.guide_overlap_viable_connectors += overlap_viable
            value.guide_reconstructed_states += reconstructed
            value.guide_nonmaterial_states += nonmaterial
            value.guide_qualifying_states += qualifying
            value.guide_best_improvement_m = max(
                value.guide_best_improvement_m, best_improvement_m
            )
        value.viable_connectors += overlap_viable
        value.states_reconstructed += reconstructed
        value.states_targeted_improvement += qualifying
        value.best_targeted_improvement_m = max(
            value.best_targeted_improvement_m, best_improvement_m
        )
        if best_improvement_m >= value.best_targeted_improvement_m:
            value.best_distance_change_m = best_distance_change_m
        if qualifying:
            value.final_reason = "archive_dominated"
        elif nonmaterial:
            if strategy == "ordinary_alternative":
                value.final_reason = "ordinary_no_material_repair"
            elif strategy == "custom_model_corridor_avoidance":
                value.final_reason = "avoidance_no_material_repair"
            else:
                value.final_reason = "guide_no_material_repair"

    def record_spur_rejection(self, stable_id: str | None, reason: str) -> None:
        if stable_id is None or stable_id not in self._spurs:
            return
        value = self._spurs[stable_id]
        if reason == "no_path":
            value.rejected_no_path += 1
            value.final_reason = "no_connector_path"
        elif reason == "coverage":
            value.rejected_coverage += 1
            value.final_reason = "coverage_regression"
        elif reason == "profile":
            value.rejected_profile += 1
            value.final_reason = "profile_regression"
        elif reason == "distance":
            value.rejected_distance += 1
            value.final_reason = "explicit_maximum"
        else:
            value.rejected_infeasible += 1
            value.final_reason = "reconstruction_failed"

    def record_spur_outcome(
        self,
        stable_id: str | None,
        *,
        improved: bool = False,
        archived: bool = False,
        published: bool = False,
    ) -> None:
        if stable_id is None or stable_id not in self._spurs:
            return
        value = self._spurs[stable_id]
        value.complete_states_improved += int(improved)
        value.archived_states += int(archived)
        value.published_states += int(published)
        if published:
            value.final_reason = "published"
        elif archived:
            value.final_reason = "portfolio_excluded"

    def record_published_spur_ids(
        self,
        source_candidate_id: str,
        spur_ids: tuple[str, ...],
    ) -> int:
        """Mark every registered target confirmed by final public PR19 analysis."""
        published = 0
        for value in self._spurs.values():
            if (
                value.source_candidate_id == source_candidate_id
                and value.spur_id in spur_ids
            ):
                self.record_spur_outcome(value.stable_id, published=True)
                published += 1
        return published

    def set_spur_reason(self, stable_id: str, reason: SpurFinalReason) -> None:
        if stable_id in self._spurs:
            self._spurs[stable_id].final_reason = reason

    def record_spur_evaluation(self, stable_id: str | None) -> None:
        if stable_id is not None and stable_id in self._spurs:
            self._spurs[stable_id].complete_states_evaluated += 1

    def as_dict(self) -> dict[str, Any]:
        timings = (
            self.wall_time_ms,
            self.routing_wait_time_ms,
            self.optimization_cpu_time_ms,
        )
        if any(not isfinite(value) or value < 0 for value in timings):
            raise ValueError("optimizer timing diagnostics must be finite")
        result = {
            item.name: (
                dict(value)
                if isinstance((value := getattr(self, item.name)), dict)
                else value
            )
            for item in fields(self)
            if not item.name.startswith("_")
        }
        result.update(
            {
                "complete_evaluations_used": self.complete_evaluations,
                "targeted_spurs": tuple(
                    self._spurs[key].safe_dict() for key in sorted(self._spurs)
                ),
            }
        )
        return result
