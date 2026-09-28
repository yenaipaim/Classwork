"""Structured error handling for pet hospital MCP service."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Error codes for structured error responses."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    BACKEND_TIMEOUT = "BACKEND_TIMEOUT"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    BACKEND_API_ERROR = "BACKEND_API_ERROR"
    BACKEND_INVALID_RESPONSE = "BACKEND_INVALID_RESPONSE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass
class ErrorDetail:
    """Structured error detail following the unified error format."""

    code: ErrorCode
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "details": self.details,
            }
        }


class PetHospitalError(Exception):
    """Base exception for pet hospital MCP service."""

    def __init__(self, error_detail: ErrorDetail) -> None:
        self.error_detail = error_detail
        super().__init__(error_detail.message)


class ValidationError(PetHospitalError):
    """Raised when input validation fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            ErrorDetail(
                code=ErrorCode.VALIDATION_ERROR,
                message=message,
                details=details or {},
            )
        )


class BackendTimeoutError(PetHospitalError):
    """Raised when the backend request times out."""

    def __init__(self, message: str = "Backend request timed out") -> None:
        super().__init__(
            ErrorDetail(code=ErrorCode.BACKEND_TIMEOUT, message=message)
        )


class BackendUnavailableError(PetHospitalError):
    """Raised when the backend is unavailable."""

    def __init__(self, message: str = "Backend service unavailable") -> None:
        super().__init__(
            ErrorDetail(code=ErrorCode.BACKEND_UNAVAILABLE, message=message)
        )


class BackendAPIError(PetHospitalError):
    """Raised when the backend returns an error response."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        error_details = details or {}
        if status_code is not None:
            error_details["status_code"] = status_code
        super().__init__(
            ErrorDetail(
                code=ErrorCode.BACKEND_API_ERROR,
                message=message,
                details=error_details,
            )
        )


class BackendInvalidResponseError(PetHospitalError):
    """Raised when the backend returns an invalid response."""

    def __init__(self, message: str = "Invalid response from backend") -> None:
        super().__init__(
            ErrorDetail(code=ErrorCode.BACKEND_INVALID_RESPONSE, message=message)
        )


class InternalError(PetHospitalError):
    """Raised for unexpected internal errors."""

    def __init__(self, message: str = "Internal server error") -> None:
        super().__init__(
            ErrorDetail(code=ErrorCode.INTERNAL_ERROR, message=message)
        )
