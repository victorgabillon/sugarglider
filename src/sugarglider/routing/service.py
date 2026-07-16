"""Application service coordinating ordinary route requests."""

from sugarglider.domain.models import RouteRequest, RouteResult
from sugarglider.routing.graphhopper import GraphHopperClient
from sugarglider.routing.result import RouteResultFactory


class RouteService:
    """Compute typed routes and expose GraphHopper readiness."""

    def __init__(
        self,
        graphhopper: GraphHopperClient,
        result_factory: RouteResultFactory | None = None,
    ) -> None:
        self._graphhopper = graphhopper
        self._result_factory = result_factory or RouteResultFactory()

    async def route(self, request: RouteRequest) -> RouteResult:
        """Route all request anchors in order on the hiking network."""
        path = await self._graphhopper.route(tuple(request.points), request.profile)
        return self._result_factory.create(
            name=request.name,
            path=path,
            input_point_count=request.input_point_count,
        )

    async def ready(self) -> bool:
        """Return whether the required GraphHopper profile is loaded."""
        return await self._graphhopper.is_ready("hike")
