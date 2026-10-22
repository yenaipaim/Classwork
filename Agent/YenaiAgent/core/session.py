"""一轮问答的编排：上下文裁剪、流式调用、工具循环、提交历史。

会话层只产出事件，不打印、不读输入，也不关心界面是什么样子。
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Iterator

from .config import AppConfig
from .context import build_messages
from .errors import AgentError, ErrorCode, LlmRequestError
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
    ) -> None:
        self._backend = backend
        self._registry = registry
        self._config = config
        self._transcript = transcript
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

            if not collector.has_tool_calls:
                break

            if rounds >= self._config.max_tool_rounds:
                yield TurnFailed(
                    AgentError(
                        ErrorCode.TOOL_ROUND_LIMIT,
                        "工具调用超过 %d 次，已中止" % self._config.max_tool_rounds,
                    ),
                    "".join(parts),
                )
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
        self._history.append({"role": "user", "content": question})
        self._history.append({"role": "assistant", "content": text})
        if self._transcript is not None:
            self._transcript.save_turn(question, text, records)
        yield TurnCompleted(text, tuple(records))