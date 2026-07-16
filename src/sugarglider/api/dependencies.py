"""FastAPI dependency accessors."""

from typing import Annotated

from fastapi import Depends, Request

from sugarglider.routing.service import RouteService


def get_route_service(request: Request) -> RouteService:
    """Return the application-scoped route service."""
    service: RouteService = request.app.state.route_service
    return service


RouteServiceDependency = Annotated[RouteService, Depends(get_route_service)]
