"""Tests for the REST client module."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from pet_hospital_mcp.config import Config
from pet_hospital_mcp.errors import (
    BackendAPIError,
    BackendInvalidResponseError,
    BackendTimeoutError,
    BackendUnavailableError,
)
from pet_hospital_mcp.rest_client import PetHospitalClient


@pytest.fixture
def config():
    """Create a test configuration."""
    return Config(
        pet_hospital_base_url="http://127.0.0.1:8080",
        http_timeout=5.0,
        max_retries=0,
    )


class TestGetPets:
    """Test get_pets method."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_successful_request(self, config, sample_pets_response):
        """Test successful request."""
        route = respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=Response(200, json=sample_pets_response)
        )

        client = PetHospitalClient(config)
        result = await client.get_pets({"page": 1, "pageSize": 10})

        assert route.called
        assert result["total"] == 1
        assert len(result["items"]) == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_request_with_all_params(self, config, sample_pets_response):
        """Test request with all parameters forwarded."""
        route = respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=Response(200, json=sample_pets_response)
        )

        client = PetHospitalClient(config)
        params = {
            "q": "test",
            "name": "旺财",
            "ownerName": "张三",
            "species": "犬",
            "page": 2,
            "pageSize": 50,
        }
        await client.get_pets(params)

        assert route.called
        request = route.calls.last.request
        request_params = dict(request.url.params)
        for key, value in params.items():
            assert request_params.get(key) == str(value)

    @pytest.mark.asyncio
    @respx.mock
    async def test_4xx_error(self, config):
        """Test handling of 4xx errors."""
        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=Response(400, text="Bad request")
        )

        client = PetHospitalClient(config)
        with pytest.raises(BackendAPIError) as exc_info:
            await client.get_pets({})
        assert exc_info.value.error_detail.code.value == "BACKEND_API_ERROR"

    @pytest.mark.asyncio
    @respx.mock
    async def test_5xx_error(self, config):
        """Test handling of 5xx errors."""
        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=Response(500, text="Internal server error")
        )

        client = PetHospitalClient(config)
        with pytest.raises(BackendAPIError):
            await client.get_pets({})

    @pytest.mark.asyncio
    @respx.mock
    async def test_timeout(self, config):
        """Test handling of timeout."""
        import httpx

        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            side_effect=httpx.TimeoutException("Timeout")
        )

        client = PetHospitalClient(config)
        with pytest.raises(BackendTimeoutError):
            await client.get_pets({})

    @pytest.mark.asyncio
    @respx.mock
    async def test_connection_error(self, config):
        """Test handling of connection error."""
        import httpx

        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        client = PetHospitalClient(config)
        with pytest.raises(BackendUnavailableError):
            await client.get_pets({})

    @pytest.mark.asyncio
    @respx.mock
    async def test_invalid_json(self, config):
        """Test handling of invalid JSON response."""
        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=Response(200, text="not json")
        )

        client = PetHospitalClient(config)
        with pytest.raises(BackendInvalidResponseError):
            await client.get_pets({})

    @pytest.mark.asyncio
    @respx.mock
    async def test_non_200_code_in_response(self, config):
        """Test handling of non-200 code in response body."""
        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=Response(200, json={"code": 400, "message": "error", "data": None})
        )

        client = PetHospitalClient(config)
        with pytest.raises(BackendAPIError):
            await client.get_pets({})

    @pytest.mark.asyncio
    @respx.mock
    async def test_missing_data_field(self, config):
        """Test handling of missing data field in response."""
        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=Response(200, json={"code": 200, "message": "ok"})
        )

        client = PetHospitalClient(config)
        with pytest.raises(BackendInvalidResponseError):
            await client.get_pets({})

    @pytest.mark.asyncio
    @respx.mock
    async def test_retry_on_timeout(self, config):
        """Test that retries work on timeout."""
        import httpx

        # First call times out, second succeeds
        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            side_effect=[
                httpx.TimeoutException("Timeout"),
                Response(200, json={"code": 200, "message": "ok", "data": {"items": [], "total": 0, "page": 1, "pageSize": 20, "totalPages": 0, "totalCost": 0}}),
            ]
        )

        retry_config = Config(
            pet_hospital_base_url="http://127.0.0.1:8080",
            http_timeout=5.0,
            max_retries=1,
        )
        client = PetHospitalClient(retry_config)
        result = await client.get_pets({})
        assert result["total"] == 0


class TestHealthCheck:
    """Test health_check method."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_successful_health_check(self, config):
        """Test successful health check."""
        respx.get("http://127.0.0.1:8080/health").mock(
            return_value=Response(200, json={"status": "healthy"})
        )

        client = PetHospitalClient(config)
        result = await client.health_check()
        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    @respx.mock
    async def test_failed_health_check(self, config):
        """Test failed health check."""
        import httpx

        respx.get("http://127.0.0.1:8080/health").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        client = PetHospitalClient(config)
        with pytest.raises(BackendUnavailableError):
            await client.health_check()
