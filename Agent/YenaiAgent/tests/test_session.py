"""会话编排测试：流式、工具循环、失败、中断与上下文提交。"""

from __future__ import annotations

import json

from core.config import AppConfig
from core.errors import ErrorCode, LlmRequestError
from core.events import (
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
    TurnCancelled,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
)
from core.llm.types import LlmChunk
from core.session import CancelToken
from support import FakeBackend, RaisingBackend, text_chunks, tool_script


def collect(session, question, cancel=None):
    return list(session.ask(question, cancel))


def test_plain_turn_commits_history_and_transcript(make_session) -> None:
    backend = FakeBackend([text_chunks("你", "好")])
    session = make_session(backend)

    events = collect(session, "你好")

    assert isinstance(events[0], TurnStarted)
    assert [event.text for event in events if isinstance(event, TextDelta)] == ["你", "好"]
    completed = events[-1]
    assert isinstance(completed, TurnCompleted)
    assert completed.text == "你好"
    assert completed.tool_calls == ()

    assert session.history == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好"},
    ]
    path = session.transcript_path
    assert path is not None and path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "# 模型：test-model" in text
    assert "[回复]\n你好" in text


def test_tool_round_is_executed_and_fed_back(make_session) -> None:
    backend = FakeBackend(
        [
            tool_script("call-1", "isLeapyear", '{"year": 2048}'),
            text_chunks("2048 是闰年"),
        ]
    )
    session = make_session(backend)

    events = collect(session, "2048 是闰年吗")

    started = [event for event in events if isinstance(event, ToolCallStarted)]
    finished = [event for event in events if isinstance(event, ToolCallFinished)]
    assert [(event.name, event.call_id) for event in started] == [("isLeapyear", "call-1")]
    assert finished[0].ok is True
    assert finished[0].output == "2048 年是闰年"

    assert len(backend.requests) == 2
    second_messages = backend.requests[1].messages
    assistant = second_messages[-2]
    assert assistant["role"] == "assistant"
    assert assistant["tool_calls"][0]["function"]["name"] == "isLeapyear"
    assert second_messages[-1] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": "2048 年是闰年",
    }

    completed = events[-1]
    assert isinstance(completed, TurnCompleted)
    assert len(completed.tool_calls) == 1
    assert completed.tool_calls[0].name == "isLeapyear"
    assert session.history[-1]["content"] == "2048 是闰年"
    assert "[工具] isLeapyear" in session.transcript_path.read_text(encoding="utf-8")


def test_tool_failure_is_reported_to_model(make_session) -> None:
    backend = FakeBackend(
        [tool_script("call-1", "read_text_file", '{"path": "absent.txt"}'), text_chunks("找不到")]
    )
    session = make_session(backend)

    events = collect(session, "读一下")

    finished = [event for event in events if isinstance(event, ToolCallFinished)]
    assert finished[0].ok is False
    assert "不存在" in finished[0].output
    tool_message = backend.requests[1].messages[-1]
    assert tool_message["role"] == "tool"
    assert json.loads(tool_message["content"])["ok"] is False


def test_request_failure_does_not_touch_history(make_session) -> None:
    session = make_session(RaisingBackend(LlmRequestError(ErrorCode.REQUEST_FAILED, "boom")))

    events = collect(session, "hi")

    failed = events[-1]
    assert isinstance(failed, TurnFailed)
    assert failed.error.code is ErrorCode.REQUEST_FAILED
    assert failed.partial_text == ""
    assert session.history == []
    assert session.transcript_path is None


def test_partial_text_is_preserved_on_failure(make_session) -> None:
    class FailAfterChunk:
        def stream(self, request):
            def generate():
                yield LlmChunk(content="半截")
                raise LlmRequestError(ErrorCode.REQUEST_FAILED, "断了")

            return generate()

    session = make_session(FailAfterChunk())
    events = collect(session, "hi")
    failed = events[-1]
    assert isinstance(failed, TurnFailed)
    assert failed.partial_text == "半截"
    assert session.history == []


def test_cancel_before_start(make_session) -> None:
    backend = FakeBackend([text_chunks("不该出现")])
    session = make_session(backend)
    cancel = CancelToken()
    cancel.cancel()

    events = collect(session, "hi", cancel)

    assert [type(event) for event in events] == [TurnStarted, TurnCancelled]
    assert backend.requests == []
    assert session.history == []


def test_cancel_mid_stream_keeps_partial_text(make_session) -> None:
    class CancelAfterFirstChunk:
        def __init__(self, cancel: CancelToken) -> None:
            self.cancel = cancel

        def stream(self, request):
            def generate():
                yield LlmChunk(content="半")
                self.cancel.cancel()
                yield LlmChunk(content="截")

            return generate()

    cancel = CancelToken()
    session = make_session(CancelAfterFirstChunk(cancel))

    events = collect(session, "hi", cancel)

    cancelled = events[-1]
    assert isinstance(cancelled, TurnCancelled)
    assert cancelled.partial_text == "半截"
    assert session.history == []


def test_tool_round_limit_finishes_gracefully(make_session) -> None:
    config = AppConfig(
        base_url="http://x", api_key="k", model_name="m", max_tool_rounds=1
    )
    backend = FakeBackend(
        [
            tool_script("call-1", "get_date", "{}"),
            tool_script("call-2", "get_date", "{}"),
            text_chunks("永远不会到这"),
        ]
    )
    session = make_session(backend, config=config)

    events = collect(session, "现在几点")

    done = events[-1]
    assert isinstance(done, TurnCompleted)
    assert "达到上限" in done.text
    assert len(done.tool_calls) == 1
    # 结果保留下来，用户可以接着追问
    assert [item["role"] for item in session.history] == ["user", "assistant"]


def test_repeated_identical_tool_calls_stop_gracefully(make_session) -> None:
    """模型用同样的参数反复调同一个工具时及时停下，而不是空转到上限。"""
    config = AppConfig(
        base_url="http://x", api_key="k", model_name="m", max_tool_rounds=10
    )
    scripts = [tool_script("call-%d" % i, "get_date", "{}") for i in range(4)]
    scripts.append(text_chunks("永远不会到这"))
    session = make_session(FakeBackend(scripts), config=config)

    events = collect(session, "几点了")

    done = events[-1]
    assert isinstance(done, TurnCompleted)
    assert "反复以相同参数调用" in done.text
    executed = [event for event in events if isinstance(event, ToolCallFinished)]
    assert len(executed) == 3  # 第 4 次在真正执行前就被拦下
    assert len(session.history) == 2


def test_empty_response_is_reported(make_session) -> None:
    """流结束了却没有任何内容时明确报错，而不是静默停在“思考中”。"""
    session = make_session(FakeBackend([[]]))

    events = collect(session, "hi")

    failed = events[-1]
    assert isinstance(failed, TurnFailed)
    assert "没有返回任何内容" in failed.error.detail
    assert session.history == []


def test_truncated_reply_is_flagged(make_session) -> None:
    """模型被输出上限截断时在回答末尾说明，避免用户以为回答就这么短。"""
    session = make_session(
        FakeBackend([[LlmChunk(content="开头部分", finish_reason="length")]])
    )

    events = collect(session, "写一段长文")

    done = events[-1]
    assert isinstance(done, TurnCompleted)
    assert done.text.startswith("开头部分")
    assert "输出上限" in done.text


def test_unknown_tool_returns_failure_json(make_session) -> None:
    backend = FakeBackend([tool_script("call-1", "nope", "{}"), text_chunks("好的")])
    session = make_session(backend)

    events = collect(session, "试试")

    finished = [event for event in events if isinstance(event, ToolCallFinished)]
    assert finished[0].ok is False
    assert "未知工具" in finished[0].output


def test_history_trimming_between_turns(make_session) -> None:
    config = AppConfig(
        base_url="http://x", api_key="k", model_name="m", history_turns=1
    )
    backend = FakeBackend(
        [
            text_chunks("a1"),
            text_chunks("a2"),
            text_chunks("a3"),
        ]
    )
    session = make_session(backend, config=config)

    collect(session, "q1")
    collect(session, "q2")
    collect(session, "q3")

    third = backend.requests[2].messages
    assert third[0]["role"] == "system"
    assert third[1] == {"role": "user", "content": "q2"}
    assert third[2] == {"role": "assistant", "content": "a2"}
    assert third[-1] == {"role": "user", "content": "q3"}


def test_reset_clears_history_and_starts_new_transcript(make_session) -> None:
    backend = FakeBackend([text_chunks("第一"), text_chunks("第二")])
    session = make_session(backend)

    collect(session, "q1")
    first_path = session.transcript_path
    session.reset()
    assert session.history == []
    assert session.transcript_path is None

    collect(session, "q2")
    second_path = session.transcript_path
    assert second_path is not None and second_path != first_path
    assert "q1" not in second_path.read_text(encoding="utf-8")