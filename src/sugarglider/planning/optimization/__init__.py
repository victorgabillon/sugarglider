"""Shared edge-aware global tour optimizer."""

from sugarglider.planning.optimization.adapters import (
    optimization_source,
    requested_outcomes_regress,
)
from sugarglider.planning.optimization.diagnostics import (
    GlobalOptimizationDiagnostics,
)
from sugarglider.planning.optimization.models import (
    GlobalOptimizationSettings,
    OptimizationAnchor,
    OptimizationDraft,
    OptimizationMove,
    OptimizationResult,
    OptimizationSource,
    PathOption,
    RejoinPosition,
    SpurOptimizationTarget,
    TourObjective,
    TourOptimizationState,
)
from sugarglider.planning.optimization.optimizer import optimize_tours
from sugarglider.planning.optimization.progress import normalized_anchor_progress
from sugarglider.planning.optimization.source_models import (
    SemanticOptimizationSource,
    SemanticRoutingAnchor,
)

__all__ = [
    "GlobalOptimizationDiagnostics",
    "GlobalOptimizationSettings",
    "OptimizationAnchor",
    "OptimizationDraft",
    "OptimizationMove",
    "OptimizationResult",
    "OptimizationSource",
    "PathOption",
    "RejoinPosition",
    "SemanticOptimizationSource",
    "SemanticRoutingAnchor",
    "SpurOptimizationTarget",
    "TourObjective",
    "TourOptimizationState",
    "optimization_source",
    "optimize_tours",
    "normalized_anchor_progress",
    "requested_outcomes_regress",
]
