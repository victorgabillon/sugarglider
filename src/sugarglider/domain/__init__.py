"""Domain models."""

from sugarglider.domain.analysis import (
    DetailBreakdown,
    DetailBucket,
    DistanceMetric,
    RepetitionAnalysis,
    RouteAnalysis,
)
from sugarglider.domain.generation import (
    CandidateScore,
    GeneratedCandidate,
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
    "DetailBreakdown",
    "DetailBucket",
    "DistanceMetric",
    "GeneratedCandidate",
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
