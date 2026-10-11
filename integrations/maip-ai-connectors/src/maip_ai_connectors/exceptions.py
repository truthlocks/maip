# Copyright 2026 Truthlocks Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Custom exceptions for the maip-ai-connectors package."""

from __future__ import annotations


class MAIPError(Exception):
    """Base exception for all MAIP-related errors."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class MAIPAuthError(MAIPError):
    """Raised when authentication with the MAIP API fails.

    Common causes: missing or invalid API key, expired credentials,
    insufficient permissions for the requested tenant.
    """

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, status_code=401)


class MAIPNotFoundError(MAIPError):
    """Raised when a requested MAIP resource does not exist.

    Examples: receipt ID not found, agent ID has no associated receipts.
    """

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=404)


class MAIPValidationError(MAIPError):
    """Raised when request payload fails server-side validation.

    Check the message for details on which fields failed validation.
    """

    def __init__(self, message: str = "Validation error") -> None:
        super().__init__(message, status_code=422)


class MAIPConnectionError(MAIPError):
    """Raised when a network-level failure prevents communication with the MAIP API.

    This wraps transport errors such as DNS resolution failures, connection
    timeouts, and TLS handshake errors.
    """

    def __init__(self, message: str = "Connection to MAIP API failed") -> None:
        super().__init__(message, status_code=None)


class MAIPReceiptError(MAIPError):
    """Raised when receipt generation fails due to invalid or missing data.

    This typically occurs when a callback handler cannot extract sufficient
    information from an AI framework event to construct a valid receipt.
    """

    def __init__(self, message: str = "Receipt generation failed") -> None:
        super().__init__(message, status_code=None)
