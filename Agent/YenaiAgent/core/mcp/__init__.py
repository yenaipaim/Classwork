"""MCP（Model Context Protocol）客户端：配置、连接与工具注册。

对外只暴露三样东西：:func:`discover_mcp_config` 找到并解析技能目录里的
`.mcp.json`（缺失时按 :data:`MCP_TEMPLATE` 生成模板），:class:`McpConnection`
管理单个 Server 的会话，:class:`McpHub` 把它们注册成 Agent 工具。
界面层不需要知道 MCP SDK 的存在。
"""

from __future__ import annotations

from .config import (
    ENV_MCP_CONFIG,
    MCP_TEMPLATE,
    TRANSPORT_HTTP,
    TRANSPORT_SSE,
    TRANSPORT_STDIO,
    McpConfig,
    McpConfigIssue,
    McpServerConfig,
    discover_mcp_config,
    ensure_mcp_config,
    load_mcp_config,
    mcp_config_path,
    render_mcp_template,
)
from .connection import McpConnection
from .hub import McpHub, McpServerStatus, McpToolInfo, plan_tool_names

__all__ = [
    "ENV_MCP_CONFIG",
    "MCP_TEMPLATE",
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
    "ensure_mcp_config",
    "load_mcp_config",
    "mcp_config_path",
    "plan_tool_names",
    "render_mcp_template",
]
