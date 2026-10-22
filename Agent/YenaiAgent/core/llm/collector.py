"""把流式分片拼成一次完整回复。

OpenAI 兼容接口把工具调用拆成多个 chunk（id/name 在前，arguments 逐段拼），
这里按 index 归并，供会话层做决定。
"""

from __future__ import annotations

from dataclasses import dataclass

from .types import LlmChunk


@dataclass(frozen=True, slots=True)
class ToolCallInvocation:
    """模型要求执行的一次工具调用。"""

    name: str
    arguments: str
    call_id: str


@dataclass
class _PendingCall:
    call_id: str = ""
    name: str = ""
    arguments: str = ""


class TurnCollector:
    """收集一次流式回复的正文与工具调用。"""

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._calls: dict[int, _PendingCall] = {}

    @property
    def text(self) -> str:
        return "".join(self._parts)

    def add_chunk(self, chunk: LlmChunk) -> None:
        if chunk.content:
            self._parts.append(chunk.content)
        for delta in chunk.tool_calls:
            pending = self._calls.setdefault(delta.index, _PendingCall())
            if delta.id:
                pending.call_id = delta.id
            if delta.name:
                pending.name += delta.name
            if delta.arguments:
                pending.arguments += delta.arguments

    @property
    def has_tool_calls(self) -> bool:
        return bool(self._calls)

    def tool_calls(self) -> list[ToolCallInvocation]:
        calls: list[ToolCallInvocation] = []
        for position in range(len(self._calls)):
            pending = self._calls[position]
            calls.append(
                ToolCallInvocation(
                    name=pending.name,
                    arguments=pending.arguments or "{}",
                    call_id=pending.call_id or "call_%d" % position,
                )
            )
        return calls