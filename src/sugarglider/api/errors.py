"""Stable public error responses for expected application failures."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from sugarglider.routing.graphhopper import (
    RoutingPointError,
    RoutingTimeoutError,
    RoutingUnavailableError,
    RoutingUpstreamError,
)


@dataclass(frozen=True)
class PublicError:
    status_code: int
    code: str
    message: str


ERRORS: dict[type[Exception], PublicError] = {
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
