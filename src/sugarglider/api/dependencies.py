"""FastAPI dependency accessors."""

from typing import Annotated

from fastapi import Depends, Request

from sugarglider.planning.pipeline import PlanService
from sugarglider.routing.service import RouteService


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
