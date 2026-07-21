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
    "DetailBreakdown",
    "DetailBucket",
    "DistanceMetric",
    "LoopGeometryAnalysis",
    "LoopGeometryPenaltyBreakdown",
    "PathDetailSegment",
    "RepetitionAnalysis",
    "RouteAnalysis",
    "RouteRequest",
    "RouteResult",
    "RouteSummary",
    "RouteTopology",
    "ResolvedEndpoints",
]
