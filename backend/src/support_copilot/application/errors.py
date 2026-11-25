class InvalidChatRequest(ValueError):
    pass


class RetrievalUnavailable(RuntimeError):
    pass


class GenerationUnavailable(RuntimeError):
    pass


class Unauthorized(Exception):
    """No valid signed-in user (HTTP 401)."""


class Forbidden(Exception):
    """Role or ownership does not allow this (HTTP 403)."""


class NotFound(Exception):
    """Missing, or in another account (HTTP 404)."""


class Conflict(Exception):
    """The current state does not allow this (HTTP 409)."""


class Unprocessable(ValueError):
    """Well-formed but invalid input (HTTP 422)."""


class ServiceUnavailable(RuntimeError):
    """The database is unreachable or not configured (HTTP 503)."""
