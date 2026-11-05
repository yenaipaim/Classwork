"""第十一次课：上下文压缩、原始归档与 recallContext 检索。

只跑本地文件与假后端，不访问网络。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import replace
from pathlib import Path

import pytest
from textual.widgets import Static

from core.archive import ContextArchive
from core.budget import (
    estimate_message,
    estimate_messages,
    estimate_tokens,
    estimate_tools,
    measure,
    resolve_window,
)
from core.context import recent_messages
from core.llm.types import LlmChunk
from core.compaction import COMPACTION_PROMPT, SUMMARY_ACK
from core.config import ConfigStore
from core.constants import CONTEXT_WARN_RATIO, DEFAULT_CONTEXT_WINDOW
from core.errors import ErrorCode, ToolError
from core.events import (
    CompactionArchived,
    CompactionCompleted,
    CompactionFailed,
    CompactionStarted,
    ContextWarning,
    TurnFailed,
)
from core.factory import build_registry
from core.recall import build_recall_tool
from core.session import AgentSession
from core.transcript import Transcript
from support import FakeBackend, text_chunks
from tui.app import YenaiApp
from tui.widgets.chat_input import ChatInput


def make_archive(tmp_path: Path) -> ContextArchive:
    return ContextArchive(tmp_path / ".agents" / "context")


def build_session(config, workspace, history_dir, archive, backend):
    """手工装配带归档目录的会话（conftest 的 make_session 不接 archive）。"""

    def registry_factory(root):
        return build_registry(root, archive=archive)

    session = AgentSession(
        backend,
        registry_factory(workspace),
        config,
        Transcript(history_dir, config.model_name),
        registry_factory=registry_factory,
        archive=archive,
    )
    return session


async def wait_idle(app: YenaiApp, pilot, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while app._turn_busy and time.monotonic() < deadline:
        await pilot.pause(0.01)
    assert not app._turn_busy, "本轮没有在超时前结束"
    await pilot.pause(0.1)


# ---------------------------------------------------------------- Token 估算


def test_estimate_tokens_counts_cjk_and_ascii() -> None:
    assert estimate_tokens("") == 0
    # 中文按 1.6 字 / token：4 个字约 2.5 token，不再是「1 字 1 token」
    assert estimate_tokens("你好") == 1
    assert estimate_tokens("你好世界") == 3
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcdefg") == 2
    # 同样字数的中文估算值明显低于早先的 1 字 1 token，避免占用条虚高
    text = "这是一段用于对比估算密度的中文测试文本"
    assert estimate_tokens(text) < len(text)


def test_resolve_window_prefers_config_then_model_then_default(config) -> None:
    assert resolve_window(config) == (DEFAULT_CONTEXT_WINDOW, True)
    assert resolve_window(replace(config, model_name="gpt-4o-mini")) == (128_000, False)
    assert resolve_window(replace(config, context_window=64_000)) == (64_000, False)


def test_measure_prefers_api_usage_over_estimate(config) -> None:
    real = measure(config, [{"role": "user", "content": "x"}], api_tokens=700)
    assert real.used == 700
    assert real.estimated is False
    assert real.ratio == pytest.approx(700 / DEFAULT_CONTEXT_WINDOW)

    estimated = measure(config, [{"role": "user", "content": "你好"}])
    assert estimated.estimated is True
    assert estimated.used >= 4


def test_context_usage_measures_the_messages_actually_sent(
    config, workspace, history_dir, tmp_path
) -> None:
    archive = make_archive(tmp_path)
    backend = FakeBackend([text_chunks("好"), text_chunks("嗯")])
    session = build_session(config, workspace, history_dir, archive, backend)
    list(session.ask("第一问"))
    list(session.ask("第二问"))

    expected = estimate_messages(recent_messages(session.history, config))
    expected += estimate_tools(session.registry.schemas())
    usage = session.context_usage()
    assert usage.estimated is True  # 假后端不给 usage，走本地估算
    assert usage.used == expected

    # 工具调用与结果只在当轮请求里存在，下一轮不再发送，因此不计入常驻上下文
    session._raw.append(
        {"role": "tool", "tool_call_id": "x", "content": "输出" * 2000}
    )
    assert session.context_usage().used == expected


def test_context_usage_adds_the_answer_generated_after_the_request(
    config, workspace, history_dir, tmp_path
) -> None:
    archive = make_archive(tmp_path)
    answer = "这是一条刚生成、还没进到 usage 里的回答"
    backend = FakeBackend([[LlmChunk(content=answer, usage_tokens=1200)]])
    session = build_session(config, workspace, history_dir, archive, backend)
    list(session.ask("问题"))

    usage = session.context_usage()
    assert usage.estimated is False
    # 真实用量 + 这条请求之后才生成的回答，数字不再落后一轮
    assert usage.used == 1200 + estimate_message(
        {"role": "assistant", "content": answer}
    )


def test_context_usage_follows_the_history_window(
    config, workspace, history_dir, tmp_path
) -> None:
    tight = replace(config, history_turns=1)
    archive = make_archive(tmp_path)
    backend = FakeBackend([text_chunks("回答") for _ in range(4)])
    session = build_session(tight, workspace, history_dir, archive, backend)
    for index in range(4):
        list(session.ask("第 %d 问" % index))

    # 历史累计 8 条，但真正发送的只有最近 1 轮，占用不会随轮数无限增长
    assert len(session.history) == 8
    basis = recent_messages(session.history, tight)
    assert [item["role"] for item in basis] == ["system", "user", "assistant"]
    assert session.context_usage().used == estimate_messages(
        basis
    ) + estimate_tools(session.registry.schemas())


# ---------------------------------------------------------------- 归档


def test_archive_writes_jsonl_with_order_and_tool_fields(tmp_path) -> None:
    archive = make_archive(tmp_path)
    messages = [
        {"role": "user", "content": "请整理上下文"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "get_date", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": "2026-10-22"},
    ]
    record = archive.save(messages, model="test-model")

    assert re.fullmatch(r"\d{8}-\d{6}", record.id)
    assert record.path.name == record.id + ".jsonl"
    assert record.message_count == 3
    assert record.bytes > 0

    lines = record.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    first = json.loads(lines[0])
    assert first["index"] == 1 and first["role"] == "user"
    assert first["model"] == "test-model"
    assert json.loads(lines[1])["tool_calls"][0]["function"]["name"] == "get_date"
    assert json.loads(lines[2])["tool_call_id"] == "call-1"

    loaded = archive.load(record.id)
    assert [item["role"] for item in loaded] == ["user", "assistant", "tool"]


def test_archive_same_second_gets_unique_id(tmp_path) -> None:
    archive = make_archive(tmp_path)
    first = archive.save([{"role": "user", "content": "a"}])
    second = archive.save([{"role": "user", "content": "b"}])
    assert first.id != second.id
    assert archive.ids()[0] == second.id  # 新的在前


def test_archive_rejects_path_traversal(tmp_path) -> None:
    archive = make_archive(tmp_path)
    assert archive.path_for("../secrets") is None
    assert archive.path_for("a/b") is None
    with pytest.raises(ValueError):
        archive.search("x", archive_id="../secrets")


def test_search_reports_archive_line_and_snippet(tmp_path) -> None:
    archive = make_archive(tmp_path)
    record = archive.save(
        [
            {"role": "user", "content": "部署脚本在 deploy.sh 里"},
            {"role": "assistant", "content": "预算上限是 5000 tokens"},
        ]
    )
    result = archive.search("预算")
    assert result.matched == 1
    hit = result.hits[0]
    assert hit.archive == record.id
    assert hit.line == 2
    assert hit.role == "assistant"
    assert "5000" in hit.snippet
    assert archive.search("预算", archive_id=record.id).matched == 1


def test_search_truncates_long_results(tmp_path) -> None:
    archive = make_archive(tmp_path)
    archive.save(
        [{"role": "user", "content": "重复关键词 %d" % index} for index in range(10)]
    )
    result = archive.search("重复关键词")
    assert result.matched == 10
    assert len(result.hits) <= 6
    assert result.truncated is True


# ---------------------------------------------------------------- recallContext


def test_recall_tool_returns_hits(tmp_path) -> None:
    archive = make_archive(tmp_path)
    record = archive.save([{"role": "user", "content": "唯一标记 alpha-keyword"}])
    tool = build_recall_tool(archive)

    assert tool.name == "recallContext"
    payload = tool.handler(text="alpha-keyword")
    assert payload["ok"] is True
    assert payload["hits"][0]["archive"] == record.id
    assert payload["hits"][0]["line"] == 1

    with pytest.raises(ToolError):
        tool.handler(text="   ")
    with pytest.raises(ToolError):
        tool.handler(text="alpha-keyword", id="不存在")


def test_factory_registers_recall_tool_only_with_archive(workspace, tmp_path) -> None:
    archive = ContextArchive(tmp_path / "context")
    assert "recallContext" in build_registry(workspace, archive=archive).names()
    assert "recallContext" not in build_registry(workspace).names()


# ---------------------------------------------------------------- 压缩流程


def test_compact_archives_then_replaces_context(
    config, workspace, history_dir, tmp_path
) -> None:
    backend = FakeBackend(
        [text_chunks("第一轮回答"), text_chunks("用户目标：把压缩做完")]
    )
    archive = make_archive(tmp_path)
    session = build_session(config, workspace, history_dir, archive, backend)

    list(session.ask("第一轮问题"))
    assert len(session.raw_context) == 2

    events = list(session.compact())
    assert [type(event).__name__ for event in events] == [
        "CompactionStarted",
        "CompactionArchived",
        "CompactionCompleted",
    ]
    started, archived, done = events
    assert isinstance(started, CompactionStarted)
    assert started.message_count == 2

    assert isinstance(archived, CompactionArchived)
    assert archive.path_for(archived.archive_id).is_file()

    assert isinstance(done, CompactionCompleted)
    assert done.archive_id == archived.archive_id
    assert "上下文压缩摘要" in done.summary
    assert archived.archive_id in done.summary
    assert "recallContext" in done.summary

    # 历史只剩摘要 + 确认语，原始上下文清空，阈值标记解除
    assert [item["role"] for item in session.history] == ["user", "assistant"]
    assert session.history[1]["content"] == SUMMARY_ACK
    assert session.raw_context == []
    assert session.compact_required is False
    assert session.context_usage().used < 2000

    # 压缩请求只带压缩 Prompt，且不传任何工具定义
    request = backend.requests[-1]
    assert request.tools == ()
    assert request.messages[0]["content"] == COMPACTION_PROMPT
    assert "第一轮问题" in request.messages[1]["content"]


def test_compact_failure_keeps_original_context(
    config, workspace, history_dir, tmp_path
) -> None:
    backend = FakeBackend([text_chunks("回答"), []])  # 第二次没有任何摘要内容
    archive = make_archive(tmp_path)
    session = build_session(config, workspace, history_dir, archive, backend)

    list(session.ask("问题"))
    before = list(session.history)

    events = list(session.compact())
    assert isinstance(events[-1], CompactionFailed)
    assert events[-1].error.code is ErrorCode.COMPACT_FAILED

    assert session.history == before
    assert len(session.raw_context) == 2
    # 归档先落盘，压缩失败也不丢原始记录
    assert len(archive.ids()) == 1


def test_compact_without_context_fails_cleanly(
    config, workspace, history_dir, tmp_path
) -> None:
    archive = make_archive(tmp_path)
    session = build_session(config, workspace, history_dir, archive, FakeBackend())

    events = list(session.compact())
    assert isinstance(events[0], CompactionStarted)
    assert isinstance(events[-1], CompactionFailed)
    assert archive.ids() == []


# ---------------------------------------------------------------- 阈值与拦截


def test_threshold_warns_and_blocks_new_prompts(
    config, workspace, history_dir, tmp_path
) -> None:
    tight = replace(config, context_window=200)
    backend = FakeBackend([text_chunks("好的"), text_chunks("不该被调用")])
    archive = make_archive(tmp_path)
    session = build_session(tight, workspace, history_dir, archive, backend)

    events = list(session.ask("你好"))
    warnings = [event for event in events if isinstance(event, ContextWarning)]
    assert warnings, "超过 70% 应发出上下文警告"
    assert warnings[0].threshold == CONTEXT_WARN_RATIO
    assert warnings[0].window == 200
    assert session.compact_required is True

    blocked = list(session.ask("再来一次"))
    assert isinstance(blocked[0], TurnFailed)
    assert blocked[0].error.code is ErrorCode.CONTEXT_LIMIT
    assert len(backend.requests) == 1  # 被拦下的提问没有打到模型
    assert [item["content"] for item in session.history] == ["你好", "好的"]


def test_compact_releases_blocked_prompts(
    config, workspace, history_dir, tmp_path
) -> None:
    tight = replace(config, context_window=200)
    backend = FakeBackend(
        [text_chunks("好的"), text_chunks("摘要正文"), text_chunks("压缩后继续")]
    )
    archive = make_archive(tmp_path)
    session = build_session(tight, workspace, history_dir, archive, backend)

    list(session.ask("你好"))
    assert session.compact_required is True
    list(session.compact())
    assert session.compact_required is False

    events = list(session.ask("继续"))
    assert not any(isinstance(event, TurnFailed) for event in events)
    assert session.history[-2]["content"] == "继续"


# ---------------------------------------------------------------- TUI 占用条


async def test_context_bar_shows_default_marker_and_percent(
    config, workspace, history_dir, tmp_path
) -> None:
    archive = make_archive(tmp_path)
    backend = FakeBackend([text_chunks("好")])
    session = build_session(config, workspace, history_dir, archive, backend)
    app = YenaiApp(session=session, store=ConfigStore(tmp_path / "config.ini"))

    async with app.run_test() as pilot:
        bar = app.query_one("#context", Static)
        initial = str(bar.render())
        assert "128k" in initial
        assert "（默认）" in initial
        assert "~" in initial  # 还没拿到接口用量，数字是本地估算

        app.query_one("#prompt", ChatInput).load_text("hi")
        await pilot.press("enter")
        await wait_idle(app, pilot)

        after = str(bar.render())
        assert "已占用" in after
        assert "128k（默认）" in after


async def test_context_bar_drops_estimate_marker_when_usage_arrives(
    config, workspace, history_dir, tmp_path
) -> None:
    archive = make_archive(tmp_path)
    backend = FakeBackend([[LlmChunk(content="好", usage_tokens=1234)]])
    session = build_session(config, workspace, history_dir, archive, backend)
    app = YenaiApp(session=session, store=ConfigStore(tmp_path / "config.ini"))

    async with app.run_test() as pilot:
        app.query_one("#prompt", ChatInput).load_text("hi")
        await pilot.press("enter")
        await wait_idle(app, pilot)

        after = str(app.query_one("#context", Static).render())
        assert "~" not in after  # 拿到真实用量后不再标估算
        assert "1.2k" in after
        assert after.endswith("%")


async def test_compact_command_replaces_history_in_tui(
    config, workspace, history_dir, tmp_path
) -> None:
    archive = make_archive(tmp_path)
    backend = FakeBackend([text_chunks("回答"), text_chunks("摘要正文")])
    session = build_session(config, workspace, history_dir, archive, backend)
    app = YenaiApp(session=session, store=ConfigStore(tmp_path / "config.ini"))

    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", ChatInput)
        prompt.load_text("hi")
        await pilot.press("enter")
        await wait_idle(app, pilot)

        prompt.load_text("/compact")
        await pilot.press("enter")
        await wait_idle(app, pilot)

        assert [item["role"] for item in session.history] == ["user", "assistant"]
        assert session.history[1]["content"] == SUMMARY_ACK
        assert len(archive.ids()) == 1
