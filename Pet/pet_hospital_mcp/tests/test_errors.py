"""Tests for error handling module."""

from __future__ import annotations

import pytest

from pet_hospital_mcp.errors import (
    BackendAPIError,
    BackendInvalidResponseError,
    BackendTimeoutError,
    BackendUnavailableError,
    ErrorCode,
    ErrorDetail,
    InternalError,
    PetHospitalError,
    ValidationError,
)


class TestErrorCodes:
    """Test error code definitions."""

    def test_all_error_codes_exist(self):
        """Test that all required error codes are defined."""
        expected_codes = [
            "VALIDATION_ERROR",
            "BACKEND_TIMEOUT",
            "BACKEND_UNAVAILABLE",
            "BACKEND_API_ERROR",
            "BACKEND_INVALID_RESPONSE",
            "INTERNAL_ERROR",
        ]
        for code in expected_codes:
            assert hasattr(ErrorCode, code), f"ErrorCode.{code} not found"

    def test_error_code_values(self):
        """Test that error code values are correct strings."""
        assert ErrorCode.VALIDATION_ERROR.value == "VALIDATION_ERROR"
        assert ErrorCode.BACKEND_TIMEOUT.value == "BACKEND_TIMEOUT"
        assert ErrorCode.BACKEND_UNAVAILABLE.value == "BACKEND_UNAVAILABLE"
        assert ErrorCode.BACKEND_API_ERROR.value == "BACKEND_API_ERROR"
        assert ErrorCode.BACKEND_INVALID_RESPONSE.value == "BACKEND_INVALID_RESPONSE"
        assert ErrorCode.INTERNAL_ERROR.value == "INTERNAL_ERROR"


class TestErrorDetail:
    """Test ErrorDetail class."""

    def test_to_dict_basic(self):
        """Test basic to_dict conversion."""
        detail = ErrorDetail(
            code=ErrorCode.VALIDATION_ERROR,
            message="Test error",
        )
        result = detail.to_dict()
        assert result == {
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Test error",
                "details": {},
            }
        }

    def test_to_dict_with_details(self):
        """Test to_dict with details."""
        detail = ErrorDetail(
            code=ErrorCode.BACKEND_API_ERROR,
            message="Backend error",
            details={"status_code": 500},
        )
        result = detail.to_dict()
        assert result["error"]["details"]["status_code"] == 500


class TestPetHospitalError:
    """Test PetHospitalError base class."""

    def test_is_exception(self):
        """Test that PetHospitalError is an Exception."""
        detail = ErrorDetail(code=ErrorCode.INTERNAL_ERROR, message="test")
        error = PetHospitalError(detail)
        assert isinstance(error, Exception)

    def test_error_detail_attribute(self):
        """Test that error_detail is accessible."""
        detail = ErrorDetail(code=ErrorCode.INTERNAL_ERROR, message="test")
        error = PetHospitalError(detail)
        assert error.error_detail.code == ErrorCode.INTERNAL_ERROR


class TestValidationError:
    """Test ValidationError."""

    def test_basic_creation(self):
        """Test basic ValidationError creation."""
        error = ValidationError("Invalid input")
        assert error.error_detail.code == ErrorCode.VALIDATION_ERROR
        assert error.error_detail.message == "Invalid input"
        assert error.error_detail.details == {}

    def test_with_details(self):
        """Test ValidationError with details."""
        error = ValidationError("Invalid field", {"field": "species"})
        assert error.error_detail.details == {"field": "species"}

    def test_to_dict(self):
        """Test ValidationError to_dict."""
        error = ValidationError("Invalid input")
        result = error.error_detail.to_dict()
        assert result["error"]["code"] == "VALIDATION_ERROR"


class TestBackendTimeoutError:
    """Test BackendTimeoutError."""

    def test_default_message(self):
        """Test default message."""
        error = BackendTimeoutError()
        assert error.error_detail.code == ErrorCode.BACKEND_TIMEOUT
        assert "timed out" in error.error_detail.message.lower()

    def test_custom_message(self):
        """Test custom message."""
        error = BackendTimeoutError("Custom timeout message")
        assert error.error_detail.message == "Custom timeout message"


class TestBackendUnavailableError:
    """Test BackendUnavailableError."""

    def test_default_message(self):
        """Test default message."""
        error = BackendUnavailableError()
        assert error.error_detail.code == ErrorCode.BACKEND_UNAVAILABLE
        assert "unavailable" in error.error_detail.message.lower()

    def test_custom_message(self):
        """Test custom message."""
        error = BackendUnavailableError("Custom message")
        assert error.error_detail.message == "Custom message"


class TestBackendAPIError:
    """Test BackendAPIError."""

    def test_basic_creation(self):
        """Test basic creation."""
        error = BackendAPIError("API error")
        assert error.error_detail.code == ErrorCode.BACKEND_API_ERROR

    def test_with_status_code(self):
        """Test with status code."""
        error = BackendAPIError("Not found", status_code=404)
        assert error.error_detail.details["status_code"] == 404

    def test_with_details(self):
        """Test with additional details."""
        error = BackendAPIError("Error", details={"key": "value"})
        assert error.error_detail.details["key"] == "value"

    def test_status_code_in_details(self):
        """Test that status_code is added to details."""
        error = BackendAPIError("Error", status_code=500)
        assert error.error_detail.details["status_code"] == 500


class TestBackendInvalidResponseError:
    """Test BackendInvalidResponseError."""

    def test_default_message(self):
        """Test default message."""
        error = BackendInvalidResponseError()
        assert error.error_detail.code == ErrorCode.BACKEND_INVALID_RESPONSE
        assert "invalid" in error.error_detail.message.lower()


class TestInternalError:
    """Test InternalError."""

    def test_default_message(self):
        """Test default message."""
        error = InternalError()
        assert error.error_detail.code == ErrorCode.INTERNAL_ERROR
        assert "internal" in error.error_detail.message.lower()
