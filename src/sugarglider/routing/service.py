"""Application service for ordinary routing and profile availability."""

from sugarglider.domain.models import RouteRequest, RouteResult
from sugarglider.routing.errors import (
    RoutingError,
    RoutingProfileUnavailableError,
)
from sugarglider.routing.graphhopper import GraphHopperClient
from sugarglider.routing.profiles import (
    ROUTING_PROFILES,
    RoutingProfileCatalog,
    RoutingProfileId,
    routing_profile_catalog,
)
from sugarglider.routing.result import RouteResultFactory


class RouteService:
    """Compute routes and own one safe cached GraphHopper availability snapshot."""

    def __init__(
        self,
        graphhopper: GraphHopperClient,
        result_factory: RouteResultFactory | None = None,
    ) -> None:
        self._graphhopper = graphhopper
        self._result_factory = result_factory or RouteResultFactory()
        self._available_backend_profiles: frozenset[str] | None = None

    async def route(self, request: RouteRequest) -> RouteResult:
        path = await self._graphhopper.route(tuple(request.points), request.profile)
        return self._result_factory.create(
            name=request.name,
            path=path,
            input_point_count=request.input_point_count,
            routing_profile=request.profile,
        )

    async def refresh_profile_catalog(self) -> RoutingProfileCatalog:
        try:
            available = await self._graphhopper.available_profiles()
        except RoutingError:
            self._available_backend_profiles = None
            return routing_profile_catalog(frozenset(), upstream_warning=True)
        self._available_backend_profiles = available
        return routing_profile_catalog(available)

    async def profile_catalog(self) -> RoutingProfileCatalog:
        if self._available_backend_profiles is None:
            return await self.refresh_profile_catalog()
        return routing_profile_catalog(self._available_backend_profiles)

    async def ensure_profile_available(self, profile: RoutingProfileId) -> None:
        catalog = await self.profile_catalog()
        status = next(
            value for value in catalog.profiles if value.profile.id == profile
        )
        if not status.available:
            raise RoutingProfileUnavailableError(profile)

    async def ready(self) -> bool:
        """Refresh availability; packaged readiness requires all six profiles."""
        catalog = await self.refresh_profile_catalog()
        required = {profile.id for profile in ROUTING_PROFILES}
        available = {
            status.profile.id for status in catalog.profiles if status.available
        }
        return available == required
