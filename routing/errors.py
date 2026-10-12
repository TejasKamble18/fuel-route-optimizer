from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .geocoding import GeocodingError
from .optimizer import OptimizationError, RangeGap
from .ors_client import NoRouteFound, ORSError, ORSTimeout

DOMAIN_ERRORS = (GeocodingError, OptimizationError, ORSError)


def error_response(http_status: int, code: str, detail, **extra) -> Response:
    return Response({"error": code, "detail": detail, **extra}, status=http_status)


def domain_error_response(exc: Exception) -> Response:
    if isinstance(exc, GeocodingError):
        return error_response(status.HTTP_404_NOT_FOUND, exc.code, str(exc))
    if isinstance(exc, RangeGap):
        return error_response(422, exc.code, str(exc),
                              from_mile=round(exc.from_mile, 1), to_mile=round(exc.to_mile, 1))
    if isinstance(exc, OptimizationError):
        return error_response(422, exc.code, str(exc))
    if isinstance(exc, NoRouteFound):
        return error_response(422, "no_route", f"No truck route found between these locations: {exc}")
    if isinstance(exc, ORSTimeout):
        return error_response(status.HTTP_504_GATEWAY_TIMEOUT, "routing_timeout", str(exc))
    detail = str(exc)
    if getattr(exc, "status", None) in (401, 403):
        detail = "The routing service rejected the API key. Check ORS_API_KEY."
    return error_response(status.HTTP_502_BAD_GATEWAY, "routing_error", detail)


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None
    if isinstance(exc, ValidationError):
        response.data = {"error": "invalid_input", "detail": response.data}
    else:
        data = response.data
        detail = data.get("detail", data) if isinstance(data, dict) else data
        response.data = {"error": getattr(exc, "default_code", "error"), "detail": detail}
    return response
