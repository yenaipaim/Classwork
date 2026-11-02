"""MCP（Model Context Protocol）客户端：配置、连接与工具注册。

对外只暴露三样东西：:func:`discover_mcp_config` 找到并解析 `.mcp.json`，
:class:`McpConnection` 管理单个 Server 的会话，:class:`McpHub` 把它们注册成
Agent 工具。界面层不需要知道 MCP SDK 的存在。
"""

from __future__ import annotations

from .config import (
    ENV_MCP_CONFIG,
    TRANSPORT_HTTP,
    TRANSPORT_SSE,
    TRANSPORT_STDIO,
    McpConfig,
    McpConfigIssue,
    McpServerConfig,
    discover_mcp_config,
    load_mcp_config,
)
from .connection import McpConnection
from .hub import McpHub, McpServerStatus, McpToolInfo, plan_tool_names

__all__ = [
    "ENV_MCP_CONFIG",
    "TRANSPORT_HTTP",
    "TRANSPORT_SSE",
    "TRANSPORT_STDIO",
    "McpConfig",
    "McpConfigIssue",
    "McpConnection",
    "McpHub",
    "McpServerConfig",
    "McpServerStatus",
    "McpToolInfo",
    "discover_mcp_config",
    "load_mcp_config",
    "plan_tool_names",
]
