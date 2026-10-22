"""上下文裁剪测试。"""

from __future__ import annotations

from core.config import AppConfig
from core.constants import HISTORY_TURNS, SYSTEM_PROMPT
from core.context import build_messages


def make_config(**overrides) -> AppConfig:
    values = dict(base_url="http://x", api_key="k", model_name="m")
    values.update(overrides)
    return AppConfig(**values)


def test_only_recent_ten_turns_are_kept() -> None:
    config = make_config()
    history = []
    for index in range(HISTORY_TURNS + 5):
        history.append({"role": "user", "content": "q%d" % index})
        history.append({"role": "assistant", "content": "a%d" % index})

    messages = build_messages(history, "next", config)

    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert len(messages) == 1 + HISTORY_TURNS * 2 + 1
    assert messages[1] == {"role": "user", "content": "q5"}
    assert messages[-1] == {"role": "user", "content": "next"}


def test_leading_assistant_is_dropped() -> None:
    config = make_config(history_turns=2)
    history = [
        {"role": "assistant", "content": "orphan"},
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
    ]

    messages = build_messages(history, "q2", config)

    assert messages[1] == {"role": "user", "content": "q1"}
    assert messages[-1] == {"role": "user", "content": "q2"}


def test_zero_history_keeps_only_system_and_question() -> None:
    config = make_config(history_turns=0)
    history = [{"role": "user", "content": "old"}]

    messages = build_messages(history, "new", config)

    assert messages == [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "new"},
    ]


def test_history_is_not_mutated() -> None:
    config = make_config()
    history = [
        {"role": "assistant", "content": "orphan"},
        {"role": "user", "content": "q"},
    ]
    snapshot = list(history)
    build_messages(history, "next", config)
    assert history == snapshot