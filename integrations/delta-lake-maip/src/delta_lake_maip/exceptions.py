"""Shared receipt errors retain consistent catch behavior across integrations."""
from maip_ai_connectors.exceptions import MAIPError, MAIPAuthError, MAIPNotFoundError, MAIPValidationError, MAIPConnectionError

class DeltaTableError(MAIPError):
    """Raised when a Delta Lake table operation fails during receipt generation.

    Examples: table not found, transaction log corrupted, version not available.
    """

    def __init__(self, message: str = "Delta table operation failed") -> None:
        super().__init__(message, status_code=None)
