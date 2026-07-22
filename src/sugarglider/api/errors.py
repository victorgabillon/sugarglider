"""Stable public error responses for expected application failures."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from sugarglider.domain.endpoints import EndpointSnapTooFarError
from sugarglider.gpx.writer import SelectedStopNotReachedError
from sugarglider.planning.auto_tour.state import (
    AutoTourMaximumBelowDirectLowerBoundError,
    AutoTourNoCandidateError,
)
from sugarglider.planning.validation import ExactWaypointNotReachedError
from sugarglider.pois.errors import PoiSearchLimitError
from sugarglider.routing.graphhopper import (
    RoutingPointError,
    RoutingProfileUnavailableError,
    RoutingTimeoutError,
    RoutingUnavailableError,
    RoutingUpstreamError,
)


class RouteVisualizationError(ValueError):
    """A posted route cannot be projected into valid map sections."""


@dataclass(frozen=True)
class PublicError:
    status_code: int
    code: str
    message: str


class PublicErrorBody(BaseModel):
    """Stable safe fields exposed for one expected application failure."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str
    point_index: int | None = None
    point_name: str | None = None
    snap_distance_m: float | None = None
    maximum_snap_distance_m: float | None = None


ERRORS: dict[type[Exception], PublicError] = {
    AutoTourMaximumBelowDirectLowerBoundError: PublicError(
        422,
        "auto_tour_maximum_below_direct_lower_bound",
        "Maximum distance is below the graph-valid direct endpoint route.",
    ),
    EndpointSnapTooFarError: PublicError(
        422,
        "endpoint_snap_too_far",
        "A hard endpoint is too far from the routed hiking network.",
    ),
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
    SelectedStopNotReachedError: PublicError(
        422,
        "selected_stop_not_reached",
        "A selected stop is not within its required arrival tolerance of the track.",
    ),
    RoutingPointError: PublicError(
        400,
        "routing_point_not_found",
        "One or more route points could not be matched to the hiking network.",
    ),
    RoutingProfileUnavailableError: PublicError(
        503,
        "routing_profile_unavailable",
        "The selected routing profile is currently unavailable.",
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


def _response(
    error: PublicError,
    *,
    point_index: int | None = None,
    point_name: str | None = None,
    snap_distance_m: float | None = None,
    maximum_snap_distance_m: float | None = None,
) -> JSONResponse:
    body = PublicErrorBody(
        code=error.code,
        message=error.message,
        point_index=point_index,
        point_name=point_name,
        snap_distance_m=snap_distance_m,
        maximum_snap_distance_m=maximum_snap_distance_m,
    )
    return JSONResponse(
        status_code=error.status_code,
        content={"error": body.model_dump(mode="json", exclude_none=True)},
    )


def install_error_handlers(app: FastAPI) -> None:
    """Install handlers without leaking internal exception details."""

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        _request: Request, _exception: RequestValidationError
    ) -> JSONResponse:
        return _response(
            PublicError(
                422, "invalid_request", "The canonical plan request is invalid."
            )
        )

    @app.exception_handler(ExactWaypointNotReachedError)
    async def exact_waypoint_handler(
        _request: Request, exception: ExactWaypointNotReachedError
    ) -> JSONResponse:
        return _response(
            PublicError(
                422,
                "exact_waypoint_not_reached",
                (
                    "An exact mandatory waypoint is too far from the selected "
                    "routing network."
                ),
            ),
            point_index=exception.point_index,
            point_name=exception.point_name,
            snap_distance_m=exception.snap_distance_m,
            maximum_snap_distance_m=exception.maximum_snap_distance_m,
        )

    for exception_type, public_error in ERRORS.items():

        def make_handler(
            error: PublicError,
        ) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
            async def handler(_request: Request, _exception: Exception) -> JSONResponse:
                return _response(error)

            return handler

        app.add_exception_handler(exception_type, make_handler(public_error))
