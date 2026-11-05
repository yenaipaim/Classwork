"""LLM 后端抽象与 OpenAI 兼容实现。

界面层只依赖 :class:`LlmBackend` 协议，测试用假后端替换即可，无需网络。
"""

from __future__ import annotations

from typing import Any, Iterator, Protocol

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
        """按需开启 usage 上报：拿得到真实 token 用量就不必估算。"""
        try:
            stream = self._open(request, with_usage=True)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            # 少数兼容接口不认 stream_options：去掉再试一次，不影响正常对话
            if "stream_options" not in str(exc).lower():
                raise LlmRequestError(ErrorCode.REQUEST_FAILED, str(exc)) from exc
            try:
                stream = self._open(request, with_usage=False)
            except Exception as fallback:
                raise LlmRequestError(
                    ErrorCode.REQUEST_FAILED, str(fallback)
                ) from fallback
        try:
            for chunk in stream:
                yield _to_chunk(chunk)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            raise LlmRequestError(ErrorCode.REQUEST_FAILED, str(exc)) from exc

    def _open(self, request: LlmRequest, with_usage: bool):
        params: dict[str, Any] = {
            "model": request.model,
            "messages": list(request.messages),
            "max_tokens": request.max_tokens,
            "stream": True,
        }
        # 压缩请求不带任何工具；空列表会让部分接口报 400，所以干脆不传这个字段
        if request.tools:
            params["tools"] = list(request.tools)
        if with_usage:
            params["stream_options"] = {"include_usage": True}
        return self._client.chat.completions.create(**params)


def _to_chunk(chunk) -> LlmChunk:
    """把 SDK 的 chunk 归一化成 :class:`LlmChunk`。"""
    usage = _usage_tokens(chunk)
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        # 开了 include_usage 后，末尾会多一个只带 usage、choices 为空的分片
        return LlmChunk(usage_tokens=usage)

    delta = getattr(choices[0], "delta", None)
    if delta is None:
        return LlmChunk(usage_tokens=usage)

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
        usage_tokens=usage,
    )


def _usage_tokens(chunk) -> int | None:
    """读取本次请求的 prompt token 数；字段缺失或为 0 时返回 None。"""
    usage = getattr(chunk, "usage", None)
    if usage is None:
        return None
    for name in ("prompt_tokens", "input_tokens", "total_tokens"):
        value = getattr(usage, name, None)
        if isinstance(value, int) and value > 0:
            return value
    return None


def _finish_reason(chunk: Any) -> str | None:
    """读取结束原因；不同兼容接口字段位置可能不同，缺失时返回 None。"""
    choices = getattr(chunk, "choices", None) or ()
    if not choices:
        return None
    return getattr(choices[0], "finish_reason", None)
