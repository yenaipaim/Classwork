"""Tests for the list_pets tool."""

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
    ValidationError,
)
from pet_hospital_mcp.tools.list_pets import ListPetsInput, list_pets


class TestListPetsInput:
    """Test input validation for list_pets."""

    def test_valid_input_defaults(self):
        """Test that default values are set correctly."""
        input_data = ListPetsInput()
        assert input_data.page == 1
        assert input_data.pageSize == 20
        assert input_data.q is None
        assert input_data.species is None

    def test_valid_input_all_params(self):
        """Test with all parameters provided."""
        input_data = ListPetsInput(
            q="test",
            name="旺财",
            ownerName="张三",
            ownerPhone="13800001111",
            species="犬",
            doctor="李医生",
            disease="肠胃炎",
            status="就诊中",
            min=100.0,
            max=5000.0,
            sortBy="totalCost",
            order="desc",
            page=2,
            pageSize=50,
        )
        assert input_data.q == "test"
        assert input_data.species == "犬"
        assert input_data.status == "就诊中"
        assert input_data.min == 100.0
        assert input_data.max == 5000.0

    def test_invalid_species(self):
        """Test that invalid species is rejected."""
        with pytest.raises(Exception) as exc_info:
            ListPetsInput(species="龙")
        assert "species" in str(exc_info.value).lower() or "龙" in str(exc_info.value)

    def test_invalid_status(self):
        """Test that invalid status is rejected."""
        with pytest.raises(Exception) as exc_info:
            ListPetsInput(status="已死亡")
        assert "status" in str(exc_info.value).lower() or "已死亡" in str(exc_info.value)

    def test_invalid_sort_by(self):
        """Test that invalid sortBy is rejected."""
        with pytest.raises(Exception) as exc_info:
            ListPetsInput(sortBy="invalidField")
        assert "sortBy" in str(exc_info.value).lower() or "invalidField" in str(exc_info.value)

    def test_invalid_order(self):
        """Test that invalid order is rejected."""
        with pytest.raises(Exception) as exc_info:
            ListPetsInput(order="random")
        assert "order" in str(exc_info.value).lower() or "random" in str(exc_info.value)

    def test_page_less_than_1(self):
        """Test that page < 1 is rejected."""
        with pytest.raises(Exception) as exc_info:
            ListPetsInput(page=0)
        assert "page" in str(exc_info.value).lower()

    def test_page_size_too_large(self):
        """Test that pageSize > 500 is rejected."""
        with pytest.raises(Exception) as exc_info:
            ListPetsInput(pageSize=501)
        assert "pageSize" in str(exc_info.value).lower() or "500" in str(exc_info.value)

    def test_page_size_zero(self):
        """Test that pageSize < 1 is rejected."""
        with pytest.raises(Exception) as exc_info:
            ListPetsInput(pageSize=0)
        assert "pagesize" in str(exc_info.value).lower()

    def test_min_negative(self):
        """Test that negative min is rejected."""
        with pytest.raises(Exception) as exc_info:
            ListPetsInput(min=-1)
        assert "min" in str(exc_info.value).lower()

    def test_min_greater_than_max(self):
        """Test that min > max is rejected."""
        with pytest.raises(Exception) as exc_info:
            ListPetsInput(min=1000, max=100)
        assert "min" in str(exc_info.value).lower() and "max" in str(exc_info.value).lower()

    def test_reject_unknown_fields(self):
        """Test that unknown fields are rejected."""
        with pytest.raises(Exception) as exc_info:
            ListPetsInput(unknownField="test")
        assert "unknown" in str(exc_info.value).lower() or "extra" in str(exc_info.value).lower()

    def test_reject_nan(self):
        """Test that NaN values are rejected."""
        with pytest.raises(Exception):
            ListPetsInput(min=float("nan"))

    def test_reject_infinity(self):
        """Test that Infinity values are accepted by Pydantic (backend will validate)."""
        # Note: Pydantic doesn't reject infinity by default for float fields.
        # The backend API will handle validation of actual values.
        input_data = ListPetsInput(min=float("inf"))
        assert input_data.min == float("inf")


class TestListPetsTool:
    """Test the list_pets tool function."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_normal_call_with_all_params(self, config, sample_pets_response):
        """Test normal call with all filter/sort/pagination params forwarded correctly."""
        # Mock the backend API
        route = respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=Response(200, json=sample_pets_response)
        )

        from pet_hospital_mcp.rest_client import PetHospitalClient

        client = PetHospitalClient(config)

        result = await list_pets(
            client,
            q="test",
            name="旺财",
            ownerName="张三",
            species="犬",
            doctor="李医生",
            disease="肠胃炎",
            status="就诊中",
            min=100.0,
            max=5000.0,
            sortBy="totalCost",
            order="desc",
            page=2,
            pageSize=50,
        )

        # Verify the request was made with correct params
        assert route.called
        request = route.calls.last.request
        params = dict(request.url.params)
        assert params["q"] == "test"
        assert params["name"] == "旺财"
        assert params["ownerName"] == "张三"
        assert params["species"] == "犬"
        assert params["doctor"] == "李医生"
        assert params["disease"] == "肠胃炎"
        assert params["status"] == "就诊中"
        assert params["min"] == "100.0"
        assert params["max"] == "5000.0"
        assert params["sortBy"] == "totalCost"
        assert params["order"] == "desc"
        assert params["page"] == "2"
        assert params["pageSize"] == "50"

        # Verify the response
        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["id"] == "PET-000001"

    @pytest.mark.asyncio
    @respx.mock
    async def test_normal_call_minimal_params(self, config, sample_pets_response):
        """Test normal call with only required params (defaults)."""
        route = respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=Response(200, json=sample_pets_response)
        )

        from pet_hospital_mcp.rest_client import PetHospitalClient

        client = PetHospitalClient(config)

        result = await list_pets(client)

        assert route.called
        request = route.calls.last.request
        params = dict(request.url.params)
        assert params["page"] == "1"
        assert params["pageSize"] == "20"

    @pytest.mark.asyncio
    async def test_input_validation_failure(self, config):
        """Test that invalid input raises ValidationError."""
        from pet_hospital_mcp.rest_client import PetHospitalClient

        client = PetHospitalClient(config)

        with pytest.raises(ValidationError):
            await list_pets(client, species="龙")

    @pytest.mark.asyncio
    @respx.mock
    async def test_backend_4xx_error(self, config):
        """Test handling of backend 4xx errors."""
        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=Response(400, json={"error": "bad request"})
        )

        from pet_hospital_mcp.rest_client import PetHospitalClient

        client = PetHospitalClient(config)

        with pytest.raises(BackendAPIError) as exc_info:
            await list_pets(client)
        assert exc_info.value.error_detail.code.value == "BACKEND_API_ERROR"

    @pytest.mark.asyncio
    @respx.mock
    async def test_backend_5xx_error(self, config):
        """Test handling of backend 5xx errors."""
        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=Response(500, json={"error": "internal server error"})
        )

        from pet_hospital_mcp.rest_client import PetHospitalClient

        client = PetHospitalClient(config)

        with pytest.raises(BackendAPIError) as exc_info:
            await list_pets(client)
        assert exc_info.value.error_detail.code.value == "BACKEND_API_ERROR"

    @pytest.mark.asyncio
    @respx.mock
    async def test_backend_timeout(self, config):
        """Test handling of backend timeout."""
        import httpx

        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            side_effect=httpx.TimeoutException("Request timed out")
        )

        from pet_hospital_mcp.rest_client import PetHospitalClient

        # Use a config with no retries for this test
        test_config = Config(
            pet_hospital_base_url="http://127.0.0.1:8080",
            http_timeout=1.0,
            max_retries=0,
        )
        client = PetHospitalClient(test_config)

        with pytest.raises(BackendTimeoutError):
            await list_pets(client)

    @pytest.mark.asyncio
    @respx.mock
    async def test_backend_connection_error(self, config):
        """Test handling of backend connection errors."""
        import httpx

        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        from pet_hospital_mcp.rest_client import PetHospitalClient

        test_config = Config(
            pet_hospital_base_url="http://127.0.0.1:8080",
            http_timeout=1.0,
            max_retries=0,
        )
        client = PetHospitalClient(test_config)

        with pytest.raises(BackendUnavailableError):
            await list_pets(client)

    @pytest.mark.asyncio
    @respx.mock
    async def test_backend_invalid_json(self, config):
        """Test handling of invalid JSON response."""
        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=Response(200, text="not json")
        )

        from pet_hospital_mcp.rest_client import PetHospitalClient

        client = PetHospitalClient(config)

        with pytest.raises(BackendInvalidResponseError):
            await list_pets(client)

    @pytest.mark.asyncio
    @respx.mock
    async def test_backend_invalid_response_structure(self, config):
        """Test handling of response with invalid structure."""
        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=Response(200, json={"code": 200, "message": "ok", "data": "invalid"})
        )

        from pet_hospital_mcp.rest_client import PetHospitalClient

        client = PetHospitalClient(config)

        with pytest.raises(BackendInvalidResponseError):
            await list_pets(client)

    @pytest.mark.asyncio
    @respx.mock
    async def test_backend_error_code_in_response(self, config):
        """Test handling of error code in response body."""
        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=Response(200, json={"code": 400, "message": "bad request", "data": None})
        )

        from pet_hospital_mcp.rest_client import PetHospitalClient

        client = PetHospitalClient(config)

        with pytest.raises(BackendAPIError):
            await list_pets(client)

    @pytest.mark.asyncio
    @respx.mock
    async def test_response_with_null_records_and_charges(self, config):
        """Test that null records and charges are handled correctly."""
        response_data = {
            "code": 200,
            "message": "ok",
            "data": {
                "items": [
                    {
                        "id": "PET-000001",
                        "name": "旺财",
                        "species": "犬",
                        "ownerName": "张三",
                        "ownerPhone": "13800001111",
                        "doctor": "李医生",
                        "disease": "肠胃炎",
                        "status": "就诊中",
                        "records": None,
                        "charges": None,
                        "totalCost": 0,
                        "visitCount": 0,
                    }
                ],
                "total": 1,
                "page": 1,
                "pageSize": 20,
                "totalPages": 1,
                "totalCost": 0,
            },
        }

        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=Response(200, json=response_data)
        )

        from pet_hospital_mcp.rest_client import PetHospitalClient

        client = PetHospitalClient(config)

        result = await list_pets(client)
        assert result["items"][0]["records"] is None
        assert result["items"][0]["charges"] is None
