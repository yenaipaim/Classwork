"""Tests for logging configuration with sensitive data masking."""

from __future__ import annotations

import json
import logging

import pytest

from pet_hospital_mcp.logging_config import (
    LogContext,
    StructuredJsonFormatter,
    mask_sensitive_data,
    mask_text,
    mask_sensitive_value,
)


class TestMaskSensitiveValue:
    """Test sensitive value masking."""

    def test_mask_phone_field(self):
        """Test masking of phone field."""
        result = mask_sensitive_value("ownerPhone", "13800001111")
        assert result.startswith("13")
        assert result.endswith("11")
        assert "***" in result

    def test_mask_owner_phone(self):
        """Test masking of owner_phone field."""
        result = mask_sensitive_value("owner_phone", "13800001111")
        assert result.startswith("13")
        assert result.endswith("11")

    def test_mask_address_field(self):
        """Test masking of address field."""
        result = mask_sensitive_value("ownerAddr", "北京市朝阳区某某路123号")
        assert result.startswith("北京")
        assert result.endswith("3号")
        assert "***" in result

    def test_mask_chip_no_field(self):
        """Test masking of chip number field."""
        result = mask_sensitive_value("chipNo", "CHIP-000001")
        assert result.startswith("CH")
        assert result.endswith("01")
        assert "***" in result

    def test_mask_short_value(self):
        """Test masking of short values."""
        result = mask_sensitive_value("ownerPhone", "ab")
        assert result == "***"

    def test_non_sensitive_field_unchanged(self):
        """Test that non-sensitive fields are unchanged."""
        result = mask_sensitive_value("name", "旺财")
        assert result == "旺财"

    def test_non_string_value_unchanged(self):
        """Test that non-string values are unchanged."""
        result = mask_sensitive_value("ownerPhone", 123)
        assert result == 123


class TestMaskSensitiveData:
    """Test recursive sensitive data masking."""

    def test_mask_dict(self):
        """Test masking in a dictionary."""
        data = {
            "name": "旺财",
            "ownerPhone": "13800001111",
            "ownerAddr": "北京市朝阳区",
        }
        result = mask_sensitive_data(data)
        assert result["name"] == "旺财"
        assert "***" in result["ownerPhone"]
        assert "***" in result["ownerAddr"]

    def test_mask_nested_dict(self):
        """Test masking in nested dictionaries."""
        data = {
            "pet": {
                "name": "旺财",
                "ownerPhone": "13800001111",
            }
        }
        result = mask_sensitive_data(data)
        assert result["pet"]["name"] == "旺财"
        assert "***" in result["pet"]["ownerPhone"]

    def test_mask_list(self):
        """Test masking in a list."""
        data = [
            {"name": "旺财", "ownerPhone": "13800001111"},
            {"name": "咪咪", "ownerPhone": "13900002222"},
        ]
        result = mask_sensitive_data(data)
        assert len(result) == 2
        assert "***" in result[0]["ownerPhone"]
        assert "***" in result[1]["ownerPhone"]

    def test_mask_non_dict_non_list(self):
        """Test that non-dict non-list values are unchanged."""
        assert mask_sensitive_data("test") == "test"
        assert mask_sensitive_data(123) == 123
        assert mask_sensitive_data(None) is None


class TestMaskText:
    """Test text masking for phone numbers and chip numbers."""

    def test_mask_phone_in_text(self):
        """Test masking phone numbers in text."""
        text = "Owner phone: 13800001111"
        result = mask_text(text)
        assert "13800001111" not in result
        assert "***" in result

    def test_mask_chip_in_text(self):
        """Test masking chip numbers in text."""
        text = "Chip: CHIP-000001"
        result = mask_text(text)
        assert "CHIP-000001" not in result
        assert "***" in result

    def test_no_sensitive_data(self):
        """Test text without sensitive data."""
        text = "Normal text without sensitive data"
        result = mask_text(text)
        assert result == text


class TestStructuredJsonFormatter:
    """Test JSON log formatter."""

    def test_format_basic(self):
        """Test basic log formatting."""
        formatter = StructuredJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        parsed = json.loads(result)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "Test message"
        assert "timestamp" in parsed

    def test_format_with_extra_fields(self):
        """Test formatting with extra fields."""
        formatter = StructuredJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Tool call",
            args=(),
            exc_info=None,
        )
        record.tool_name = "list_pets"
        record.params = {"page": 1}
        record.status = "success"
        record.duration_ms = 123.45

        result = formatter.format(record)
        parsed = json.loads(result)
        assert parsed["tool_name"] == "list_pets"
        assert parsed["params"]["page"] == 1
        assert parsed["status"] == "success"
        assert parsed["duration_ms"] == 123.45

    def test_format_with_sensitive_params(self):
        """Test that sensitive params are masked in logs."""
        formatter = StructuredJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Tool call",
            args=(),
            exc_info=None,
        )
        record.params = {"ownerPhone": "13800001111"}

        result = formatter.format(record)
        parsed = json.loads(result)
        assert "13800001111" not in json.dumps(parsed)
        assert "***" in parsed["params"]["ownerPhone"]


class TestLogContext:
    """Test LogContext context manager."""

    def test_success_logging(self, caplog):
        """Test logging of successful tool call."""
        logger = logging.getLogger("test")
        with caplog.at_level(logging.INFO):
            with LogContext(logger, "list_pets", {"page": 1}):
                pass

        assert len(caplog.records) == 1
        assert caplog.records[0].tool_name == "list_pets"
        assert caplog.records[0].status == "success"
        assert caplog.records[0].duration_ms >= 0

    def test_error_logging(self, caplog):
        """Test logging of failed tool call."""
        logger = logging.getLogger("test")
        with caplog.at_level(logging.ERROR):
            try:
                with LogContext(logger, "list_pets", {"page": 1}):
                    raise ValueError("Test error")
            except ValueError:
                pass

        assert len(caplog.records) == 1
        assert caplog.records[0].tool_name == "list_pets"
        assert caplog.records[0].status == "error"
        assert "Test error" in str(caplog.records[0].error)
