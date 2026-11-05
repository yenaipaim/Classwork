"""LLM 层的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class LlmRequest:
    """一次流式请求的输入。"""

    model: str
    messages: Sequence[Mapping[str, Any]]
    tools: Sequence[Mapping[str, Any]]
    max_tokens: int
    timeout: float


@dataclass(frozen=True, slots=True)
class ToolCallDelta:
    """工具调用的一个流式分片。"""

    index: int
    id: str | None = None
    name: str | None = None
    arguments: str | None = None


@dataclass(frozen=True, slots=True)
class LlmChunk:
    """流式响应的一个分片：正文、工具调用分片、结束原因与 token 用量。

    `usage_tokens` 是本次请求的 prompt token 数（含 System Prompt 与历史）。
    兼容接口不一定给（不给就是 None），会话层据此决定用真实值还是本地估算。
    """

    content: str | None = None
    tool_calls: tuple[ToolCallDelta, ...] = ()
    finish_reason: str | None = None
    usage_tokens: int | None = None