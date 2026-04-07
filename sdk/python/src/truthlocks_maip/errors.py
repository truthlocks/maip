# Copyright 2026 Truthlocks Inc.
# Licensed under the Apache License, Version 2.0

"""Error types for the MAIP SDK."""

from __future__ import annotations

from typing import Optional


class MaipError(Exception):
    """Base error class for all MAIP SDK errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class LimitExceededError(MaipError):
    """Raised when the caller exceeds a rate limit or quota."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after_seconds: Optional[int] = None,
    ) -> None:
        super().__init__(message, status_code=429, code="LIMIT_EXCEEDED")
        self.retry_after_seconds = retry_after_seconds


class UnauthorizedError(MaipError):
    """Raised when the API key is missing, invalid, or lacks permission."""

    def __init__(
        self, message: str = "Unauthorized: invalid or missing API key"
    ) -> None:
        super().__init__(message, status_code=401, code="UNAUTHORIZED")


class NotFoundError(MaipError):
    """Raised when a requested resource is not found."""

    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            f"{resource} not found: {identifier}",
            status_code=404,
            code="NOT_FOUND",
        )
        self.resource = resource
        self.identifier = identifier


class VerificationError(MaipError):
    """Raised when bundle or receipt verification fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="VERIFICATION_FAILED")
