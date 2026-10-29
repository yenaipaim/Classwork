"""一轮问答的编排：上下文裁剪、流式调用、工具循环、提交历史。

会话层只产出事件，不打印、不读输入，也不关心界面是什么样子。
"""

from __future__ import annotations

import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

from .config import AppConfig
from .constants import MAX_REPEATED_TOOL_CALLS
from .context import build_messages
from .errors import AgentError, ConfigError, ErrorCode, LlmRequestError
from .events import (
    AgentEvent,
    TextDelta,
    ToolCallFinished,
    ToolCallRecord,
    ToolCallStarted,
    TurnCancelled,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
)
from .llm.backend import LlmBackend
from .llm.collector import TurnCollector
from .llm.types import LlmRequest
from .tools.spec import ToolRegistry
from .transcript import Transcript


class CancelToken:
    """线程安全的中断标志，由界面层置位。"""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def reset(self) -> None:
        self._event.clear()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


class _Cancelled(Exception):
    """内部信号：中断发生在流式循环里，用异常跳出去。"""


class AgentSession:
    """持有内存上下文与存档，按需执行一次问答。"""

    def __init__(
        self,
        backend: LlmBackend,
        registry: ToolRegistry,
        config: AppConfig,
        transcript: Transcript | None = None,
        registry_factory: Callable[[Path | str], ToolRegistry] | None = None,
    ) -> None:
        self._backend = backend
        self._registry = registry
        self._config = config
        self._transcript = transcript
        # 由装配点注入：换工作区时按新目录重建工具注册表
        self._registry_factory = registry_factory
        self._history: list[dict[str, Any]] = []

    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    @property
    def transcript_path(self):
        return self._transcript.path if self._transcript is not None else None

    def reset(self) -> None:
        """清空上下文，并让后续存档写到新文件。"""
        self._history.clear()
        if self._transcript is not None:
            self._transcript.reset()

    def switch_model(self, config: AppConfig) -> None:
        """切换模型等设置：保留当前上下文，从下一轮开始生效。"""
        self._config = config

    def switch_workspace(self, workspace_root: Path | str) -> Path:
        """切换工作区：文件工具沙箱与 RunCli 工作目录随之改变，上下文保留。

        支持 ``%VAR%`` / ``~`` / 相对路径（按当前进程目录解析）。
        目录不存在或会话未注入注册表工厂时抛 :class:`ConfigError`。
        """
        root = Path(os.path.expandvars(str(workspace_root))).expanduser().resolve()
        if not root.exists():
            raise ConfigError(
                ErrorCode.CONFIG_INVALID, "工作区目录不存在：%s" % workspace_root
            )
        if not root.is_dir():
            raise ConfigError(ErrorCode.CONFIG_INVALID, "工作区不是目录：%s" % root)
        if self._registry_factory is None:
            raise ConfigError(
                ErrorCode.CONFIG_INVALID, "当前会话未启用工作区切换"
            )
        self._registry = self._registry_factory(root)
        return root

    def ask(
        self,
        question: str,
        cancel: CancelToken | None = None,
    ) -> Iterator[AgentEvent]:
        """执行一轮问答，逐事件产出。

        只有完整成功才写入上下文与存档；失败或中断都不留下半截记录。
        """
        yield TurnStarted(question)

        messages = build_messages(self._history, question, self._config)
        parts: list[str] = []
        records: list[ToolCallRecord] = []
        rounds = 0
        # 同一工具 + 同一组参数的连续调用次数，用来发现原地打转
        repeats: dict[tuple[str, str], int] = {}

        while True:
            if cancel is not None and cancel.cancelled:
                yield TurnCancelled("".join(parts))
                return

            collector = TurnCollector()
            try:
                request = LlmRequest(
                    model=self._config.model_name,
                    messages=messages,
                    tools=self._registry.schemas(),
                    max_tokens=self._config.max_tokens,
                    timeout=self._config.request_timeout,
                )
                for chunk in self._backend.stream(request):
                    collector.add_chunk(chunk)
                    if chunk.content:
                        parts.append(chunk.content)
                        yield TextDelta(chunk.content)
                    if cancel is not None and cancel.cancelled:
                        raise _Cancelled()
            except _Cancelled:
                yield TurnCancelled("".join(parts))
                return
            except LlmRequestError as exc:
                yield TurnFailed(exc, "".join(parts))
                return
            except KeyboardInterrupt:
                yield TurnCancelled("".join(parts))
                return
            except AgentError as exc:
                yield TurnFailed(exc, "".join(parts))
                return
            except Exception as exc:  # 兜底，避免界面层拿到裸异常
                yield TurnFailed(
                    AgentError(ErrorCode.UNKNOWN, str(exc)), "".join(parts)
                )
                return

            if not collector.text.strip() and not collector.has_tool_calls:
                # 流结束了却什么都没有：多半是连接被掐断或模型空回复。
                # 静默结束会让界面停在“思考中”，所以明确报错让用户重试。
                yield TurnFailed(
                    AgentError(
                        ErrorCode.UNKNOWN,
                        "模型没有返回任何内容（连接可能中断或模型异常），请重试。",
                    ),
                    "".join(parts),
                )
                return

            if not collector.has_tool_calls:
                break

            if rounds >= self._config.max_tool_rounds:
                # 不再报错中止：保留已经拿到的回答，让用户可以继续追问。
                text = "".join(parts) + _round_limit_note(self._config.max_tool_rounds)
                self._commit(question, text, records)
                yield TurnCompleted(text, tuple(records))
                return
            rounds += 1

            calls = collector.tool_calls()
            messages.append(
                {
                    "role": "assistant",
                    "content": collector.text or None,
                    "tool_calls": [
                        {
                            "id": call.call_id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": call.arguments,
                            },
                        }
                        for call in calls
                    ],
                }
            )

            for call in calls:
                if cancel is not None and cancel.cancelled:
                    yield TurnCancelled("".join(parts))
                    return

                signature = (call.name, call.arguments)
                repeats[signature] = repeats.get(signature, 0) + 1
                if repeats[signature] > MAX_REPEATED_TOOL_CALLS:
                    # 模型在用同样的参数反复调同一个工具，再跑下去只是空转
                    text = "".join(parts) + _repeat_note(call.name)
                    self._commit(question, text, records)
                    yield TurnCompleted(text, tuple(records))
                    return

                yield ToolCallStarted(call.name, call.arguments, call.call_id)
                started_at = datetime.now().strftime("%H:%M:%S")
                outcome = self._registry.execute(call.name, call.arguments)
                records.append(
                    ToolCallRecord(
                        name=call.name,
                        arguments=call.arguments,
                        output=outcome.output,
                        ok=outcome.ok,
                        started_at=started_at,
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.call_id,
                        "content": outcome.output,
                    }
                )
                yield ToolCallFinished(
                    call.name, call.arguments, outcome.output, outcome.ok
                )

        text = "".join(parts)
        if collector.finish_reason == "length":
            # 模型被单次输出上限截断：明确告诉用户，而不是让回答莫名其妙停在半句
            text += _truncated_note(self._config.max_tokens)
        self._commit(question, text, records)
        yield TurnCompleted(text, tuple(records))

    def _commit(
        self,
        question: str,
        text: str,
        records: list[ToolCallRecord],
    ) -> None:
        """把一轮问答写入上下文与存档（失败和中断不走这里）。"""
        self._history.append({"role": "user", "content": question})
        self._history.append({"role": "assistant", "content": text})
        if self._transcript is not None:
            self._transcript.save_turn(question, text, records)


def _round_limit_note(limit: int) -> str:
    return (
        "\n\n（本轮已连续调用工具 %d 轮，达到上限；上面的结果已保留，"
        "可以继续追问，或让我换个方式处理。）" % limit
    )


def _repeat_note(name: str) -> str:
    return (
        "\n\n（工具「%s」被反复以相同参数调用，已停止以免空转；"
        "可以换个说法，或告诉我需要什么信息。）" % name
    )


def _truncated_note(max_tokens: int) -> str:
    return (
        "\n\n（本次回答达到单次输出上限 %d tokens，后面被截断了；"
        "回复“继续”即可接着写，或在 config.ini 里调大 max_tokens。）" % max_tokens
    )