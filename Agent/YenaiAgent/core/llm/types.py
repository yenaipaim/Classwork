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
    """流式响应的一个分片：正文和/或工具调用分片。"""

    content: str | None = None
    tool_calls: tuple[ToolCallDelta, ...] = ()