"""core 向界面层输出的事件。

界面层只消费这些事件，因此 core 不需要知道自己被谁驱动：
TUI 打印成文本，Web 可以转成 SSE，Desktop 可以转成信号。
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import AgentError


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    """一次工具执行的记录，用于写历史存档。"""

    name: str
    arguments: str
    output: str
    ok: bool
    started_at: str


@dataclass(frozen=True, slots=True)
class TurnStarted:
    question: str


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class ToolCallStarted:
    name: str
    arguments: str
    call_id: str


@dataclass(frozen=True, slots=True)
class ToolCallFinished:
    name: str
    arguments: str
    output: str
    ok: bool


@dataclass(frozen=True, slots=True)
class TurnCompleted:
    text: str
    tool_calls: tuple[ToolCallRecord, ...] = ()


@dataclass(frozen=True, slots=True)
class TurnFailed:
    error: AgentError
    partial_text: str = ""


@dataclass(frozen=True, slots=True)
class TurnCancelled:
    partial_text: str = ""


AgentEvent = (
    TurnStarted
    | TextDelta
    | ToolCallStarted
    | ToolCallFinished
    | TurnCompleted
    | TurnFailed
    | TurnCancelled
)