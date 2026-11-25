"""The one place domain errors become HTTP responses."""

import json

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from support_copilot.application.errors import (
    Conflict,
    Forbidden,
    NotFound,
    ServiceUnavailable,
    Unauthorized,
    Unprocessable,
)

_UNAVAILABLE = "The service is temporarily unavailable."
_STATUS = {
    Unauthorized: (401, "Authentication required."),
    Forbidden: (403, "Not allowed."),
    NotFound: (404, "Not found."),
    Conflict: (409, "The current state does not allow this."),
    Unprocessable: (422, None),
    ServiceUnavailable: (503, _UNAVAILABLE),
    # Details of connection failures can contain hosts or credentials: never echo.
    psycopg.OperationalError: (503, _UNAVAILABLE),
}


def register(app: FastAPI) -> None:
    for exc_type, (status, message) in _STATUS.items():

        def handler(_: Request, exc: Exception, status=status, message=message):
            detail = message or (str(exc) or "Invalid input.")
            return JSONResponse({"detail": detail}, status_code=status)

        app.add_exception_handler(exc_type, handler)

    app.add_exception_handler(RequestValidationError, _invalid_request)


def _invalid_request(_: Request, exc: RequestValidationError) -> Response:
    # The default handler echoes `input`, which can hold NaN or lone surrogates
    # that cannot be encoded. Keep only type, loc and msg, escaped to ASCII.
    detail = [
        {"type": e["type"], "loc": list(e["loc"]), "msg": e["msg"]}
        for e in exc.errors()
    ]
    return Response(
        json.dumps({"detail": detail}, ensure_ascii=True),
        status_code=422,
        media_type="application/json",
    )
