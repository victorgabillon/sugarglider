"""Stable public error responses for expected application failures."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from sugarglider.generation.service import (
    RouteGenerationNoCandidateError,
    TargetDistanceInfeasibleError,
)
from sugarglider.pois.errors import PoiSearchLimitError
from sugarglider.routing.graphhopper import (
    RoutingPointError,
    RoutingTimeoutError,
    RoutingUnavailableError,
    RoutingUpstreamError,
)
from sugarglider.tours.service import AutoTourNoCandidateError


class RouteVisualizationError(ValueError):
    """A posted route cannot be projected into valid map sections."""


@dataclass(frozen=True)
class PublicError:
    status_code: int
    code: str
    message: str


ERRORS: dict[type[Exception], PublicError] = {
    AutoTourNoCandidateError: PublicError(
        422,
        "auto_tour_no_candidate",
        "No graph-valid Auto Tour control candidate was found.",
    ),
    PoiSearchLimitError: PublicError(
        422,
        "poi_limit_exceeded",
        "The requested POI result limit exceeds the configured maximum.",
    ),
    RouteVisualizationError: PublicError(
        422,
        "route_visualization_invalid",
        "The route result cannot be projected for visualization.",
    ),
    TargetDistanceInfeasibleError: PublicError(
        422,
        "target_distance_infeasible",
        "The mandatory route is already longer than the target tolerance.",
    ),
    RouteGenerationNoCandidateError: PublicError(
        422,
        "route_generation_no_candidate",
        "No graph-valid generated route candidate was found.",
    ),
    RoutingPointError: PublicError(
        400,
        "routing_point_not_found",
        "One or more route points could not be matched to the hiking network.",
    ),
    RoutingUpstreamError: PublicError(
        502,
        "routing_upstream_invalid",
        "The routing engine returned an invalid response.",
    ),
    RoutingUnavailableError: PublicError(
        503,
        "routing_unavailable",
        "The routing engine is currently unavailable.",
    ),
    RoutingTimeoutError: PublicError(
        504,
        "routing_timeout",
        "The routing engine did not respond in time.",
    ),
}


def _response(error: PublicError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"error": {"code": error.code, "message": error.message}},
    )


def install_error_handlers(app: FastAPI) -> None:
    """Install handlers without leaking internal exception details."""

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        _request: Request, _exception: RequestValidationError
    ) -> JSONResponse:
        return _response(
            PublicError(422, "invalid_request", "The route request is invalid.")
        )

    for exception_type, public_error in ERRORS.items():

        def make_handler(
            error: PublicError,
        ) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
            async def handler(_request: Request, _exception: Exception) -> JSONResponse:
                return _response(error)

            return handler

        app.add_exception_handler(exception_type, make_handler(public_error))
