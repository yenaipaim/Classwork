"""构造发给模型的消息列表。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .config import AppConfig


def system_content(config: AppConfig, extra_system: str = "") -> str:
    """System Prompt 正文；`extra_system` 非空时追加在末尾（如技能清单）。"""
    content = config.system_prompt
    if extra_system and extra_system.strip():
        content = content.rstrip() + "\n\n" + extra_system.strip()
    return content


def recent_messages(
    history: Sequence[Mapping[str, Any]],
    config: AppConfig,
    extra_system: str = "",
) -> list[dict[str, Any]]:
    """真正会发给模型的那部分上下文：System Prompt + 最近 N 轮历史。

    裁剪规则只写在这一处：``build_messages`` 拼请求、``context_usage`` 统计
    占用都调它，这样「占用条算的」与「实际发出去的」是同一批消息，不会
    出现两个口径来回跳。

    历史里只有 user / assistant 文本，工具调用与结果只存在于当轮请求中，
    下一轮不再发送，所以它们的占用不应计入常驻上下文。
    """
    keep = max(config.history_turns, 0) * 2
    recent = [dict(item) for item in (history[-keep:] if keep else ())]
    # 裁剪后可能以 assistant 开头，一直丢到第一个 user，避免孤立回答
    while recent and recent[0].get("role") != "user":
        recent.pop(0)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_content(config, extra_system)}
    ]
    messages.extend(recent)
    return messages


def build_messages(
    history: Sequence[Mapping[str, Any]],
    question: str,
    config: AppConfig,
    extra_system: str = "",
) -> list[dict[str, Any]]:
    """system + 最近 N 轮历史 + 当前问题（裁剪规则见 :func:`recent_messages`）。"""
    messages = recent_messages(history, config, extra_system)
    messages.append({"role": "user", "content": question})
    return messages