"""Test fixtures for pet hospital MCP service."""

from __future__ import annotations

import pytest
from mcp import Client

from pet_hospital_mcp.config import Config
from pet_hospital_mcp.server import create_mcp_server


@pytest.fixture
def config() -> Config:
    """Create a test configuration."""
    return Config(
        pet_hospital_base_url="http://127.0.0.1:8080",
        mcp_host="127.0.0.1",
        mcp_port=9000,
        http_timeout=5.0,
        max_retries=0,
    )


@pytest.fixture
def mcp_server(config: Config):
    """Create a configured MCP server for testing."""
    return create_mcp_server(config)


@pytest.fixture
async def mcp_client(mcp_server):
    """Create an in-memory MCP client connected to the server."""
    async with Client(mcp_server) as client:
        yield client


@pytest.fixture
def sample_pets_response() -> dict:
    """Sample successful response from the Go API."""
    return {
        "code": 200,
        "message": "ok",
        "data": {
            "items": [
                {
                    "id": "PET-000001",
                    "name": "旺财",
                    "species": "犬",
                    "breed": "金毛",
                    "gender": "公",
                    "ageMonths": 36,
                    "color": "金色",
                    "chipNo": "CHIP-000001",
                    "ownerName": "张三",
                    "ownerPhone": "13800001111",
                    "ownerAddr": "北京市朝阳区",
                    "doctor": "李医生",
                    "disease": "急性肠胃炎",
                    "status": "就诊中",
                    "allergy": "无",
                    "note": None,
                    "records": [
                        {
                            "id": "MR-001",
                            "visitDate": "2024-01-15",
                            "doctor": "李医生",
                            "diagnosis": "急性肠胃炎",
                            "symptoms": "呕吐腹泻",
                            "treatment": "补液消炎",
                            "prescription": ["阿莫西林"],
                            "weightKg": 12.5,
                            "temperature": 39.1,
                            "followUp": "3天后复查",
                            "charge": 380.0,
                            "createdAt": "2024-01-15T10:00:00Z",
                        }
                    ],
                    "charges": [
                        {
                            "id": "CH-001",
                            "item": "血常规检查",
                            "category": "检查",
                            "amount": 180.0,
                            "doctor": "李医生",
                            "date": "2024-01-15",
                        }
                    ],
                    "totalCost": 560.0,
                    "visitCount": 1,
                    "createdAt": "2024-01-15T10:00:00Z",
                    "updatedAt": "2024-01-15T10:00:00Z",
                }
            ],
            "total": 1,
            "page": 1,
            "pageSize": 20,
            "totalPages": 1,
            "totalCost": 560.0,
        },
        "time": "2024-01-15T12:00:00+08:00",
    }


@pytest.fixture
def sample_error_response() -> dict:
    """Sample error response from the Go API."""
    return {
        "code": 400,
        "message": "invalid parameter",
        "data": None,
        "time": "2024-01-15T12:00:00+08:00",
    }
