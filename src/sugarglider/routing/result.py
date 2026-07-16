"""Shared conversion from routed paths to analyzed public route results."""

from sugarglider.analysis.route import RouteAnalysisError, RouteAnalyzer
from sugarglider.domain.models import RouteResult, RouteSummary
from sugarglider.routing.backend import RoutedPath
from sugarglider.routing.errors import RoutingUpstreamError


class RouteResultFactory:
    """Analyze and expose a backend path without duplicating service logic."""

    def __init__(self, analyzer: RouteAnalyzer | None = None) -> None:
        self._analyzer = analyzer or RouteAnalyzer()

    def create(
        self, *, name: str, path: RoutedPath, input_point_count: int
    ) -> RouteResult:
        try:
            analysis = self._analyzer.analyze(
                path.geometry, path.distance_m, path.details
            )
        except RouteAnalysisError as exc:
            raise RoutingUpstreamError(
                "GraphHopper returned route details that cannot be analyzed"
            ) from exc
        return RouteResult(
            name=name,
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
