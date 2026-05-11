"""Truthlock SDK error types."""

from __future__ import annotations
from typing import Any


class TruthlockError(Exception):
    """Base error for all Truthlock SDK errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}


class AuthenticationError(TruthlockError):
    """Raised when authentication fails (401/403)."""


class NotFoundError(TruthlockError):
    """Raised when a resource is not found (404)."""


class ValidationError(TruthlockError):
    """Raised when request validation fails (400/422)."""


class RateLimitError(TruthlockError):
    """Raised when rate limit is exceeded (429)."""

    def __init__(self, message: str, retry_after: float | None = None, **kwargs: Any):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ServerError(TruthlockError):
    """Raised for server-side errors (5xx)."""
