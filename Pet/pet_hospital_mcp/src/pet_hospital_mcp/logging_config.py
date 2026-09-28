"""Logging configuration with sensitive data masking."""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from typing import Any

# Fields that must be masked in logs (including snake_case variants)
SENSITIVE_FIELDS = {
    "ownerPhone",
    "owner_phone",
    "ownerAddr",
    "owner_addr",
    "chipNo",
    "chip_no",
    "phone",
    "address",
    "addr",
}

# Regex patterns for sensitive data
PHONE_PATTERN = re.compile(r"\b1[3-9]\d{9}\b")
CHIP_PATTERN = re.compile(r"\bCHIP-\d{6}\b")


def mask_sensitive_value(key: str, value: Any) -> Any:
    """Mask a sensitive value based on the key name."""
    if not isinstance(value, str):
        return value

    key_lower = key.lower()
    if any(s.lower() in key_lower for s in SENSITIVE_FIELDS):
        if len(value) > 4:
            return value[:2] + "***" + value[-2:]
        return "***"
    return value


def mask_sensitive_data(data: Any) -> Any:
    """Recursively mask sensitive data in a dictionary or list."""
    if isinstance(data, dict):
        return {k: mask_sensitive_data(mask_sensitive_value(k, v)) for k, v in data.items()}
    elif isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    return data


def mask_text(text: str) -> str:
    """Mask phone numbers and chip numbers in free text."""
    text = PHONE_PATTERN.sub(lambda m: m.group()[:2] + "***" + m.group()[-2:], text)
    text = CHIP_PATTERN.sub(lambda m: m.group()[:6] + "***", text)
    return text


class StructuredJsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields from record
        if hasattr(record, "tool_name"):
            log_entry["tool_name"] = record.tool_name
        if hasattr(record, "params"):
            log_entry["params"] = mask_sensitive_data(record.params)
        if hasattr(record, "status"):
            log_entry["status"] = record.status
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms
        if hasattr(record, "error"):
            log_entry["error"] = mask_text(str(record.error))

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Set up structured JSON logging."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add JSON handler to stderr
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(StructuredJsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z"))
    root_logger.addHandler(handler)


class LogContext:
    """Context manager for logging tool calls with timing."""

    def __init__(self, logger: logging.Logger, tool_name: str, params: dict[str, Any]) -> None:
        self.logger = logger
        self.tool_name = tool_name
        self.params = params
        self.start_time: float = 0.0

    def __enter__(self) -> LogContext:
        self.start_time = time.monotonic()
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        duration_ms = round((time.monotonic() - self.start_time) * 1000, 2)

        if exc_type is not None:
            self.logger.error(
                "Tool call failed",
                extra={
                    "tool_name": self.tool_name,
                    "params": self.params,
                    "status": "error",
                    "duration_ms": duration_ms,
                    "error": str(exc_val),
                },
            )
        else:
            self.logger.info(
                "Tool call completed",
                extra={
                    "tool_name": self.tool_name,
                    "params": self.params,
                    "status": "success",
                    "duration_ms": duration_ms,
                },
            )
