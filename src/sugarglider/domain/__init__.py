"""Domain models."""

from sugarglider.domain.analysis import (
    DetailBreakdown,
    DetailBucket,
    DistanceMetric,
    RepetitionAnalysis,
    RouteAnalysis,
)
from sugarglider.domain.generation import (
    CandidateConstruction,
    CandidateScore,
    GeneratedCandidate,
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
    "CandidateScore",
    "CandidateConstruction",
    "DetailBreakdown",
    "DetailBucket",
    "DistanceMetric",
    "GeneratedCandidate",
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
    "SearchSummary",
]
