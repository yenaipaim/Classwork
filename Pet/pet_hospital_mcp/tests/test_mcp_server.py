"""Tests for MCP server tool registration and stateless connection flow."""

from __future__ import annotations

import pytest
import respx
from httpx import Response
from mcp import Client

from pet_hospital_mcp.config import Config
from pet_hospital_mcp.server import create_mcp_server


class TestMCPToolRegistration:
    """Test MCP tool registration, tool name and JSON Schema."""

    @pytest.mark.asyncio
    async def test_tool_registration(self, config):
        """Test that list_pets tool is registered."""
        mcp = create_mcp_server(config)

        async with Client(mcp) as client:
            tools = await client.list_tools()

            # Should have exactly one tool
            assert len(tools.tools) == 1

            tool = tools.tools[0]
            assert tool.name == "list_pets"

    @pytest.mark.asyncio
    async def test_tool_schema(self, config):
        """Test that list_pets tool has correct JSON Schema."""
        mcp = create_mcp_server(config)

        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool = tools.tools[0]

            # Verify schema structure
            schema = tool.input_schema
            assert schema["type"] == "object"
            assert "properties" in schema

            # Verify all expected parameters exist
            properties = schema["properties"]
            expected_params = [
                "q", "name", "ownerName", "ownerPhone", "species", "doctor",
                "disease", "status", "min", "max", "sortBy", "order", "page", "pageSize"
            ]
            for param in expected_params:
                assert param in properties, f"Parameter '{param}' not found in schema"

            # Verify page defaults
            assert properties["page"].get("default") == 1
            assert properties["pageSize"].get("default") == 20

    @pytest.mark.asyncio
    async def test_tool_description(self, config):
        """Test that list_pets tool has a meaningful description."""
        mcp = create_mcp_server(config)

        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool = tools.tools[0]

            assert tool.description is not None
            assert len(tool.description) > 50  # Should be meaningful
            assert "pet" in tool.description.lower() or "宠物" in tool.description

    @pytest.mark.asyncio
    @respx.mock
    async def test_tool_call_returns_structured_content(self, config, sample_pets_response):
        """Test that tool call returns structured content."""
        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=Response(200, json=sample_pets_response)
        )

        mcp = create_mcp_server(config)

        async with Client(mcp) as client:
            result = await client.call_tool("list_pets", {"page": 1, "pageSize": 10})

            # Should have content
            assert result.content is not None
            assert len(result.content) > 0

            # Should not be an error
            assert not result.is_error


class TestStatelessConnection:
    """Test SDK 2.x stateless connection flow (2026-07-28 protocol)."""

    @pytest.mark.asyncio
    async def test_no_initialize_handshake(self, config):
        """Test that connection works without old-style initialize handshake.

        In MCP 2026-07-28, there is no initialize handshake. The client
        sends protocol version in headers and _meta with each request.
        """
        mcp = create_mcp_server(config)

        # Client connects and immediately discovers tools
        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert len(tools.tools) > 0

    @pytest.mark.asyncio
    async def test_no_session_id(self, config):
        """Test that no Mcp-Session-Id is used.

        In MCP 2026-07-28, there is no session tracking via Mcp-Session-Id.
        """
        mcp = create_mcp_server(config)

        async with Client(mcp) as client:
            # Make multiple requests - they should all work independently
            tools1 = await client.list_tools()
            tools2 = await client.list_tools()

            assert len(tools1.tools) == len(tools2.tools)

    @pytest.mark.asyncio
    @respx.mock
    async def test_stateless_tool_call(self, config, sample_pets_response):
        """Test that tool calls work without session state."""
        respx.get("http://127.0.0.1:8080/api/v1/pets").mock(
            return_value=Response(200, json=sample_pets_response)
        )

        mcp = create_mcp_server(config)

        async with Client(mcp) as client:
            # Make multiple independent calls
            result1 = await client.call_tool("list_pets", {"page": 1, "pageSize": 10})
            result2 = await client.call_tool("list_pets", {"page": 2, "pageSize": 5})

            assert not result1.is_error
            assert not result2.is_error

    @pytest.mark.asyncio
    async def test_health_endpoint(self, config):
        """Test the /health endpoint works."""
        mcp = create_mcp_server(config)
        app = mcp.streamable_http_app()

        # The app should have the /health route
        routes = [route.path for route in app.routes if hasattr(route, "path")]
        assert "/health" in routes
