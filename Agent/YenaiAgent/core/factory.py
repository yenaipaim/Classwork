"""唯一的装配点：配置 + 工具 + 后端 + 存档 → 会话。

界面层只需要调用 :func:`create_session`，不必知道工具是怎么注册的。
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .archive import ContextArchive
from .config import AppConfig
from .constants import CONTEXT_ARCHIVE_DIR, SESSIONS_DIR
from .llm.backend import LlmBackend, OpenAIBackend
from .mcp import McpConfig, McpHub, discover_mcp_config, load_mcp_config
from .paths import DEFAULT_HISTORY_DIR, DEFAULT_WORKSPACE_ROOT, context_archive_dir
from .recall import build_recall_tool
from .session import AgentSession
from .sessions import SessionStore
from .skills import (
    SkillLibrary,
    build_create_skill_tool,
    build_load_skill_tool,
    resolve_skill_roots,
)
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
    mcp: McpHub | None = None,
    archive: ContextArchive | None = None,
) -> ToolRegistry:
    """按旧版顺序注册文件/计算工具，末尾追加联网、网页、命令行、技能、MCP 与工具清单。

    ``skills`` 非空时追加 ``loadSkill``（按需加载）与 ``createSkill``（新建技能）
    两个工具；``mcp`` 非空时把已连接的 MCP 工具追加在技能之后。``list_tools``
    始终最后注册，才能把前面的工具都列进去。``archive`` 非空时再追加
    ``recallContext``（按关键词检索压缩前的上下文归档）。
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
    # 技能工具只在有 SkillLibrary 时注册；createSkill 连「一个技能都还没有」的空库也
    # 要可用——新建第一个技能正是它最有用武之地的时候。
    if skills is not None:
        if skills:
            registry.register(build_load_skill_tool(skills))
        registry.register(build_create_skill_tool(skills))
    # MCP 工具排在技能之后、list_tools 之前；连不上的 Server 已在 hub 里被跳过
    if mcp is not None:
        mcp.register_into(registry)
    # 归档目录存在时才注册 recallContext：没有归档就没有可检索的历史
    if archive is not None:
        registry.register(build_recall_tool(archive))
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
    skill_roots: Sequence[str] | None = None,
    mcp_config: McpConfig | Path | str | None = None,
    mcp: McpHub | None = None,
    context_dir: Path | str | None = None,
) -> AgentSession:
    """装配一个可直接驱动的会话；测试可注入 backend / registry / skills / MCP。

    ``project_root`` 默认取程序启动时的工作目录，Skill 扫描根固定跟随它，不受
    运行中切换工作区的影响。扫描根默认是 ``<project_root>/.agents/skills/``，也可
    由 ``config.ini`` 的 ``[skills] roots`` 或 ``skill_roots`` 追加/替换。

    MCP 配置与技能目录同源：第一个技能根（默认 ``<project_root>/.agents/skills/``）
    下的 ``.mcp.json`` 缺失时自动写入模板；也可用 ``YENAI_MCP_CONFIG`` 指定别的
    文件或设为 off 关闭。``mcp_config`` 可直接给已解析的 :class:`McpConfig`
    或文件路径，``mcp`` 则用于注入现成的 :class:`McpHub`（测试与复用）。
    """
    if backend is None:
        backend = OpenAIBackend(
            config.base_url, config.api_key, config.request_timeout
        )
    # 搜索配置只读一次：换工作区时重建注册表，密钥与接口地址原样带过去；
    # 抓取与命令行工具不依赖配置，随注册表按新工作区重新创建（RunCli 的
    # cwd 会变成新工作区）。
    search_client = SearchClient(
        config.search_api_key,
        endpoint=config.search_endpoint,
        timeout=config.search_timeout,
        top_k=config.search_top_k,
    )
    base_root = Path.cwd() if project_root is None else Path(project_root)
    # 上下文归档目录与会话同寿命：换工作区不影响它（归档属于会话，不属于工作区）
    if context_dir is not None:
        archive_dir = Path(context_dir)
    else:
        archive_dir = context_archive_dir(base_root)
        if config.archive_dir and Path(config.archive_dir) != Path(CONTEXT_ARCHIVE_DIR):
            archive_dir = Path(config.archive_dir).expanduser()
            if not archive_dir.is_absolute():
                archive_dir = base_root / archive_dir
    archive = ContextArchive(
        archive_dir,
        max_snippets=config.recall_max_snippets,
        max_chars=config.recall_max_chars,
    )
    # 会话事件日志：/new、/resume、/save 的事实来源
    sessions_dir = Path(config.sessions_dir or SESSIONS_DIR).expanduser()
    if not sessions_dir.is_absolute():
        sessions_dir = base_root / sessions_dir
    session_store = SessionStore(sessions_dir, config.model_name)
    # Skill 清单只在初始化时扫描一次；切换工作区重建注册表时复用同一份清单
    if skills is None:
        base = base_root
        # 显式参数优先，其次读配置；都为空时就是默认的 .agents/skills
        configured = tuple(skill_roots) if skill_roots else tuple(config.skill_roots)
        skills = SkillLibrary(base, roots=resolve_skill_roots(base, configured))

    # MCP 连接与配置只在会话创建时建立一次；切换工作区重建注册表时复用同一批会话
    hub = mcp
    if hub is None:
        source = mcp_config if mcp_config is not None else (config.mcp_config or None)
        parsed = _resolve_mcp_config(source, project_root, skills.skills_dir)
        hub = McpHub(parsed)
        # 异步连接：TUI 先进场，连上后再把工具挂进注册表、刷新边栏
        hub.start_async()

    def registry_factory(root: Path | str) -> ToolRegistry:
        return build_registry(
            root,
            search_client=search_client,
            fetcher=WebFetcher(
                timeout=config.fetch_timeout, max_chars=config.fetch_max_chars
            ),
            cli_runner=CommandRunner(
                cwd=str(root),
                timeout=config.cli_timeout,
                max_timeout=config.cli_max_timeout,
                max_output=config.cli_max_output,
            ),
            skills=skills,
            mcp=hub,
            archive=archive,
        )

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
        mcp=hub,
        archive=archive,
        sessions=session_store,
        project_root=base_root,
    )


def _resolve_mcp_config(
    source: McpConfig | Path | str | None,
    project_root: Path | str | None,
    skills_dir: Path | str | None = None,
) -> McpConfig:
    """显式配置优先，否则用技能目录里的 ``.mcp.json``（缺失时生成模板）。"""
    if isinstance(source, McpConfig):
        return source
    if source is None:
        return discover_mcp_config(skills_dir, project_root=project_root)
    path = Path(source).expanduser()
    if not path.is_absolute():
        base = Path(project_root) if project_root is not None else Path.cwd()
        path = base / path
    return load_mcp_config(path)


def _list_tools(registry: ToolRegistry) -> dict:
    tools = []
    for name in registry.names():
        tool = registry.get(name)
        if tool is not None:
            tools.append({"name": tool.name, "description": tool.description})
    return {"ok": True, "count": len(tools), "tools": tools}