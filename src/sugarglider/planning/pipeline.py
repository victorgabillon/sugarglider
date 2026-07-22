"""Canonical planning orchestration and shared publication invariants."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sugarglider.planning.diagnostics import PlanSearchDiagnostics
from sugarglider.planning.models import AutoTourPlanRequest, PlanRequest
from sugarglider.planning.portfolio import build_portfolio
from sugarglider.planning.result import PlanCandidate, PlanResult
from sugarglider.planning.validation import (
    CandidateEvaluationError,
    validate_search_candidate,
)

if TYPE_CHECKING:
    from sugarglider.planning.auto_tour.service import AutoTourPlanner
    from sugarglider.planning.direction.models import (
        ReversePlanRequest,
        ReversePlanResponse,
    )
    from sugarglider.planning.direction.service import ReversePlanner
    from sugarglider.planning.models import PlanRequestBase
    from sugarglider.planning.waypoint.service import WaypointPlanner


@dataclass(frozen=True)
class EvaluatedPortfolio:
    """Valid published candidates and explicit producer-draft rejections."""

    candidates: tuple[PlanCandidate, ...]
    rejection_reasons: tuple[str, ...]

    def attach_rejections(
        self, diagnostics: PlanSearchDiagnostics
    ) -> PlanSearchDiagnostics:
        """Expose every canonical rejection without hiding producer diagnostics."""
        if not self.rejection_reasons:
            return diagnostics
        return diagnostics.model_copy(
            update={
                "warnings": tuple(
                    sorted({*diagnostics.warnings, *self.rejection_reasons})
                )
            }
        )


def evaluate_candidate_portfolio(
    request: PlanRequestBase,
    candidates: tuple[PlanCandidate, ...],
    *,
    limit: int,
    ranking_key: Callable[[PlanCandidate], tuple[object, ...]] | None = None,
) -> EvaluatedPortfolio:
    """Validate every routed draft before shared deduplication and role assignment."""
    valid: list[PlanCandidate] = []
    rejections: list[str] = []
    for candidate in candidates:
        try:
            valid.append(validate_search_candidate(request, candidate))
        except CandidateEvaluationError as exc:
            rejections.append(f"candidate_rejected:{candidate.id}:{exc}")
    return EvaluatedPortfolio(
        candidates=build_portfolio(tuple(valid), limit=limit, ranking_key=ranking_key),
        rejection_reasons=tuple(rejections),
    )


class PlanService:
    """Dispatch one strict request union to mode-specific candidate producers."""

    def __init__(
        self,
        *,
        auto_tour: AutoTourPlanner,
        waypoint: WaypointPlanner,
        reverse: ReversePlanner,
    ) -> None:
        self._auto_tour = auto_tour
        self._waypoint = waypoint
        self._reverse = reverse

    async def generate(self, request: PlanRequest) -> PlanResult:
        if isinstance(request, AutoTourPlanRequest):
            return await self._auto_tour.generate(request)
        return await self._waypoint.generate(request)

    async def reverse(self, request: ReversePlanRequest) -> ReversePlanResponse:
        return await self._reverse.reverse(request)
