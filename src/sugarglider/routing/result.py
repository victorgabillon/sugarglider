"""Shared conversion from routed paths to analyzed public route results."""

from sugarglider.analysis.route import RouteAnalysisError, RouteAnalyzer
from sugarglider.domain.models import RouteResult, RouteSummary
from sugarglider.routing.backend import RoutedPath
from sugarglider.routing.errors import RoutingUpstreamError
from sugarglider.routing.profiles import (
    RoutingProfileId,
)
from sugarglider.routing.profiles import (
    routing_profile as get_routing_profile,
)


class RouteResultFactory:
    """Analyze and expose a backend path without duplicating service logic."""

    def __init__(self, analyzer: RouteAnalyzer | None = None) -> None:
        self._analyzer = analyzer or RouteAnalyzer()

    def create(
        self,
        *,
        name: str,
        path: RoutedPath,
        input_point_count: int,
        routing_profile: RoutingProfileId,
    ) -> RouteResult:
        try:
            analysis = self._analyzer.analyze(
                path.geometry,
                path.distance_m,
                path.details,
                activity_kind=get_routing_profile(routing_profile).activity_kind,
            )
        except RouteAnalysisError as exc:
            raise RoutingUpstreamError(
                "GraphHopper returned route details that cannot be analyzed"
            ) from exc
        return RouteResult(
            name=name,
            routing_profile=routing_profile,
            summary=RouteSummary(
                distance_m=path.distance_m,
                duration_ms=path.duration_ms,
                ascend_m=path.ascend_m,
                descend_m=path.descend_m,
                input_point_count=input_point_count,
                routed_point_count=len(path.geometry),
            ),
            geometry=path.geometry,
            snapped_points=path.snapped_points,
            path_details=dict(path.details),
            analysis=analysis,
        )
