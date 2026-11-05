"""Textual 应用：只处理输入、展示与命令，业务全部交给 core。

线程模型：``ask()`` 是阻塞的生成器，放在后台 worker 线程里跑；
每个事件通过 ``call_from_thread`` 回到 UI 线程处理，界面因而不会被网络卡住。
"""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.timer import Timer
from textual.widgets import Footer, Header, Static

from core.budget import ContextUsage
from core.config import (
    MOCK_API_KEY,
    MOCK_BASE_URL,
    MOCK_MODEL_NAME,
    AppConfig,
    ConfigStore,
)
from core.constants import CONTEXT_WARN_RATIO
from core.errors import AgentError, ConfigError
from core.events import (
    AgentEvent,
    CompactionArchived,
    CompactionCompleted,
    CompactionFailed,
    CompactionStarted,
    ContextWarning,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
    TurnCancelled,
    TurnCompleted,
    TurnFailed,
)
from core.factory import create_session
from core.llm.backend import LlmBackend
from core.paths import DEFAULT_CONFIG_PATH, DEFAULT_HISTORY_DIR, DEFAULT_WORKSPACE_ROOT
from core.session import AgentSession, CancelToken

from .i18n import (
    APP_SUBTITLE,
    APP_TITLE,
    CANCELLED,
    CANCELLING,
    CONFIG_CANCELLED,
    COMPACT_ARCHIVED,
    COMPACT_BUSY,
    COMPACT_DONE,
    COMPACT_FAILED_HINT,
    COMPACT_NEED_SESSION,
    COMPACT_RUNNING,
    COMPACT_STARTED,
    CONFIG_SAVED,
    CONTEXT_BAR,
    CONTEXT_BAR_DEFAULT,
    CONTEXT_BAR_EMPTY,
    CONTEXT_CLEARED,
    CONTEXT_PAUSED,
    CONTEXT_WARNING,
    AGENTS_MD_LOADED,
    BUSY_TURN,
    CONFIG_WRITE_FAILED,
    AGENTS_MD_NONE,
    FIRST_RUN_HINT,
    HELP_TEXT,
    INPUT_PLACEHOLDER,
    MCP_HEADER,
    MCP_ISSUES,
    MCP_ISSUE_ITEM,
    MCP_ITEM,
    MCP_ITEM_DISABLED,
    MCP_ITEM_FAILED,
    MCP_NEED_SESSION,
    MCP_NONE,
    MCP_STARTUP_FAILED,
    MCP_STARTUP_OK,
    MCP_TEMPLATE_CREATED,
    MOCK_CONFIG_WARNING,
    MODEL_SWITCHED,
    MODEL_USAGE,
    NEED_CONFIG,
    READY,
    SESSION_EXPORT_FAILED,
    SESSION_EXPORT_OK,
    SESSION_LIST_EMPTY,
    SESSION_LIST_HEADER,
    SESSION_LIST_ROW,
    SESSION_LOG_OFF,
    SESSION_NEW_OK,
    SESSION_NEW_PLAIN,
    SESSION_NEED_SESSION,
    SESSION_RESTORED,
    SESSION_RESTORE_FAILED,
    SESSION_RESUME_HINT,
    SESSION_SAVED,
    SESSION_SAVE_FAILED,
    SESSION_SAVE_NONE,
    STATUS_BLOCKED,
    STATUS_DISABLED,
    STATUS_ENABLED,
    STATUS_HEADER,
    STATUS_LOADING,
    STATUS_NONE,
    STATUS_OK,
    STATUS_ROW,
    SKILLS_ADD_HINT,
    SKILLS_ITEM,
    SKILLS_LOADED,
    SKILLS_NEED_SESSION,
    SKILLS_NONE,
    SKILLS_ROOT_ITEM,
    SKILLS_ROOTS_HEADER,
    SKILLS_SKIPPED,
    STATUS_THINKING_ELAPSED,
    STATUS_TOOL_RUNNING,
    THINKING,
    TOOLS_HEADER,
    TOOLS_ROW,
    UNKNOWN_COMMAND,
    WELCOME,
    WORKSPACE_SWITCHED,
    WORKSPACE_SWITCH_FAILED,
    WORKSPACE_USAGE,
    describe_error,
)
from .screens.config_screen import ConfigScreen
from .screens.first_run_screen import FirstRunScreen
from .screens.session_screen import SessionScreen
from .widgets.chat_input import ChatInput
from .widgets.chat_log import ChatLog
from .widgets.command_menu import CommandMenu
from .widgets.sidebar import McpSidebar

_FLUSH_INTERVAL = 0.05


def _one_line(text: str, limit: int) -> str:
    """压成一行并截断，用于 `/skills`、`/mcp` 这类状态展示。"""
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= limit else one_line[:limit] + "…"


def _token_text(value: int) -> str:
    """把 token 数写成 12.3k / 128k 这样的短形式，状态栏才放得下。"""
    if value < 1000:
        return str(value)
    if value % 1000 == 0:
        return "%dk" % (value // 1000)
    return "%.1fk" % (value / 1000)


def _context_text(usage: ContextUsage) -> tuple[str, str]:
    """返回占用条文案与配色类名（''/warn/danger）。

    数字前带 ``~`` 表示这一轮还没拿到接口返回的用量，是本地估算：
    估算只求量级正确（中文 1.6 字 / token），不要当精确值看。
    """
    percent = "%.1f%%" % (usage.ratio * 100)
    used = _token_text(usage.used)
    if usage.estimated:
        used = "~" + used
    template = CONTEXT_BAR_DEFAULT if usage.window_is_default else CONTEXT_BAR
    text = template % (used, _token_text(usage.window), percent)
    if usage.ratio >= 0.9:
        return text, "danger"
    if usage.ratio >= CONTEXT_WARN_RATIO:
        return text, "warn"
    return text, ""


def _skill_description(text: str, limit: int = 120) -> str:
    """技能描述压成一行，过长时截断，用于 `/skills` 展示。"""
    return _one_line(text, limit)


def _error_text(error: Exception) -> str:
    """异常转成一句用户能看懂的话。"""
    if isinstance(error, AgentError):
        return describe_error(error)
    return str(error)


def _is_mock_config(config: AppConfig) -> bool:
    """配置里还留着模板示例值时提醒：这样发请求一定连不上。"""
    return (
        config.base_url.rstrip("/") == MOCK_BASE_URL.rstrip("/")
        or config.api_key == MOCK_API_KEY
        or config.model_name == MOCK_MODEL_NAME
    )


class YenaiApp(App[None]):
    """YenaiAgent 的终端界面。"""

    CSS_PATH = "styles.tcss"
    TITLE = APP_TITLE
    SUB_TITLE = APP_SUBTITLE

    BINDINGS = [
        # priority=True 保证输入框聚焦时 Ctrl+C 仍然是“中断/退出”，
        # 而不是被 TextArea 自带的“复制”抢走。
        Binding("ctrl+q", "quit_app", "退出", priority=True),
        Binding("ctrl+c", "interrupt", "中断", priority=True),
        Binding("ctrl+l", "clear_screen", "清屏", priority=True),
    ]

    def __init__(
        self,
        *,
        config_path: Path | str | None = None,
        history_dir: Path | str | None = None,
        workspace_root: Path | str | None = None,
        backend: LlmBackend | None = None,
        session: AgentSession | None = None,
        store: ConfigStore | None = None,
        skill_dirs: Sequence[Path | str] | None = None,
    ) -> None:
        super().__init__()
        self._store = store or ConfigStore(config_path or DEFAULT_CONFIG_PATH)
        self._history_dir = Path(history_dir or DEFAULT_HISTORY_DIR)
        self._workspace_root = Path(workspace_root or DEFAULT_WORKSPACE_ROOT)
        self._backend = backend
        self._session = session
        # 额外的技能根目录：命令行/环境变量传入，最终交给 create_session
        self._skill_dirs = tuple(skill_dirs or ())

        self._cancel = CancelToken()
        self._worker = None
        self._turn_busy = False
        self._cancelling = False
        self._stream_parts: list[str] = []
        self._flush_timer: Timer | None = None
        self._status_timer: Timer | None = None
        self._turn_started = 0.0
        self._tool_calls = 0
        self._current_tool: str | None = None
        self._tool_starts: dict[str, list[float]] = {}
        # 压缩是独立于问答的一轮后台任务，期间同样禁止输入
        self._compacting = False
        # MCP 异步加载：先用定时器轮询，连上后刷新边栏并注册工具
        self._mcp_timer: Timer | None = None

    # ---------------------------------------------------------------- 布局

    def compose(self) -> ComposeResult:
        yield Header()
        # 左边是聊天区，右边是 MCP 边栏（服务与工具清单）
        with Horizontal(id="body"):
            yield ChatLog(id="chat")
            yield McpSidebar(id="sidebar")
        # 命令候选紧贴输入框，平时收起（CSS display: none）
        yield CommandMenu(id="commands")
        # 上下文占用条固定显示在输入框上方，随时可见
        yield Static(CONTEXT_BAR_EMPTY, id="context")
        yield Static(READY, id="status")
        yield ChatInput(placeholder=INPUT_PLACEHOLDER, id="prompt")
        yield Footer()

    def on_mount(self) -> None:
        self._chat = self.query_one("#chat", ChatLog)
        self._status = self.query_one("#status", Static)
        # 注意别叫 _context：Textual 的 App 自己有个 _context() 方法
        self._context_bar = self.query_one("#context", Static)
        self._prompt = self.query_one("#prompt", ChatInput)
        self._commands = self.query_one("#commands", CommandMenu)
        self._sidebar = self.query_one("#sidebar", McpSidebar)
        self._prompt.menu = self._commands
        self._chat.add_system(WELCOME)
        self._refresh_context()
        self._prompt.focus()

        if self._session is not None:
            self._start_mcp_watch()
            return
        # 没有配置文件时先落一份带示例值的完整模板，再弹框提示改完重启
        try:
            created = self._store.ensure_template()
        except OSError as exc:
            self._chat.add_system(CONFIG_WRITE_FAILED % exc, kind="error")
            created = False
        if created:
            self._sidebar.show_unavailable()
            self.push_screen(FirstRunScreen(self._store.path), self._after_first_run)
            return
        try:
            config = self._store.load()
        except ConfigError:
            self._open_config()
        else:
            self._install_config(config)

    def _after_first_run(self, result: object | None = None) -> None:
        """模板里的都是示例值，改完重启才有意义，所以读完提示就退出。"""
        self.exit()

    # ---------------------------------------------------------------- 配置

    def _open_config(self) -> None:
        current: AppConfig | None = None
        try:
            if self._store.exists():
                current = self._store.load()
        except ConfigError:
            current = None

        self.push_screen(
            ConfigScreen(
                self._store,
                base_url=current.base_url if current else "",
                api_key=current.api_key if current else "",
                model_name=current.model_name if current else "",
            ),
            self._after_config,
        )

    def _after_config(self, result: AppConfig | None) -> None:
        if result is None:
            if self._session is None:
                self._chat.add_system(CONFIG_CANCELLED, kind="error")
                self.exit()
            else:
                self._status.update(READY)
                self._prompt.focus()
            return

        self._install_config(result)
        self._chat.add_system(CONFIG_SAVED)
        self._prompt.focus()

    def _install_config(self, config: AppConfig) -> None:
        # 重新配置等于换一个会话：先把旧会话的 MCP 子进程 / 连接收掉
        if self._session is not None:
            self._session.close()
        self._session = create_session(
            config,
            workspace_root=self._workspace_root,
            history_dir=self._history_dir,
            backend=self._backend,
            skill_roots=self._skill_dirs or None,
        )
        self._status.update(READY)
        self._start_mcp_watch()
        self._refresh_context()
        if _is_mock_config(config):
            self._chat.add_system(MOCK_CONFIG_WARNING % self._store.path, kind="warn")

    # ---------------------------------------------------------------- MCP 异步

    def _start_mcp_watch(self) -> None:
        """MCP 在后台线程里连：先把边栏画成加载中，连上后原地刷新。"""
        hub = self._session.mcp if self._session is not None else None
        self._sidebar.show_hub(hub)
        if hub is None or not hub.config.configured:
            return
        if not hub.loading:
            # 已经连完（例如启动时就是同步完成的），直接收尾
            self._mcp_ready()
            return
        self._stop_mcp_timer()
        self._mcp_timer = self.set_interval(0.2, self._poll_mcp)

    def _poll_mcp(self) -> None:
        hub = self._session.mcp if self._session is not None else None
        if hub is None or not hub.loading:
            self._mcp_ready()

    def _mcp_ready(self) -> None:
        """加载结束：注册 MCP 工具、刷新边栏与占用条，并汇报结果。"""
        self._stop_mcp_timer()
        session = self._session
        if session is None:
            return
        hub = session.mcp
        if hub is None:
            self._sidebar.show_unavailable()
            return
        try:
            session.sync_mcp_tools()
        except (AgentError, ValueError) as exc:
            # 注册失败只影响 MCP 工具，界面与本地工具照常可用
            self._chat.add_system("MCP 工具注册失败：%s" % exc, kind="error")
        self._sidebar.show_hub(hub)
        self._report_mcp_startup()
        self._refresh_context()

    def _stop_mcp_timer(self) -> None:
        if self._mcp_timer is not None:
            self._mcp_timer.stop()
            self._mcp_timer = None

    def _require_session(self) -> AgentSession | None:
        if self._session is None:
            self._chat.add_system(NEED_CONFIG, kind="error")
            return None
        return self._session

    # ---------------------------------------------------------------- 输入

    def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        self._prompt.reset()
        value = event.text.strip()
        if not value or self._turn_busy:
            return
        if value.startswith("/"):
            self._run_command(value)
            return
        # 达到阈值后暂停普通提问，直到压缩成功（/compact、/reset 仍可用）
        if self._session is not None and self._session.compact_required:
            self._chat.add_system(CONTEXT_PAUSED, kind="warn")
            self._refresh_context()
            return
        self._start_turn(value)

    def _run_command(self, raw: str) -> None:
        parts = raw.split(maxsplit=1)
        command = parts[0].lower()
        argument = parts[1].strip() if len(parts) > 1 else ""
        if command == "/exit":
            self.exit()
        elif command == "/help":
            self._chat.add_system(HELP_TEXT)
        elif command == "/clear":
            self._chat.clear_messages()
        elif command == "/reset":
            if self._session is not None:
                self._session.reset()
            self._chat.add_system(CONTEXT_CLEARED)
            self._refresh_context()
        elif command == "/compact":
            self._start_compact()
        elif command == "/config":
            self._open_config()
        elif command == "/model":
            self._switch_model(argument)
        elif command == "/workspace":
            self._switch_workspace(argument)
        elif command == "/skills":
            self._show_skills()
        elif command == "/mcp":
            self._show_mcp()
        elif command == "/new":
            self._new_session()
        elif command == "/resume":
            self._open_resume(argument)
        elif command == "/sessions":
            self._show_sessions()
        elif command == "/save":
            self._save_session()
        elif command == "/export":
            self._export_session(argument)
        elif command == "/status":
            self._show_status()
        elif command == "/tools":
            self._show_tools()
        elif command == "/quit":
            self.exit()
        else:
            self._chat.add_system(UNKNOWN_COMMAND % raw, kind="error")

    def _switch_model(self, name: str) -> None:
        """`/model` 查看当前模型，`/model 名称` 切换并写回 config.ini。"""
        if self._session is None:
            self._chat.add_system(NEED_CONFIG, kind="error")
            self._open_config()
            return
        if not name:
            self._chat.add_system(MODEL_USAGE % self._session.config.model_name)
            return

        config = replace(self._session.config, model_name=name)
        try:
            saved = self._store.save(
                config.base_url, config.api_key, config.model_name
            )
        except (ConfigError, OSError) as exc:
            detail = describe_error(exc) if isinstance(exc, ConfigError) else str(exc)
            self._chat.add_system("切换失败：%s" % detail, kind="error")
            return
        self._session.switch_model(saved)
        self._chat.add_system(MODEL_SWITCHED % saved.model_name)
        self._refresh_context()

    def _switch_workspace(self, raw: str) -> None:
        """`/workspace` 查看当前工作区，`/workspace 目录` 切换工具范围。"""
        if self._session is None:
            self._chat.add_system(NEED_CONFIG, kind="error")
            self._open_config()
            return
        if not raw:
            self._chat.add_system(WORKSPACE_USAGE % str(self._workspace_root))
            return
        try:
            new_root = self._session.switch_workspace(raw)
        except AgentError as exc:
            self._chat.add_system(
                WORKSPACE_SWITCH_FAILED % describe_error(exc), kind="error"
            )
            return
        except OSError as exc:
            self._chat.add_system(
                WORKSPACE_SWITCH_FAILED % str(exc), kind="error"
            )
            return
        self._workspace_root = new_root
        self._chat.add_system(WORKSPACE_SWITCHED % new_root)

    def _show_skills(self) -> None:
        """`/skills` 查看技能扫描目录、已加载清单与跳过原因。"""
        if self._session is None:
            self._chat.add_system(SKILLS_NEED_SESSION, kind="error")
            return
        skills = self._session.skills
        if skills is None:
            self._chat.add_system("\n".join([SKILLS_NONE, SKILLS_ADD_HINT]))
            return
        roots = skills.roots
        lines = [SKILLS_ROOTS_HEADER % len(roots)]
        lines.extend(SKILLS_ROOT_ITEM % str(root) for root in roots)
        self._chat.add_system("\n".join(lines))
        if skills:
            lines = [SKILLS_LOADED % len(skills.skills)]
            lines.extend(
                SKILLS_ITEM % (info.name, _skill_description(info.description))
                for info in skills.skills
            )
            self._chat.add_system("\n".join(lines))
        else:
            self._chat.add_system("\n".join([SKILLS_NONE, SKILLS_ADD_HINT]))
        if skills.skipped:
            lines = [SKILLS_SKIPPED % len(skills.skipped)]
            lines.extend(
                SKILLS_ITEM % (Path(item["directory"]).name, item["reason"])
                for item in skills.skipped
            )
            self._chat.add_system("\n".join(lines))

    def _show_mcp(self) -> None:
        """`/mcp` 查看每个 MCP Server 的连接状态与已注册工具数。"""
        if self._session is None:
            self._chat.add_system(MCP_NEED_SESSION, kind="error")
            return
        hub = self._session.mcp
        if hub is None or not hub.config.configured:
            self._chat.add_system(MCP_NONE)
            return
        rows = hub.status()
        location = str(hub.config.path) if hub.config.path is not None else "—"
        lines = [MCP_HEADER % (len(rows), location)]
        for row in rows:
            if not row.enabled:
                lines.append(MCP_ITEM_DISABLED % row.name)
            elif row.connected:
                lines.append(
                    MCP_ITEM % (row.name, row.transport, row.target, row.tool_count)
                )
            else:
                lines.append(
                    MCP_ITEM_FAILED
                    % (
                        row.name,
                        row.transport,
                        row.target,
                        _one_line(row.error or "未知原因", 200),
                    )
                )
        self._chat.add_system("\n".join(lines))
        if hub.issues:
            issues = "\n".join(MCP_ISSUE_ITEM % str(item) for item in hub.issues)
            self._chat.add_system(
                MCP_ISSUES % len(hub.issues) + "\n" + issues, kind="warn"
            )

    def _report_mcp_startup(self) -> None:
        """启动/换配置后提示 MCP 结果；没配置 MCP 时不打扰用户。"""
        hub = self._session.mcp if self._session is not None else None
        if hub is None or not hub.config.configured:
            return
        if hub.config.created and hub.config.path is not None:
            self._chat.add_system(MCP_TEMPLATE_CREATED % str(hub.config.path))
        rows = hub.status()
        failed = [row for row in rows if row.enabled and not row.connected]
        connected = [row for row in rows if row.connected]
        if failed:
            names = "、".join(row.name for row in failed)
            self._chat.add_system(
                MCP_STARTUP_FAILED % (len(failed), names), kind="warn"
            )
        if connected:
            self._chat.add_system(
                MCP_STARTUP_OK
                % (len(connected), sum(row.tool_count for row in connected))
            )
        if hub.issues:
            issues = "\n".join(MCP_ISSUE_ITEM % str(item) for item in hub.issues)
            self._chat.add_system(
                MCP_ISSUES % len(hub.issues) + "\n" + issues, kind="warn"
            )

    # ------------------------------------------------------------ 会话管理

    def _new_session(self) -> None:
        """/new：先保存当前会话，再换一份新的会话日志。"""
        session = self._require_session()
        if session is None:
            return
        if self._turn_busy:
            self._chat.add_system(BUSY_TURN, kind="warn")
            return
        try:
            session.save_session()
            new_id = session.new_session()
        except (AgentError, OSError) as exc:
            self._chat.add_system(SESSION_SAVE_FAILED % _error_text(exc), kind="error")
            return
        self._chat.clear_messages()
        self._chat.add_system(WELCOME)
        self._chat.add_system(SESSION_NEW_OK % new_id if new_id else SESSION_NEW_PLAIN)
        self._refresh_context()
        self._prompt.focus()

    def _save_session(self) -> None:
        """/save：把会话事件日志刷到磁盘。"""
        session = self._require_session()
        if session is None:
            return
        try:
            path = session.save_session()
        except (AgentError, OSError) as exc:
            self._chat.add_system(SESSION_SAVE_FAILED % _error_text(exc), kind="error")
            return
        if path is None:
            self._chat.add_system(SESSION_SAVE_NONE, kind="warn")
            return
        self._chat.add_system(SESSION_SAVED % path)

    def _open_resume(self, argument: str) -> None:
        """/resume：带编号直接恢复，否则弹出历史会话面板。"""
        session = self._require_session()
        if session is None:
            return
        if self._turn_busy:
            self._chat.add_system(BUSY_TURN, kind="warn")
            return
        store = session.sessions
        if store is None or not store.enabled:
            self._chat.add_system(SESSION_LOG_OFF, kind="error")
            return
        if argument:
            self._resume(argument)
            return
        self._commands.close()
        self.push_screen(
            SessionScreen(store, current=store.session_id), self._after_resume
        )

    def _after_resume(self, session_id: str | None) -> None:
        if not session_id:
            self._prompt.focus()
            return
        self._resume(session_id)

    def _resume(self, session_id: str) -> None:
        session = self._require_session()
        if session is None:
            return
        try:
            count = session.restore(session_id)
        except (AgentError, OSError) as exc:
            self._chat.add_system(
                SESSION_RESTORE_FAILED % _error_text(exc), kind="error"
            )
            return
        self._render_history()
        self._chat.add_system(SESSION_RESTORED % (session_id, count))
        self._refresh_context()
        self._prompt.focus()

    def _render_history(self) -> None:
        """把内存里的历史重新画到聊天区（恢复会话后使用）。"""
        self._chat.clear_messages()
        session = self._session
        if session is None:
            return
        for message in session.history:
            role = str(message.get("role", ""))
            content = str(message.get("content") or "")
            if not content:
                continue
            if role == "user":
                self._chat.add_user(content)
            elif role == "assistant":
                self._chat.set_stream(content)
                self._chat.finish_assistant()

    def _show_sessions(self) -> None:
        """/sessions：列出历史会话（不打开面板，方便一次看全）。"""
        session = self._require_session()
        if session is None:
            return
        store = session.sessions
        if store is None or not store.enabled:
            self._chat.add_system(SESSION_LOG_OFF, kind="error")
            return
        try:
            items = store.list()
        except OSError as exc:
            self._chat.add_system(SESSION_SAVE_FAILED % exc, kind="error")
            return
        if not items:
            self._chat.add_system(SESSION_LIST_EMPTY + "\n" + SESSION_RESUME_HINT)
            return
        lines = [SESSION_LIST_HEADER % (len(items), store.directory)]
        current = store.session_id
        for info in items:
            lines.append(
                SESSION_LIST_ROW
                % (
                    "▶" if info.id == current else " ",
                    info.id,
                    info.message_count,
                    info.title,
                    info.updated_at,
                )
            )
        self._chat.add_system("\n".join(lines))
        self._chat.add_system(SESSION_RESUME_HINT)

    def _export_session(self, argument: str) -> None:
        """/export [目录]：把当前会话导出成 Markdown。"""
        session = self._require_session()
        if session is None:
            return
        store = session.sessions
        if store is None or store.session_id is None:
            self._chat.add_system(SESSION_SAVE_NONE, kind="warn")
            return
        target = Path(argument).expanduser() if argument else Path.cwd()
        try:
            path = store.export_markdown(store.session_id, target)
        except (AgentError, OSError) as exc:
            self._chat.add_system(
                SESSION_EXPORT_FAILED % _error_text(exc), kind="error"
            )
            return
        self._chat.add_system(SESSION_EXPORT_OK % path)

    def _show_status(self) -> None:
        """/status：把模型、工作区、会话、上下文与 MCP 的状态一次列全。"""
        session = self._require_session()
        if session is None:
            return
        config = session.config
        root = str(session.project_root or self._workspace_root)
        try:
            project = session.load_project_prompt()
        except (AgentError, OSError):
            project = session.project_prompt
        store = session.sessions
        hub = session.mcp
        if hub is None or not hub.config.configured:
            mcp_text = STATUS_DISABLED
        elif hub.loading:
            mcp_text = STATUS_LOADING
        else:
            rows = hub.status()
            connected = [row for row in rows if row.connected]
            mcp_text = "%d/%d 个服务，%d 个工具" % (
                len(connected),
                len(rows),
                sum(row.tool_count for row in connected),
            )
        lines = [
            STATUS_HEADER,
            STATUS_ROW % ("模型", config.model_name),
            STATUS_ROW % ("接口", config.base_url),
            STATUS_ROW % ("工作区", root),
            STATUS_ROW % ("会话编号", session.session_id or STATUS_NONE),
            STATUS_ROW
            % (
                "会话日志",
                STATUS_ENABLED if store is not None and store.enabled else STATUS_DISABLED,
            ),
            STATUS_ROW % ("上下文", _context_text(session.context_usage())[0]),
            STATUS_ROW
            % ("压缩", STATUS_BLOCKED if session.compact_required else STATUS_OK),
            STATUS_ROW % ("MCP", mcp_text),
            STATUS_ROW
            % (
                "项目约定",
                AGENTS_MD_LOADED % (config.agents_md, len(project))
                if project
                else AGENTS_MD_NONE % root,
            ),
        ]
        self._chat.add_system("\n".join(lines))

    def _show_tools(self) -> None:
        """/tools：列出注册表里的全部工具（含 MCP 工具）。"""
        session = self._require_session()
        if session is None:
            return
        registry = session.registry
        names = registry.names()
        lines = [TOOLS_HEADER % len(names)]
        for name in names:
            spec = registry.get(name)
            lines.append(TOOLS_ROW % (name, _one_line(spec.description, 90) if spec else ""))
        self._chat.add_system("\n".join(lines))

    # ------------------------------------------------------------ 上下文占用


    def _refresh_context(self) -> None:
        """刷新输入框上方的占用条：已用 / 窗口 / 百分比，超阈值时变色。"""
        widget = getattr(self, "_context_bar", None)
        if widget is None:
            return
        session = self._session
        if session is None:
            widget.update(CONTEXT_BAR_EMPTY)
            widget.set_classes("")
            return
        text, kind = _context_text(session.context_usage())
        widget.update(text)
        widget.set_classes(kind)

    # ------------------------------------------------------------ 上下文压缩

    def _start_compact(self) -> None:
        """`/compact`：归档原始上下文并让模型生成摘要，替换历史。"""
        if self._session is None:
            self._chat.add_system(COMPACT_NEED_SESSION, kind="error")
            self._open_config()
            return
        if self._turn_busy or self._compacting:
            self._chat.add_system(COMPACT_BUSY, kind="warn")
            return
        self._compacting = True
        self._turn_busy = True
        self._cancelling = False
        self._stream_parts = []
        self._current_tool = None
        self._chat.add_system(COMPACT_STARTED)
        self._status.update(COMPACT_RUNNING)
        self._commands.close()
        self._prompt.read_only = True
        self._worker = self._run_compact()

    @work(thread=True, exclusive=True, group="turn", exit_on_error=False)
    def _run_compact(self) -> None:
        session = self._session
        if session is None:
            return
        for event in session.compact():
            self.call_from_thread(self._handle_event, event)

    def _start_turn(self, question: str) -> None:
        if self._turn_busy:
            return
        if self._session is None:
            self._chat.add_system(NEED_CONFIG, kind="error")
            self._open_config()
            return

        self._turn_busy = True
        self._cancelling = False
        self._cancel.reset()
        self._stream_parts = []
        self._tool_calls = 0
        self._current_tool = None
        self._turn_started = time.monotonic()
        self._chat.add_user(question)
        self._status.update(THINKING)
        self._commands.close()
        self._prompt.read_only = True
        # 每秒刷新一次状态栏：等待时间和工具次数让用户知道程序没卡死
        self._status_timer = self.set_interval(1.0, self._tick_status)
        self._worker = self._run_turn(question)

    # ---------------------------------------------------------------- 后台

    @work(thread=True, exclusive=True, group="turn", exit_on_error=False)
    def _run_turn(self, question: str) -> None:
        session = self._session
        if session is None:
            return
        for event in session.ask(question, self._cancel):
            self.call_from_thread(self._handle_event, event)

    def _handle_event(self, event: AgentEvent) -> None:
        if isinstance(event, TextDelta):
            self._stream_parts.append(event.text)
            self._schedule_flush()
        elif isinstance(event, ToolCallStarted):
            self._flush()
            self._chat.finish_assistant()
            self._tool_calls += 1
            self._current_tool = event.name
            self._tool_starts.setdefault(event.name, []).append(time.monotonic())
            self._status.update(
                STATUS_TOOL_RUNNING % (event.name, 0, self._tool_calls)
            )
        elif isinstance(event, ToolCallFinished):
            starts = self._tool_starts.get(event.name) or []
            elapsed = 0.0
            if starts:
                elapsed = time.monotonic() - starts.pop(0)
            self._chat.add_tool(
                event.name,
                event.arguments,
                event.output,
                event.ok,
                int(round(elapsed * 1000)),
            )
            self._current_tool = None
            self._status.update(THINKING)
        elif isinstance(event, TurnCompleted):
            self._flush()
            self._chat.finish_assistant()
            self._finish_turn()
        elif isinstance(event, TurnFailed):
            self._flush()
            self._chat.finish_assistant()
            self._chat.add_system(describe_error(event.error), kind="error")
            self._finish_turn()
        elif isinstance(event, TurnCancelled):
            self._flush()
            self._chat.finish_assistant()
            self._chat.add_system(CANCELLED, kind="warn")
            self._finish_turn()
        elif isinstance(event, ContextWarning):
            self._chat.add_system(
                CONTEXT_WARNING % (event.used, event.window, event.ratio * 100),
                kind="warn",
            )
            self._refresh_context()
        elif isinstance(event, CompactionStarted):
            self._status.update(COMPACT_RUNNING)
        elif isinstance(event, CompactionArchived):
            self._chat.add_system(
                COMPACT_ARCHIVED
                % (event.path, event.message_count, event.bytes / 1024.0)
            )
        elif isinstance(event, CompactionCompleted):
            self._chat.add_system(
                COMPACT_DONE % (event.usage_tokens, event.archive_id)
            )
            self._finish_turn()
        elif isinstance(event, CompactionFailed):
            self._chat.add_system(describe_error(event.error), kind="error")
            self._chat.add_system(COMPACT_FAILED_HINT, kind="warn")
            self._finish_turn()

    # ---------------------------------------------------------------- 流式

    def _schedule_flush(self) -> None:
        if self._flush_timer is None:
            self._flush_timer = self.set_timer(_FLUSH_INTERVAL, self._flush)

    def _flush(self) -> None:
        self._flush_timer = None
        if self._stream_parts:
            self._chat.set_stream("".join(self._stream_parts))

    def _tick_status(self) -> None:
        """每秒刷新状态栏，展示已等待的秒数与工具次数。"""
        if not self._turn_busy or self._cancelling:
            return
        elapsed = int(time.monotonic() - self._turn_started)
        if self._current_tool is not None:
            self._status.update(
                STATUS_TOOL_RUNNING
                % (self._current_tool, elapsed, self._tool_calls)
            )
        else:
            self._status.update(
                STATUS_THINKING_ELAPSED % (elapsed, self._tool_calls)
            )

    def _finish_turn(self) -> None:
        if self._flush_timer is not None:
            self._flush_timer.stop()
            self._flush_timer = None
        if self._status_timer is not None:
            self._status_timer.stop()
            self._status_timer = None
        self._stream_parts = []
        self._turn_busy = False
        self._compacting = False
        self._cancelling = False
        self._current_tool = None
        self._prompt.read_only = False
        self._status.update(READY)
        self._refresh_context()
        self._prompt.focus()

    # ---------------------------------------------------------------- 动作

    def action_interrupt(self) -> None:
        if self._turn_busy:
            self._cancel.cancel()
            self._cancelling = True
            self._status.update(CANCELLING)
        else:
            self.exit()

    def action_quit_app(self) -> None:
        self.exit()

    def action_clear_screen(self) -> None:
        self._chat.clear_messages()

    def on_unmount(self) -> None:
        # 退出时先停掉 MCP 轮询，再回收子进程与 HTTP 连接；可重复调用
        self._stop_mcp_timer()
        if self._session is not None:
            self._session.close()