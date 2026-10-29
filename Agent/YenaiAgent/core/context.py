"""构造发给模型的消息列表。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .config import AppConfig


def build_messages(
    history: Sequence[Mapping[str, Any]],
    question: str,
    config: AppConfig,
    extra_system: str = "",
) -> list[dict[str, Any]]:
    """system + 最近 N 轮历史 + 当前问题。

    历史按「问 + 答」成对追加，但裁剪后可能以 assistant 开头，
    这时要一直丢到第一个 user，避免出现孤立的 assistant。

    ``extra_system`` 追加在 system 内容末尾（如技能清单），空串时不变。
    """
    keep = max(config.history_turns, 0) * 2
    recent = [dict(item) for item in (history[-keep:] if keep else ())]
    while recent and recent[0].get("role") != "user":
        recent.pop(0)

    system_content = config.system_prompt
    if extra_system and extra_system.strip():
        system_content = system_content.rstrip() + "\n\n" + extra_system.strip()

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_content}
    ]
    messages.extend(recent)
    messages.append({"role": "user", "content": question})
    return messages