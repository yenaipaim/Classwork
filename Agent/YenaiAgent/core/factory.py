"""唯一的装配点：配置 + 工具 + 后端 + 存档 → 会话。

界面层只需要调用 :func:`create_session`，不必知道工具是怎么注册的。
"""

from __future__ import annotations

from pathlib import Path

from .config import AppConfig
from .llm.backend import LlmBackend, OpenAIBackend
from .paths import DEFAULT_HISTORY_DIR, DEFAULT_WORKSPACE_ROOT
from .session import AgentSession
from .skills import SkillLibrary, build_load_skill_tool
from .tools.builtins import get_date, is_leap_year
from .tools.cli import CommandRunner, build_cli_tool
from .tools.files import FileToolbox
from .tools.search import SearchClient, build_search_tool
from .tools.spec import ToolRegistry, ToolSpec
from .tools.web import WebFetcher, build_fetch_tool
from .transcript import Transcript


def build_registry(
    workspace_root: Path | str = DEFAULT_WORKSPACE_ROOT,
    *,
    search_client: SearchClient | None = None,
    fetcher: WebFetcher | None = None,
    cli_runner: CommandRunner | None = None,
    skills: SkillLibrary | None = None,
) -> ToolRegistry:
    """按旧版顺序注册文件/计算工具，末尾追加联网、网页、命令行、技能与工具清单。

    ``skills`` 非空时追加 ``loadSkill`` 工具；为空或未传时注册表与旧版完全一致。
    """
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
        build_search_tool(search_client if search_client is not None else SearchClient(""))
    )
    registry.register(build_fetch_tool(fetcher if fetcher is not None else WebFetcher()))
    registry.register(
        build_cli_tool(
            cli_runner
            if cli_runner is not None
            else CommandRunner(cwd=str(workspace_root))
        )
    )
    if skills:
        registry.register(build_load_skill_tool(skills))
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
    project_root: Path | str | None = None,
    skills: SkillLibrary | None = None,
) -> AgentSession:
    """装配一个可直接驱动的会话；测试可注入 backend / registry / skills。

    ``project_root`` 默认取程序启动时的工作目录，Skill 扫描根（``.agents/skills/``）
    固定跟随它，不受运行中切换工作区的影响。
    """
    if backend is None:
        backend = OpenAIBackend(
            config.base_url, config.api_key, config.request_timeout
        )
    # 搜索配置只读一次：换工作区时重建注册表，密钥与接口地址原样带过去；
    # 抓取与命令行工具不依赖配置，随注册表按新工作区重新创建（RunCli 的
    # cwd 会变成新工作区）。
    search_client = SearchClient(
        config.search_api_key, endpoint=config.search_endpoint
    )
    # Skill 清单只在初始化时扫描一次；切换工作区重建注册表时复用同一份清单
    if skills is None:
        skills = SkillLibrary(Path.cwd() if project_root is None else project_root)

    def registry_factory(root: Path | str) -> ToolRegistry:
        return build_registry(root, search_client=search_client, skills=skills)

    if registry is None:
        registry = registry_factory(workspace_root)
    transcript = Transcript(history_dir, config.model_name)
    return AgentSession(
        backend,
        registry,
        config,
        transcript,
        registry_factory=registry_factory,
        skills=skills,
    )


def _list_tools(registry: ToolRegistry) -> dict:
    tools = []
    for name in registry.names():
        tool = registry.get(name)
        if tool is not None:
            tools.append({"name": tool.name, "description": tool.description})
    return {"ok": True, "count": len(tools), "tools": tools}