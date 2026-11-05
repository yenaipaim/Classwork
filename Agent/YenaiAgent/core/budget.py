"""上下文长度：Token 估算与窗口大小解析。

估算只求“量级正确”：中文按 1.6 字 ≈ 1 token、其余按 3.5 字符 ≈ 1 token 计，
再给每条消息加上角色与分隔符的固定开销。密度取自实测 tokenizer 的经验区间
（中文 1.5~1.7 字 / token，英文与代码 3.5~4 字符 / token）——早先按「1 字 1
token」会把中文上下文高估约 1.5 倍，占用条因此虚高。模型接口返回真实 usage
时以真实值为准（见 :attr:`ContextUsage.estimated`）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .config import AppConfig
from .constants import DEFAULT_CONTEXT_WINDOW

#: 已知模型的上下文窗口（token）：仅在 config.ini 没写 `[llm] context_window`
#: 时参考。按小写子串匹配、先命中先用；都命中不了就按 128k 处理并标记「默认」。
KNOWN_CONTEXT_WINDOWS: tuple[tuple[str, int], ...] = (
    ("gpt-4.1", 1_047_576),
    ("gpt-4o", 128_000),
    ("gpt-4-turbo", 128_000),
    ("gpt-3.5", 16_385),
    ("deepseek", 128_000),
    ("claude", 200_000),
    ("gemini", 1_048_576),
    ("qwen", 131_072),
    ("glm", 128_000),
    ("kimi", 262_144),
    ("moonshot", 128_000),
)

#: 估算密度：中文约 1.6 字 / token，英文与代码约 3.5 字符 / token
CJK_CHARS_PER_TOKEN = 1.6
OTHER_CHARS_PER_TOKEN = 3.5

#: 每条消息的固定开销：role、分隔符与 chat 模板本身
MESSAGE_OVERHEAD = 4


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x2E80 <= code <= 0x9FFF      # 中日韩部首、假名、汉字
        or 0xAC00 <= code <= 0xD7AF   # 韩文音节
        or 0xF900 <= code <= 0xFAFF   # 兼容汉字
        or 0xFF00 <= code <= 0xFFEF   # 全角符号
    )


def estimate_tokens(text: str) -> int:
    """粗略估算一段文本的 token 数：中文 1.6 字 ≈ 1 token，其余 3.5 字符 ≈ 1 token。"""
    if not text:
        return 0
    cjk = sum(1 for char in text if _is_cjk(char))
    other = len(text) - cjk
    return int(cjk / CJK_CHARS_PER_TOKEN + other / OTHER_CHARS_PER_TOKEN + 0.5)


def _dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def estimate_message(message: Mapping[str, Any]) -> int:
    """估算一条消息：正文 + 工具调用参数 + 角色开销。"""
    total = MESSAGE_OVERHEAD
    content = message.get("content")
    if isinstance(content, str):
        total += estimate_tokens(content)
    elif content:
        total += estimate_tokens(_dumps(content))
    calls = message.get("tool_calls")
    if calls:
        total += estimate_tokens(_dumps(calls))
    for key in ("name", "tool_call_id"):
        value = message.get(key)
        if isinstance(value, str):
            total += estimate_tokens(value)
    return total


def estimate_messages(messages: Sequence[Mapping[str, Any]]) -> int:
    return sum(estimate_message(message) for message in messages)


def estimate_tools(schemas: Sequence[Mapping[str, Any]]) -> int:
    """工具定义也占窗口：按 JSON schema 的字符量估。"""
    if not schemas:
        return 0
    return estimate_tokens(_dumps(list(schemas)))


def resolve_window(config: AppConfig) -> tuple[int, bool]:
    """返回（窗口大小，是否为默认值）。

    优先级：`[llm] context_window` > 已知模型表 > 128k 默认值。
    """
    configured = int(getattr(config, "context_window", 0) or 0)
    if configured > 0:
        return configured, False
    name = (getattr(config, "model_name", "") or "").lower()
    for marker, size in KNOWN_CONTEXT_WINDOWS:
        if marker in name:
            return size, False
    # 探测不到就用配置里的 default_window（模板默认 128k），并标记「默认」
    fallback = int(getattr(config, "default_context_window", 0) or 0)
    if fallback > 0:
        return fallback, True
    return DEFAULT_CONTEXT_WINDOW, True


@dataclass(frozen=True, slots=True)
class ContextUsage:
    """一次上下文占用快照。"""

    used: int
    window: int
    ratio: float
    window_is_default: bool
    estimated: bool

    @property
    def percent(self) -> float:
        return self.ratio * 100.0


def measure(
    config: AppConfig,
    messages: Sequence[Mapping[str, Any]],
    tool_schemas: Sequence[Mapping[str, Any]] = (),
    api_tokens: int | None = None,
) -> ContextUsage:
    """优先用接口返回的 usage，拿不到就本地估算 messages + 工具 schema。"""
    window, is_default = resolve_window(config)
    if api_tokens is not None and api_tokens > 0:
        used, estimated = int(api_tokens), False
    else:
        used = estimate_messages(messages) + estimate_tools(tool_schemas)
        estimated = True
    used = max(used, 0)
    ratio = (used / window) if window > 0 else 0.0
    return ContextUsage(
        used=used,
        window=window,
        ratio=ratio,
        window_is_default=is_default,
        estimated=estimated,
    )
