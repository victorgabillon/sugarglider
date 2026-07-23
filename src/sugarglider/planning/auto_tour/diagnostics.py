"""Immutable Auto Tour result and algorithm diagnostics."""

from typing import Annotated, Self

from pydantic import ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from sugarglider.domain.endpoints import (
    EndpointVisit,
    ResolvedRouteTopology,
)
from sugarglider.domain.models import Coordinate, ImmutableModel
from sugarglider.planning.auto_tour.candidate_models import AutoTourCandidate
from sugarglider.planning.auto_tour.models import (
    AutoTourSearchRequest,
    NonNegativeFloat,
    NonNegativeInt,
)
from sugarglider.planning.context import PlanningSearchContext
from sugarglider.planning.diagnostics import PlanSearchDiagnostics


class AutoTourTimings(ImmutableModel):
    isochrone_seconds: NonNegativeFloat
    skeleton_construction_seconds: NonNegativeFloat
    route_call_seconds: NonNegativeFloat
    poi_corridor_query_seconds: NonNegativeFloat
    poi_insertion_search_seconds: NonNegativeFloat
    local_repair_seconds: NonNegativeFloat
    total_seconds: NonNegativeFloat


class AutoTourSearchSummary(ImmutableModel):
    isochrone_request_count: Annotated[int, Field(ge=0, le=1)]
    round_trip_control_request_count: Annotated[int, Field(ge=0, le=8)]
    sampled_fallback_skeleton_count: NonNegativeInt = 0
    skeleton_route_request_count: Annotated[int, Field(ge=0, le=24)]
    skeleton_candidate_count: NonNegativeInt
    retained_skeleton_count: Annotated[int, Field(ge=0, le=6)]
    poi_index_candidate_count: NonNegativeInt
    already_collected_poi_count: NonNegativeInt
    poi_route_evaluation_count: Annotated[int, Field(ge=0, le=84)]
    requested_place_route_evaluations: Annotated[int, Field(ge=0, le=60)] = 0
    discovered_poi_route_evaluations: Annotated[int, Field(ge=0, le=24)] = 0
    requested_place_budget_exhausted: bool = False
    discovered_poi_budget_exhausted: bool = False
    local_repair_evaluation_count: Annotated[int, Field(ge=0, le=12)]
    corridor_repair_evaluation_count: Annotated[int, Field(ge=0, le=12)] = 0
    alternative_leg_request_count: Annotated[int, Field(ge=0, le=24)]
    total_route_request_budget: Annotated[int, Field(ge=1)]
    total_route_request_count: NonNegativeInt
    budget_exhausted: bool
    control_signature: str
    recommended_signature: str
    control_retained: bool
    selected_scenic_count: NonNegativeInt
    selected_verified_water_count: NonNegativeInt
    requested_place_selected_count: NonNegativeInt = 0
    requested_place_dropped_count: NonNegativeInt = 0
    approach_candidates_considered: NonNegativeInt = 0
    approach_route_evaluation_count: NonNegativeInt = 0
    through_route_evaluation_count: NonNegativeInt = 0
    spur_route_evaluation_count: NonNegativeInt = 0
    corridor_continuation_evaluation_count: NonNegativeInt = 0
    selected_excursion_count: NonNegativeInt = 0
    spatial_query_candidate_count: NonNegativeInt = 0
    considered_discovered_poi_count: NonNegativeInt = 0
    selected_discovered_poi_count: NonNegativeInt = 0
    dropped_discovered_poi_count: NonNegativeInt = 0
    selected_stop_count: NonNegativeInt = 0
    dropped_stop_count: NonNegativeInt = 0
    gpx_stop_count: NonNegativeInt = 0
    complete_set_candidate_distance_m: NonNegativeFloat | None = None
    full_set_route_attempted: bool = False
    full_set_route_succeeded: bool = False
    full_set_distance_m: NonNegativeFloat | None = None
    full_set_safety_eligible: bool | None = None
    full_set_rejection_reason: str | None = None
    maximum_distance_m: NonNegativeFloat = 0.0
    route_cache_hit_count: NonNegativeInt = 0
    timings: AutoTourTimings
    warnings: tuple[str, ...]

    @model_validator(mode="after")
    def validate_accounting(self) -> Self:
        if self.considered_discovered_poi_count != (
            self.selected_discovered_poi_count + self.dropped_discovered_poi_count
        ):
            raise ValueError("considered discovered POIs must be selected or dropped")
        if self.poi_route_evaluation_count != (
            self.requested_place_route_evaluations
            + self.discovered_poi_route_evaluations
        ):
            raise ValueError("requested and discovered POI evaluations must sum")
        # The shared budget snapshot is authoritative. These legacy per-family
        # fields omit control, approach, through-route and excursion phases and
        # therefore must not reconstruct the total.
        if self.total_route_request_count > self.total_route_request_budget:
            raise ValueError("Auto Tour exceeded its route-request budget")
        if self.corridor_repair_evaluation_count > self.local_repair_evaluation_count:
            raise ValueError("corridor repairs must be part of the local repair budget")
        if self.warnings != tuple(sorted(set(self.warnings))):
            raise ValueError("Auto Tour warnings must be sorted and unique")
        if self.full_set_route_succeeded and not self.full_set_route_attempted:
            raise ValueError("a successful full-set route must have been attempted")
        if self.full_set_route_succeeded != (self.full_set_distance_m is not None):
            raise ValueError("full-set success and distance must agree")
        if self.full_set_route_succeeded and self.full_set_safety_eligible is None:
            raise ValueError("a successful full-set route requires safety status")
        return self


class AutoTourSearchResult(ImmutableModel):
    """Recommended candidates plus the separately retained no-POI control."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    control: AutoTourCandidate
    candidates: tuple[AutoTourCandidate, ...]
    search: AutoTourSearchSummary
    diagnostics: PlanSearchDiagnostics
    topology: ResolvedRouteTopology = "loop"
    effective_start: Coordinate | None = None
    effective_end: Coordinate | None = None
    endpoint_visits: tuple[EndpointVisit, EndpointVisit] | tuple[()] = ()
    endpoint_warnings: tuple[str, ...] = ()
    import_warnings: tuple[str, ...] = ()
    search_context: SkipJsonSchema[PlanningSearchContext] = Field(
        exclude=True, repr=False
    )
    resolved_request: SkipJsonSchema[AutoTourSearchRequest] = Field(
        exclude=True, repr=False
    )

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.import_warnings != tuple(sorted(set(self.import_warnings))):
            raise ValueError("Auto Tour import warnings must be sorted and unique")
        if not self.candidates:
            raise ValueError("Auto Tour must return at least one candidate")
        if self.control.poi_visits and any(
            visit.inserted for visit in self.control.poi_visits
        ):
            raise ValueError("the retained control cannot contain inserted POIs")
        if self.search.control_signature != self.control.signature:
            raise ValueError("search control signature must match retained control")
        if self.search.recommended_signature != self.candidates[0].signature:
            raise ValueError("search recommendation must match rank one")
        if tuple(candidate.rank for candidate in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("Auto Tour candidate ranks must be contiguous")
        if len({candidate.signature for candidate in self.candidates}) != len(
            self.candidates
        ):
            raise ValueError("Auto Tour candidates must have unique signatures")
        return self
