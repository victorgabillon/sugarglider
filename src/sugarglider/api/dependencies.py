"""FastAPI dependency accessors."""

from typing import Annotated

from fastapi import Depends, Header, Request

from sugarglider.outings.service import OutingOperations
from sugarglider.planning.pipeline import PlanService
from sugarglider.routing.service import RouteService
from sugarglider.saved_routes.service import SavedRouteOperations


def get_route_service(request: Request) -> RouteService:
    """Return the application-scoped route service."""
    service: RouteService = request.app.state.route_service
    return service


RouteServiceDependency = Annotated[RouteService, Depends(get_route_service)]


def get_plan_service(request: Request) -> PlanService:
    """Return the canonical application-scoped planning service."""
    service: PlanService = request.app.state.plan_service
    return service


PlanServiceDependency = Annotated[PlanService, Depends(get_plan_service)]


def get_saved_route_service(request: Request) -> SavedRouteOperations:
    """Return the application-scoped immutable snapshot service."""
    service: SavedRouteOperations = request.app.state.saved_route_service
    return service


SavedRouteServiceDependency = Annotated[
    SavedRouteOperations, Depends(get_saved_route_service)
]


def get_outing_service(request: Request) -> OutingOperations:
    """Return the application-scoped shared-outing service."""
    service: OutingOperations = request.app.state.outing_service
    return service


OutingServiceDependency = Annotated[OutingOperations, Depends(get_outing_service)]


def authorize_outing_join(
    slug: str,
    outings: OutingServiceDependency,
    join_token: Annotated[
        str | None,
        Header(alias="X-Sugarglider-Outing-Join-Token"),
    ] = None,
) -> str | None:
    """Authorize a join before FastAPI validates its request body fields."""
    outings.authorize_join(slug, join_token)
    return join_token


AuthorizedOutingJoinTokenDependency = Annotated[
    str | None,
    Depends(authorize_outing_join),
]
