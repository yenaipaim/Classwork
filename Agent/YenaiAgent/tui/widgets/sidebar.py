"""右侧 MCP 边栏：显示已连接的服务及其注册进 Agent 的工具。

MCP 是异步加载的：界面先起来，边栏先显示“连接中”，连上之后由 App 的
轮询定时器调用 :meth:`McpSidebar.show_hub` 原地刷新，不阻塞启动。
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from core.mcp.hub import McpHub

from ..i18n import (
    MCP_SIDEBAR_LOADING,
    MCP_SIDEBAR_NONE,
    MCP_SIDEBAR_SERVER_DISABLED,
    MCP_SIDEBAR_SERVER_FAILED,
    MCP_SIDEBAR_SERVER_OK,
    MCP_SIDEBAR_TITLE,
    MCP_SIDEBAR_TOOL,
)

#: 单个服务最多列出的工具条数，避免边栏被超长工具清单挤爆
MAX_TOOLS_PER_SERVER = 60


class McpSidebar(VerticalScroll):
    """MCP 服务器与工具清单；没有会话或没有配置时给出对应提示。"""

    def compose(self) -> ComposeResult:
        yield Static(MCP_SIDEBAR_TITLE, id="mcp-sidebar-title")
        yield Static(MCP_SIDEBAR_LOADING, id="mcp-sidebar-body", markup=False)

    def show_loading(self) -> None:
        self._write(MCP_SIDEBAR_LOADING)

    def show_unavailable(self) -> None:
        self._write(MCP_SIDEBAR_NONE)

    def show_hub(self, hub: McpHub | None) -> None:
        """按当前连接状态刷新：先服务，再每个服务下的工具名。"""
        if hub is None or not hub.config.configured:
            self.show_unavailable()
            return
        if hub.loading:
            self.show_loading()
            return
        rows = hub.status()
        if not rows:
            self.show_unavailable()
            return
        tools_by_server: dict[str, list[str]] = {}
        for info in hub.tools:
            tools_by_server.setdefault(info.server, []).append(info.exposed)
        lines: list[str] = []
        for row in rows:
            if not row.enabled:
                lines.append(MCP_SIDEBAR_SERVER_DISABLED % row.name)
                continue
            if not row.connected:
                lines.append(MCP_SIDEBAR_SERVER_FAILED % row.name)
                continue
            lines.append(MCP_SIDEBAR_SERVER_OK % (row.name, row.tool_count))
            names = tools_by_server.get(row.name, [])
            for name in names[:MAX_TOOLS_PER_SERVER]:
                lines.append(MCP_SIDEBAR_TOOL % name)
            if len(names) > MAX_TOOLS_PER_SERVER:
                lines.append(MCP_SIDEBAR_TOOL % ("… 其余 %d 个" % (len(names) - MAX_TOOLS_PER_SERVER)))
        self._write("\n".join(lines))

    def _write(self, text: str) -> None:
        try:
            body = self.query_one("#mcp-sidebar-body", Static)
        except Exception:
            return
        body.update(text)
