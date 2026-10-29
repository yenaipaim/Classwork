"""LLM 后端抽象与 OpenAI 兼容实现。

界面层只依赖 :class:`LlmBackend` 协议，测试用假后端替换即可，无需网络。
"""

from __future__ import annotations

from typing import Iterator, Protocol

from openai import OpenAI

from ..errors import ConfigError, ErrorCode, LlmRequestError
from .types import LlmChunk, LlmRequest, ToolCallDelta


class LlmBackend(Protocol):
    """流式对话后端。"""

    def stream(self, request: LlmRequest) -> Iterator[LlmChunk]:
        ...


class OpenAIBackend:
    """基于 openai SDK 的 Chat Completions 实现。"""

    def __init__(self, base_url: str, api_key: str, timeout: float = 60.0) -> None:
        try:
            self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        except Exception as exc:  # SDK 在参数非法时会抛各种子类
            raise ConfigError(
                ErrorCode.CONFIG_INVALID, "无法创建模型客户端：%s" % exc
            ) from exc

    def stream(self, request: LlmRequest) -> Iterator[LlmChunk]:
        try:
            stream = self._client.chat.completions.create(
                model=request.model,
                messages=list(request.messages),
                max_tokens=request.max_tokens,
                stream=True,
                tools=list(request.tools),
            )
            for chunk in stream:
                yield _to_chunk(chunk)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            raise LlmRequestError(ErrorCode.REQUEST_FAILED, str(exc)) from exc


def _to_chunk(chunk) -> LlmChunk:
    """把 SDK 的 chunk 归一化成 :class:`LlmChunk`。"""
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return LlmChunk()

    delta = getattr(choices[0], "delta", None)
    if delta is None:
        return LlmChunk()

    calls: list[ToolCallDelta] = []
    for call in getattr(delta, "tool_calls", None) or []:
        function = getattr(call, "function", None)
        calls.append(
            ToolCallDelta(
                index=int(getattr(call, "index", 0) or 0),
                id=getattr(call, "id", None),
                name=getattr(function, "name", None) if function is not None else None,
                arguments=(
                    getattr(function, "arguments", None)
                    if function is not None
                    else None
                ),
            )
        )
    return LlmChunk(
        content=getattr(delta, "content", None),
        tool_calls=tuple(calls),
        finish_reason=_finish_reason(chunk),
    )


def _finish_reason(chunk: Any) -> str | None:
    """读取结束原因；不同兼容接口字段位置可能不同，缺失时返回 None。"""
    choices = getattr(chunk, "choices", None) or ()
    if not choices:
        return None
    return getattr(choices[0], "finish_reason", None)