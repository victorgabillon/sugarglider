"""FastAPI dependency accessors."""

from typing import Annotated

from fastapi import Depends, Request

from sugarglider.generation.service import RouteGenerationService
from sugarglider.routing.service import RouteService


def get_route_service(request: Request) -> RouteService:
    """Return the application-scoped route service."""
    service: RouteService = request.app.state.route_service
    return service


RouteServiceDependency = Annotated[RouteService, Depends(get_route_service)]


def get_generation_service(request: Request) -> RouteGenerationService:
    """Return the application-scoped target-distance generation service."""
    service: RouteGenerationService = request.app.state.generation_service
    return service


GenerationServiceDependency = Annotated[
    RouteGenerationService, Depends(get_generation_service)
]
