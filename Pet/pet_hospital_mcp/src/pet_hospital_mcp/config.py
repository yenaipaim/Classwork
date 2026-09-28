"""Configuration module for pet hospital MCP service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment variables."""

    # Go REST API upstream address
    pet_hospital_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "PET_HOSPITAL_BASE_URL", "http://127.0.0.1:8080"
        )
    )

    # MCP server host
    mcp_host: str = field(
        default_factory=lambda: os.environ.get("MCP_HOST", "127.0.0.1")
    )

    # MCP server port
    mcp_port: int = field(
        default_factory=lambda: int(os.environ.get("MCP_PORT", "9000"))
    )

    # HTTP client timeout in seconds
    http_timeout: float = field(
        default_factory=lambda: float(os.environ.get("HTTP_TIMEOUT", "30.0"))
    )

    # Maximum retries for backend calls
    max_retries: int = field(
        default_factory=lambda: int(os.environ.get("MAX_RETRIES", "2"))
    )


def load_config() -> Config:
    """Load configuration from environment variables."""
    return Config()
