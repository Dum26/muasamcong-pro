"""Typed failures returned by the e-GP source layer."""


class SourceError(RuntimeError):
    code = "source_error"
    transient = False


class SourceTimeoutError(SourceError):
    code, transient = "timeout", True


class SourceConnectionError(SourceError):
    code, transient = "connection", True


class RateLimitError(SourceError):
    code, transient = "rate_limit", True


class ForbiddenError(SourceError):
    code = "forbidden"


class BadRequestError(SourceError):
    code = "bad_request"


class ServerError(SourceError):
    code, transient = "server", True


class InvalidResponseError(SourceError):
    code = "invalid_response"


class InvalidJsonError(InvalidResponseError):
    code = "invalid_json"


class SchemaChangedError(InvalidResponseError):
    code = "schema_changed"


class NotFoundError(SourceError):
    code = "not_found"


class PartialDataError(SourceError):
    code = "partial"


class CircuitOpenError(SourceError):
    code, transient = "circuit_open", True
