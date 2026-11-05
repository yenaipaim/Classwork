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


@dataclass(frozen=True, slots=True)
class ContextWarning:
    """上下文占用达到阈值：提示用户执行 /compact，并暂停普通输入。

    只带数字与布尔值，界面层自己决定文案（core 不产出用户提示）。
    """

    used: int
    window: int
    ratio: float
    window_is_default: bool
    threshold: float


@dataclass(frozen=True, slots=True)
class CompactionStarted:
    """开始压缩：先把待归档的消息数与当前占用报给界面。"""

    message_count: int
    usage_tokens: int


@dataclass(frozen=True, slots=True)
class CompactionArchived:
    """原始上下文已落盘；编号即文件名。"""

    archive_id: str
    path: str
    message_count: int
    bytes: int


@dataclass(frozen=True, slots=True)
class CompactionCompleted:
    """压缩成功：历史已被摘要替换。"""

    archive_id: str
    created_at: str
    summary: str
    usage_tokens: int
    window: int


@dataclass(frozen=True, slots=True)
class CompactionFailed:
    """压缩失败：原上下文保持不变，可以重试。"""

    error: AgentError


AgentEvent = (
    TurnStarted
    | TextDelta
    | ToolCallStarted
    | ToolCallFinished
    | TurnCompleted
    | TurnFailed
    | TurnCancelled
    | ContextWarning
    | CompactionStarted
    | CompactionArchived
    | CompactionCompleted
    | CompactionFailed
)