"""Strict public and bounded internal reverse-planning models."""

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field

from sugarglider.domain.models import Coordinate
from sugarglider.planning.models import CanonicalModel, PlanRequest
from sugarglider.planning.result import PlanCandidate, PlanResult


class ReversePlanRequest(CanonicalModel):
    schema_version: Literal[1]
    source_request: PlanRequest
    candidate: PlanCandidate
    candidate_count: Annotated[int, Field(ge=1, le=3)] = 1


class ReversePlanResponse(CanonicalModel):
    schema_version: Literal[1] = 1
    transformed_request: PlanRequest
    result: PlanResult
    source_candidate_id: str


@dataclass(frozen=True)
class InternalShapeAnchor:
    coordinate: Coordinate
    source_progress: float


@dataclass(frozen=True)
class ReverseRouteVariant:
    points: tuple[Coordinate, ...]
    exact_points: tuple[Coordinate, ...]
    exact_positions: tuple[int, ...]
    exact_ids: tuple[str, ...]
    shape_anchor_count: int
    shape_anchors_removed: int
