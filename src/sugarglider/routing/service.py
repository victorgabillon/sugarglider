"""Application service coordinating domain requests and GraphHopper."""

from sugarglider.domain.models import RouteRequest, RouteResult, RouteSummary
from sugarglider.routing.graphhopper import GraphHopperClient


class RouteService:
    """Compute typed routes and expose GraphHopper readiness."""

    def __init__(self, graphhopper: GraphHopperClient) -> None:
        self._graphhopper = graphhopper

    async def route(self, request: RouteRequest) -> RouteResult:
        """Route all request anchors in order on the hiking network."""
        path = await self._graphhopper.route(tuple(request.points), request.profile)
        summary = RouteSummary(
            distance_m=path.distance_m,
            duration_ms=path.duration_ms,
            ascend_m=path.ascend_m,
            descend_m=path.descend_m,
            input_point_count=request.input_point_count,
            routed_point_count=len(path.geometry),
        )
        return RouteResult(
            name=request.name,
            summary=summary,
            geometry=path.geometry,
            snapped_points=path.snapped_points,
            path_details=path.details,
        )

    async def ready(self) -> bool:
        """Return whether the required GraphHopper profile is loaded."""
        return await self._graphhopper.is_ready("hike")
