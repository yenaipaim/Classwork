"""Integration tests that connect to the real Go service.

These tests are skipped by default since they require the Go service to be running.
Run them manually with: pytest tests/test_integration.py -v
"""

from __future__ import annotations

import pytest
import httpx

from pet_hospital_mcp.config import Config
from pet_hospital_mcp.rest_client import PetHospitalClient


def is_go_service_running() -> bool:
    """Check if the Go service is running."""
    try:
        response = httpx.get("http://127.0.0.1:8080/health", timeout=2.0)
        return response.status_code == 200
    except Exception:
        return False


# Skip all tests in this module if Go service is not running
pytestmark = pytest.mark.skipif(
    not is_go_service_running(),
    reason="Go pet hospital service is not running on port 8080",
)


@pytest.fixture
def config():
    """Create a configuration for integration tests."""
    return Config(
        pet_hospital_base_url="http://127.0.0.1:8080",
        http_timeout=10.0,
        max_retries=1,
    )


class TestIntegration:
    """Integration tests with real Go service."""

    @pytest.mark.asyncio
    async def test_health_check(self, config):
        """Test health check against real service."""
        client = PetHospitalClient(config)
        result = await client.health_check()
        # Real health endpoint returns {code, message, data: {status, ...}}
        assert result["code"] == 200
        assert result["data"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_list_pets_default(self, config):
        """Test listing pets with default parameters."""
        client = PetHospitalClient(config)
        result = await client.get_pets({"page": 1, "pageSize": 5})

        assert "items" in result
        assert "total" in result
        assert "page" in result
        assert "pageSize" in result
        assert result["page"] == 1
        assert result["pageSize"] == 5
        assert len(result["items"]) <= 5

    @pytest.mark.asyncio
    async def test_list_pets_with_species_filter(self, config):
        """Test listing pets filtered by species."""
        client = PetHospitalClient(config)
        result = await client.get_pets({"species": "犬", "page": 1, "pageSize": 10})

        assert "items" in result
        for pet in result["items"]:
            assert pet["species"] == "犬"

    @pytest.mark.asyncio
    async def test_list_pets_with_status_filter(self, config):
        """Test listing pets filtered by status."""
        client = PetHospitalClient(config)
        result = await client.get_pets({"status": "就诊中", "page": 1, "pageSize": 10})

        assert "items" in result
        for pet in result["items"]:
            assert pet["status"] == "就诊中"

    @pytest.mark.asyncio
    async def test_list_pets_with_sorting(self, config):
        """Test listing pets with sorting."""
        client = PetHospitalClient(config)
        result = await client.get_pets({
            "sortBy": "totalCost",
            "order": "desc",
            "page": 1,
            "pageSize": 5,
        })

        assert "items" in result
        if len(result["items"]) > 1:
            costs = [pet["totalCost"] for pet in result["items"]]
            assert costs == sorted(costs, reverse=True)

    @pytest.mark.asyncio
    async def test_list_pets_with_search(self, config):
        """Test listing pets with search query."""
        client = PetHospitalClient(config)
        result = await client.get_pets({"q": "肠胃炎", "page": 1, "pageSize": 10})

        assert "items" in result
        # At least some results should match
        if result["total"] > 0:
            assert len(result["items"]) > 0

    @pytest.mark.asyncio
    async def test_list_pets_with_cost_range(self, config):
        """Test listing pets with cost range filter."""
        client = PetHospitalClient(config)
        result = await client.get_pets({"min": 100, "max": 1000, "page": 1, "pageSize": 10})

        assert "items" in result
        for pet in result["items"]:
            assert pet["totalCost"] >= 100
            assert pet["totalCost"] <= 1000
