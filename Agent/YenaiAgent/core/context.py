"""构造发给模型的消息列表。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .config import AppConfig


def build_messages(
    history: Sequence[Mapping[str, Any]],
    question: str,
    config: AppConfig,
) -> list[dict[str, Any]]:
    """system + 最近 N 轮历史 + 当前问题。

    历史按「问 + 答」成对追加，但裁剪后可能以 assistant 开头，
    这时要一直丢到第一个 user，避免出现孤立的 assistant。
    """
    keep = max(config.history_turns, 0) * 2
    recent = [dict(item) for item in (history[-keep:] if keep else ())]
    while recent and recent[0].get("role") != "user":
        recent.pop(0)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": config.system_prompt}
    ]
    messages.extend(recent)
    messages.append({"role": "user", "content": question})
    return messages