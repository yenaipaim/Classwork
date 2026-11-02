"""MCP 客户端测试：配置解析、命名冲突、注册表透传与 stdio 集成。"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

from core.factory import build_registry
from core.mcp import (
    ENV_MCP_CONFIG,
    TRANSPORT_HTTP,
    TRANSPORT_STDIO,
    McpConfig,
    McpHub,
    McpServerConfig,
    discover_mcp_config,
    load_mcp_config,
    plan_tool_names,
)
from core.tools.spec import ToolOutcome, ToolRegistry, ToolSpec

# 用 SDK 自己的服务端实现起一个真实 stdio Server，验证整条链路
SERVER_SCRIPT = textwrap.dedent(
    """
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError:  # pragma: no cover - mcp 1.x
        from mcp.server.fastmcp import FastMCP as MCPServer

    server = MCPServer("probe")

    @server.tool()
    def add(a: int, b: int) -> int:
        \"\"\"两数相加\"\"\"
        return a + b

    @server.tool()
    def greet(name: str) -> str:
        \"\"\"打招呼\"\"\"
        return "你好，" + name

    server.run()
    """
)


@pytest.fixture
def server_script(tmp_path: Path) -> Path:
    script = tmp_path / "probe_server.py"
    script.write_text(SERVER_SCRIPT, encoding="utf-8")
    return script


def _probe_config(script: Path) -> McpServerConfig:
    return McpServerConfig(
        name="probe",
        transport=TRANSPORT_STDIO,
        command=sys.executable,
        args=(str(script),),
        connect_timeout=30,
        call_timeout=30,
    )


# ---------------------------------------------------------------- 配置


def test_load_config_parses_stdio_and_http(tmp_path: Path) -> None:
    path = tmp_path / ".mcp.json"
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "local": {
                        "type": "stdio",
                        "command": "python",
                        "args": ["-m", "demo"],
                        "cwd": "sub",
                        "env": {"TOKEN": "abc"},
                    },
                    "remote": {"url": "http://127.0.0.1:8090/mcp"},
                    "broken": {"type": "http"},
                }
            }
        ),
        encoding="utf-8",
    )
    config = load_mcp_config(path)
    assert config.path == path
    local = config.server("local")
    assert local is not None
    assert local.transport == TRANSPORT_STDIO
    assert local.args == ("-m", "demo")
    assert local.cwd == str(tmp_path / "sub")
    assert local.env == {"TOKEN": "abc"}
    remote = config.server("remote")
    assert remote is not None
    assert remote.transport == TRANSPORT_HTTP
    # 一家写错只进 issues，不影响其他 Server
    assert [issue.server for issue in config.issues] == ["broken"]


def test_load_config_missing_file_is_not_fatal(tmp_path: Path) -> None:
    config = load_mcp_config(tmp_path / "absent.json")
    assert config.servers == ()
    assert config.issues


def test_discover_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_MCP_CONFIG, "off")
    assert discover_mcp_config(tmp_path).configured is False

    path = tmp_path / "custom.json"
    path.write_text('{"mcpServers": {}}', encoding="utf-8")
    monkeypatch.setenv(ENV_MCP_CONFIG, str(path))
    config = discover_mcp_config(tmp_path)
    assert config.path == path


def test_disabled_server_keeps_placeholder(tmp_path: Path) -> None:
    path = tmp_path / ".mcp.json"
    path.write_text(
        json.dumps({"mcpServers": {"off": {"type": "stdio", "disabled": True}}}),
        encoding="utf-8",
    )
    config = load_mcp_config(path)
    server = config.server("off")
    assert server is not None
    assert server.enabled is False
    assert config.enabled_servers == ()


# ---------------------------------------------------------------- 命名


class _Tool:
    def __init__(self, name: str) -> None:
        self.name = name


def test_tool_names_are_prefixed_only_on_conflict() -> None:
    plans = plan_tool_names(
        [
            ("A", [_Tool("search"), _Tool("RunCli"), _Tool("unique")]),
            ("B", [_Tool("search")]),
        ],
        reserved=["RunCli"],
    )
    assert plans[("A", "unique")] == "unique"
    assert plans[("A", "search")] == "A__search"
    assert plans[("B", "search")] == "B__search"
    assert plans[("A", "RunCli")] == "A__RunCli"


def test_non_ascii_tool_names_become_numbered_placeholders() -> None:
    plans = plan_tool_names(
        [("PeiHospitalMCP", [_Tool("查询宠物列表"), _Tool("新增宠物")])]
    )
    assert plans[("PeiHospitalMCP", "查询宠物列表")] == "tool_1"
    assert plans[("PeiHospitalMCP", "新增宠物")] == "tool_2"

    plans = plan_tool_names(
        [("A", [_Tool("查询")]), ("B", [_Tool("查询")])]
    )
    assert plans[("A", "查询")] == "A__tool_1"
    assert plans[("B", "查询")] == "B__tool_1"


# ---------------------------------------------------------------- 注册表


def test_registry_passes_tool_outcome_through() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="raw",
            description="返回非 JSON 文本",
            parameters={"type": "object", "properties": {}},
            handler=lambda: ToolOutcome("MCP 原文", False),
        )
    )
    outcome = registry.execute("raw", "{}")
    assert outcome.output == "MCP 原文"
    assert outcome.ok is False


# ---------------------------------------------------------------- stdio 集成


def test_hub_lists_and_calls_stdio_tool(server_script: Path) -> None:
    hub = McpHub(McpConfig(servers=(_probe_config(server_script),)))
    hub.start()
    try:
        status = hub.status()[0]
        assert status.connected, status.error
        assert status.tool_count == 2

        registry = ToolRegistry()
        hub.register_into(registry)
        assert {"add", "greet"} <= set(registry.names())

        outcome = registry.execute("add", '{"a": 2, "b": 3}')
        assert outcome.ok is True
        assert "5" in outcome.output

        greeting = registry.execute("greet", '{"name": "小明"}')
        assert greeting.ok is True
        assert "小明" in greeting.output
    finally:
        hub.close()


def test_failed_server_does_not_block_others(
    tmp_path: Path, server_script: Path
) -> None:
    config = McpConfig(
        servers=(
            McpServerConfig(
                name="bad",
                transport=TRANSPORT_STDIO,
                command=str(tmp_path / "missing-server.exe"),
                connect_timeout=5,
            ),
            _probe_config(server_script),
        )
    )
    hub = McpHub(config)
    hub.start()
    try:
        statuses = {row.name: row for row in hub.status()}
        assert statuses["bad"].connected is False
        assert statuses["bad"].error
        assert statuses["probe"].connected

        registry = build_registry(tmp_path, mcp=hub)
        assert "add" in registry.names()
        # 本地工具仍在，MCP 只是追加
        assert "RunCli" in registry.names()
        assert "list_tools" in registry.names()
    finally:
        hub.close()
