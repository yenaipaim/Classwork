"""Textual 应用：只处理输入、展示与命令，业务全部交给 core。

线程模型：``ask()`` 是阻塞的生成器，放在后台 worker 线程里跑；
每个事件通过 ``call_from_thread`` 回到 UI 线程处理，界面因而不会被网络卡住。
"""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.timer import Timer
from textual.widgets import Footer, Header, Static

from core.config import AppConfig, ConfigStore
from core.errors import ConfigError
from core.events import (
    AgentEvent,
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
    CONFIG_SAVED,
    CONTEXT_CLEARED,
    HELP_TEXT,
    INPUT_PLACEHOLDER,
    MODEL_SWITCHED,
    MODEL_USAGE,
    NEED_CONFIG,
    READY,
    THINKING,
    TOOL_RUNNING,
    UNKNOWN_COMMAND,
    WELCOME,
    describe_error,
)
from .screens.config_screen import ConfigScreen
from .widgets.chat_input import ChatInput
from .widgets.chat_log import ChatLog

_FLUSH_INTERVAL = 0.05


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
    ) -> None:
        super().__init__()
        self._store = store or ConfigStore(config_path or DEFAULT_CONFIG_PATH)
        self._history_dir = Path(history_dir or DEFAULT_HISTORY_DIR)
        self._workspace_root = Path(workspace_root or DEFAULT_WORKSPACE_ROOT)
        self._backend = backend
        self._session = session

        self._cancel = CancelToken()
        self._worker = None
        self._turn_busy = False
        self._stream_parts: list[str] = []
        self._flush_timer: Timer | None = None
        self._tool_starts: dict[str, list[float]] = {}

    # ---------------------------------------------------------------- 布局

    def compose(self) -> ComposeResult:
        yield Header()
        yield ChatLog(id="chat")
        yield Static(READY, id="status")
        yield ChatInput(placeholder=INPUT_PLACEHOLDER, id="prompt")
        yield Footer()

    def on_mount(self) -> None:
        self._chat = self.query_one("#chat", ChatLog)
        self._status = self.query_one("#status", Static)
        self._prompt = self.query_one("#prompt", ChatInput)
        self._chat.add_system(WELCOME)
        self._prompt.focus()

        if self._session is not None:
            return
        try:
            config = self._store.load()
        except ConfigError:
            self._open_config()
        else:
            self._install_config(config)

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
        self._session = create_session(
            config,
            workspace_root=self._workspace_root,
            history_dir=self._history_dir,
            backend=self._backend,
        )
        self._status.update(READY)

    # ---------------------------------------------------------------- 输入

    def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        self._prompt.reset()
        value = event.text.strip()
        if not value or self._turn_busy:
            return
        if value.startswith("/"):
            self._run_command(value)
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
        elif command == "/config":
            self._open_config()
        elif command == "/model":
            self._switch_model(argument)
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

    def _start_turn(self, question: str) -> None:
        if self._turn_busy:
            return
        if self._session is None:
            self._chat.add_system(NEED_CONFIG, kind="error")
            self._open_config()
            return

        self._turn_busy = True
        self._cancel.reset()
        self._stream_parts = []
        self._chat.add_user(question)
        self._status.update(THINKING)
        self._prompt.read_only = True
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
            self._tool_starts.setdefault(event.name, []).append(time.monotonic())
            self._status.update("%s：%s" % (TOOL_RUNNING, event.name))
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

    # ---------------------------------------------------------------- 流式

    def _schedule_flush(self) -> None:
        if self._flush_timer is None:
            self._flush_timer = self.set_timer(_FLUSH_INTERVAL, self._flush)

    def _flush(self) -> None:
        self._flush_timer = None
        if self._stream_parts:
            self._chat.set_stream("".join(self._stream_parts))

    def _finish_turn(self) -> None:
        if self._flush_timer is not None:
            self._flush_timer.stop()
            self._flush_timer = None
        self._stream_parts = []
        self._turn_busy = False
        self._prompt.read_only = False
        self._status.update(READY)
        self._prompt.focus()

    # ---------------------------------------------------------------- 动作

    def action_interrupt(self) -> None:
        if self._turn_busy:
            self._cancel.cancel()
            self._status.update(CANCELLING)
        else:
            self.exit()

    def action_quit_app(self) -> None:
        self.exit()

    def action_clear_screen(self) -> None:
        self._chat.clear_messages()