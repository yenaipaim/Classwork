"""把通过校验的 MCP Server 注册成 Agent 工具。

工具名默认保持 Server 里的原名，这样模型看到的和 Server 文档一致；与本地工具
（RunCli、fetchWeb 等）或另一家 Server 撞名时加 `<服务器>__<工具>` 前缀。
OpenAI 兼容接口只接受 `[A-Za-z0-9_-]`，纯中文的工具名会被替换成
`tool_1`、`tool_2` 这样的占位名——原名写进描述里，模型仍能按描述挑选。
映射关系留在 :attr:`McpHub.mapping` 里，调用时据此找回原来的 Server 与工具名。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from ..tools.spec import ToolOutcome, ToolRegistry, ToolSpec
from .config import McpConfig, McpServerConfig
from .connection import McpConnection, input_schema

#: OpenAI 兼容接口对函数名的限制：字母数字下划线短横线，最长 64
MAX_TOOL_NAME = 64
_NAME_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")
#: 描述会进入 System Prompt，过长的营销文案没有意义
_MAX_DESCRIPTION = 1024


@dataclass(frozen=True, slots=True)
class McpToolInfo:
    """一家 MCP Server 上的工具在 Agent 里的最终形态。"""

    server: str
    name: str
    exposed: str
    description: str


@dataclass(frozen=True, slots=True)
class McpServerStatus:
    """给界面层展示的连接状态。"""

    name: str
    transport: str
    target: str
    enabled: bool
    connected: bool
    tool_count: int
    error: str


class McpHub:
    """持有所有 MCP 连接，负责命名、注册与状态查询。"""

    def __init__(self, config: McpConfig) -> None:
        self._config = config
        self._connections = [McpConnection(server) for server in config.servers]
        self._mapping: dict[str, tuple[McpConnection, str]] = {}
        self._tools: tuple[McpToolInfo, ...] = ()

    # ---------------------------------------------------------------- 属性

    @property
    def config(self) -> McpConfig:
        return self._config

    @property
    def issues(self) -> tuple[Any, ...]:
        return self._config.issues

    @property
    def connections(self) -> tuple[McpConnection, ...]:
        return tuple(self._connections)

    @property
    def tools(self) -> tuple[McpToolInfo, ...]:
        return self._tools

    @property
    def mapping(self) -> Mapping[str, tuple[McpConnection, str]]:
        """LLM 看到的工具名 → (连接, Server 内部工具名)。"""
        return dict(self._mapping)

    # ---------------------------------------------------------------- 生命周期

    def start(self) -> None:
        """并行连接所有 Server，整体最多等最长的 connect_timeout 秒。"""
        active = [item for item in self._connections if item.config.enabled]
        if not active:
            return
        for connection in active:
            connection.launch()
        deadline = time.monotonic() + max(
            connection.config.connect_timeout for connection in active
        )
        for connection in active:
            remaining = deadline - time.monotonic()
            connection.wait_ready(max(0.0, remaining))

    def close(self) -> None:
        for connection in self._connections:
            connection.stop()

    # ---------------------------------------------------------------- 注册

    def register_into(self, registry: ToolRegistry) -> None:
        """把已连接 Server 的工具追加到注册表（可重复调用，如切换工作区）。"""
        groups = [
            (connection.name, connection.tools)
            for connection in self._connections
            if connection.connected
        ]
        plans = plan_tool_names(groups, registry.names())
        self._mapping = {}
        tools: list[McpToolInfo] = []
        for connection in self._connections:
            if not connection.connected:
                continue
            for tool in connection.tools:
                exposed = plans[(connection.name, tool.name)]
                description = _describe(connection.name, tool, exposed)
                registry.register(
                    ToolSpec(
                        name=exposed,
                        description=description,
                        parameters=input_schema(tool),
                        handler=self._handler(connection, tool.name),
                    )
                )
                self._mapping[exposed] = (connection, tool.name)
                tools.append(
                    McpToolInfo(
                        server=connection.name,
                        name=tool.name,
                        exposed=exposed,
                        description=description,
                    )
                )
        self._tools = tuple(tools)

    def status(self) -> list[McpServerStatus]:
        rows = []
        for connection in self._connections:
            server = connection.config
            rows.append(
                McpServerStatus(
                    name=server.name,
                    transport=server.transport or "未启用",
                    target=server.target or "—",
                    enabled=server.enabled,
                    connected=connection.connected,
                    tool_count=len(connection.tools),
                    error=connection.error or "",
                )
            )
        return rows

    # ---------------------------------------------------------------- 内部

    def _handler(self, connection: McpConnection, tool_name: str):
        def handler(**arguments: Any) -> ToolOutcome:
            return connection.call_tool(tool_name, arguments)

        return handler


def plan_tool_names(
    servers: Sequence[tuple[str, Sequence[Any]]],
    reserved: Iterable[str] = (),
) -> dict[tuple[str, str], str]:
    """为每家 Server 的每个工具规划唯一、合法、≤64 字符的暴露名。

    `reserved` 是本地工具名：撞上它们或撞上另一家 Server 的同名工具时，
    改用 `<server>__<tool>`；若仍冲突，则继续加 `_2`、`_3` 后缀。
    """
    reserved_keys = {str(name).lower() for name in reserved}
    entries: list[tuple[str, str, str, str]] = []
    for server_name, tools in servers:
        prefix = _sanitize(server_name) or "mcp"
        for index, tool in enumerate(tools, start=1):
            tool_name = str(getattr(tool, "name", "") or "")
            # 纯中文（或其它非 ASCII）工具名清洗后为空，用编号占位并保证可预测
            base = _sanitize(tool_name) or "tool_%d" % index
            entries.append((server_name, tool_name, base, prefix))

    counts: dict[str, int] = {}
    for _, _, base, _ in entries:
        key = base.lower()
        counts[key] = counts.get(key, 0) + 1

    used = set(reserved_keys)
    plans: dict[tuple[str, str], str] = {}
    for server_name, tool_name, base, prefix in entries:
        candidate = base
        if counts[base.lower()] > 1 or base.lower() in reserved_keys:
            candidate = "%s__%s" % (prefix, base)
        stem = _fit(candidate)
        final = stem
        counter = 2
        while final.lower() in used:
            suffix = "_%d" % counter
            final = _fit(stem, MAX_TOOL_NAME - len(suffix)) + suffix
            counter += 1
        used.add(final.lower())
        plans[(server_name, tool_name)] = final
    return plans


def _sanitize(raw: str) -> str:
    cleaned = _NAME_PATTERN.sub("_", raw).strip("_-")
    return cleaned


def _fit(name: str, limit: int = MAX_TOOL_NAME) -> str:
    if len(name) <= limit:
        return name or "tool"
    return name[:limit].rstrip("_-") or "tool"


def _describe(server: str, tool: Any, exposed: str = "") -> str:
    original = str(getattr(tool, "name", "") or "").strip()
    text = str(getattr(tool, "description", "") or "").strip()
    if not text:
        text = "调用 MCP 工具 %s" % original
    text = " ".join(text.split())
    if len(text) > _MAX_DESCRIPTION:
        text = text[:_MAX_DESCRIPTION] + "…"
    if original and original != exposed:
        # 暴露名被清洗或加了前缀时带上原名，模型按中文描述仍能认出工具
        return "「%s」%s（MCP 服务：%s）" % (original, text, server)
    return "%s（MCP 服务：%s）" % (text, server)
