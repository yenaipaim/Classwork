"""唯一的装配点：配置 + 工具 + 后端 + 存档 → 会话。

界面层只需要调用 :func:`create_session`，不必知道工具是怎么注册的。
"""

from __future__ import annotations

from pathlib import Path

from .config import AppConfig
from .llm.backend import LlmBackend, OpenAIBackend
from .paths import DEFAULT_HISTORY_DIR, DEFAULT_WORKSPACE_ROOT
from .session import AgentSession
from .tools.builtins import get_date, is_leap_year
from .tools.files import FileToolbox
from .tools.spec import ToolRegistry, ToolSpec
from .transcript import Transcript


def build_registry(workspace_root: Path | str = DEFAULT_WORKSPACE_ROOT) -> ToolRegistry:
    """按旧版顺序注册 13 个工具。"""
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="get_date",
            description="获取当前电脑的本地日期、时间与星期",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=get_date,
        )
    )
    registry.register(
        ToolSpec(
            name="isLeapyear",
            description="判断指定年份是否为闰年（Python 计算）",
            parameters={
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "要判断的年份，例如 2024"}
                },
                "required": ["year"],
            },
            handler=is_leap_year,
        )
    )
    FileToolbox(workspace_root).register(registry)
    registry.register(
        ToolSpec(
            name="list_tools",
            description="列出当前程序注册的全部工具名称和用途",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=lambda: _list_tools(registry),
        )
    )
    return registry


def create_session(
    config: AppConfig,
    *,
    workspace_root: Path | str = DEFAULT_WORKSPACE_ROOT,
    history_dir: Path | str = DEFAULT_HISTORY_DIR,
    backend: LlmBackend | None = None,
    registry: ToolRegistry | None = None,
) -> AgentSession:
    """装配一个可直接驱动的会话；测试可注入 backend / registry。"""
    if backend is None:
        backend = OpenAIBackend(
            config.base_url, config.api_key, config.request_timeout
        )
    if registry is None:
        registry = build_registry(workspace_root)
    transcript = Transcript(history_dir, config.model_name)
    return AgentSession(backend, registry, config, transcript)


def _list_tools(registry: ToolRegistry) -> dict:
    tools = []
    for name in registry.names():
        tool = registry.get(name)
        if tool is not None:
            tools.append({"name": tool.name, "description": tool.description})
    return {"ok": True, "count": len(tools), "tools": tools}