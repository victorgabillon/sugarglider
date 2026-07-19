"""Domain models."""

from sugarglider.domain.analysis import (
    DetailBreakdown,
    DetailBucket,
    DistanceMetric,
    LoopGeometryAnalysis,
    LoopGeometryPenaltyBreakdown,
    RepetitionAnalysis,
    RouteAnalysis,
)
from sugarglider.domain.endpoints import (
    EndpointSource,
    EndpointVisit,
    ResolvedEndpoints,
    RouteTopology,
)
from sugarglider.domain.generation import (
    CandidateConstruction,
    CandidateScore,
    GeneratedCandidate,
    LoopGeometryPreference,
    PathSelectionMode,
    RequiredPointVisit,
    RouteGenerationRequest,
    RouteGenerationResult,
    SearchSummary,
)
from sugarglider.domain.models import (
    Coordinate,
    PathDetailSegment,
    RouteRequest,
    RouteResult,
    RouteSummary,
)

__all__ = [
    "Coordinate",
    "EndpointSource",
    "EndpointVisit",
    "CandidateScore",
    "CandidateConstruction",
    "DetailBreakdown",
    "DetailBucket",
    "DistanceMetric",
    "GeneratedCandidate",
    "LoopGeometryAnalysis",
    "LoopGeometryPenaltyBreakdown",
    "LoopGeometryPreference",
    "PathSelectionMode",
    "PathDetailSegment",
    "RepetitionAnalysis",
    "RequiredPointVisit",
    "RouteAnalysis",
    "RouteGenerationRequest",
    "RouteGenerationResult",
    "RouteRequest",
    "RouteResult",
    "RouteSummary",
    "RouteTopology",
    "ResolvedEndpoints",
    "SearchSummary",
]
