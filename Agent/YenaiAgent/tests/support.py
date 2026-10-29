"""测试共用工具：脚本化假后端与构造分片的函数。"""

from __future__ import annotations

from typing import Iterable, Sequence

from core.llm.types import LlmChunk, ToolCallDelta


class FakeBackend:
    """按脚本逐轮回放 chunk，不访问网络。"""

    def __init__(self, scripts: Iterable[Sequence[LlmChunk]] | None = None) -> None:
        self.scripts: list[Sequence[LlmChunk]] = [list(s) for s in (scripts or [])]
        self.requests = []

    def stream(self, request):
        self.requests.append(request)
        if not self.scripts:
            return iter(())
        chunks = self.scripts.pop(0)

        def generate():
            for chunk in chunks:
                yield chunk

        return generate()


class RaisingBackend:
    """第一次请求就抛指定异常。"""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.requests = []

    def stream(self, request):
        self.requests.append(request)
        raise self.error


def text_chunks(*parts: str) -> list[LlmChunk]:
    return [LlmChunk(content=part) for part in parts]


def tool_script(call_id: str, name: str, arguments: str) -> list[LlmChunk]:
    """模拟工具调用被拆成三段流式分片。"""
    half = max(len(arguments) // 2, 1)
    return [
        LlmChunk(
            tool_calls=(
                ToolCallDelta(
                    index=0,
                    id=call_id,
                    name=name,
                    arguments=arguments[:half],
                ),
            )
        ),
        LlmChunk(
            tool_calls=(
                ToolCallDelta(index=0, arguments=arguments[half:]),
            )
        ),
    ]