"""TUI 无头测试：用 Textual 的 run_test 驱动，不碰网络。"""

from __future__ import annotations

import time

import pytest
from textual.widgets import Input

from core.config import ConfigStore
from core.errors import ErrorCode, LlmRequestError
from core.llm.types import LlmChunk
from support import FakeBackend, RaisingBackend, text_chunks, tool_script
from tui.app import YenaiApp
from tui.screens.config_screen import ConfigScreen
from tui.widgets.chat_input import ChatInput


async def wait_idle(app: YenaiApp, pilot, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while app._turn_busy and time.monotonic() < deadline:
        await pilot.pause(0.01)
    assert not app._turn_busy, "本轮问答没有在超时前结束"
    # 让挂载与 Markdown 渲染消息跑完
    await pilot.pause(0.1)


async def submit(app: YenaiApp, pilot, text: str) -> None:
    app.query_one("#prompt", ChatInput).load_text(text)
    await pilot.press("enter")
    await pilot.pause()


def make_app(session, tmp_path) -> YenaiApp:
    return YenaiApp(session=session, store=ConfigStore(tmp_path / "config.ini"))


async def test_enter_submits(make_session, tmp_path) -> None:
    """Enter 是发送键。"""
    backend = FakeBackend([text_chunks("好")])
    session = make_session(backend)
    app = make_app(session, tmp_path)

    async with app.run_test() as pilot:
        app.query_one("#prompt", ChatInput).load_text("hi")
        await pilot.press("enter")
        await wait_idle(app, pilot)

        assert session.history[0]["content"] == "hi"


async def test_shift_enter_inserts_newline(make_session, tmp_path) -> None:
    """Shift+Enter 同样只换行，不发送消息。"""
    app = make_app(make_session(FakeBackend()), tmp_path)

    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", ChatInput)
        prompt.load_text("第一行")
        prompt.cursor_location = (0, len("第一行"))

        await pilot.press("shift+enter")
        await pilot.pause()

        assert prompt.text == "第一行\n"
        assert len(app._chat.children) == 1  # 只有欢迎语，没有发出消息


async def test_ctrl_enter_inserts_newline(make_session, tmp_path) -> None:
    """增强键盘协议下 Ctrl+Enter 换行（Windows 控制台会退化成 Enter 发送）。"""
    app = make_app(make_session(FakeBackend()), tmp_path)

    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", ChatInput)
        prompt.load_text("hi")
        prompt.cursor_location = (0, 2)

        await pilot.press("ctrl+enter")
        await pilot.pause()

        assert prompt.text == "hi\n"
        assert len(app._chat.children) == 1  # 只有欢迎语，没有发出消息


async def test_ctrl_j_inserts_newline(make_session, tmp_path) -> None:
    """Ctrl+J 是 Windows 控制台上唯一可靠的换行键。"""
    app = make_app(make_session(FakeBackend()), tmp_path)

    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", ChatInput)
        prompt.load_text("a")
        prompt.cursor_location = (0, 1)

        await pilot.press("ctrl+j")
        await pilot.pause()

        assert prompt.text == "a\n"


async def test_multiline_question_is_sent_whole(make_session, tmp_path) -> None:
    backend = FakeBackend([text_chunks("好")])
    session = make_session(backend)
    app = make_app(session, tmp_path)

    async with app.run_test() as pilot:
        await submit(app, pilot, "第一行\n第二行")
        await wait_idle(app, pilot)

        assert backend.requests[0].messages[-1]["content"] == "第一行\n第二行"
        assert session.history[0]["content"] == "第一行\n第二行"
        assert app.query_one("#prompt", ChatInput).text == ""


async def test_streamed_reply_is_rendered(make_session, tmp_path) -> None:
    backend = FakeBackend([text_chunks("你", "好")])
    session = make_session(backend)
    app = make_app(session, tmp_path)

    async with app.run_test() as pilot:
        await submit(app, pilot, "hi")
        await wait_idle(app, pilot)

        assert session.history == [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "你好"},
        ]
        assert backend.requests[0].messages[-1]["content"] == "hi"

        markdown = app.query("Markdown")
        assert any(widget.source == "你好" for widget in markdown)


async def test_tool_call_is_shown_in_log(make_session, tmp_path) -> None:
    backend = FakeBackend(
        [tool_script("call-1", "isLeapyear", '{"year": 2048}'), text_chunks("是闰年")]
    )
    session = make_session(backend)
    app = make_app(session, tmp_path)

    async with app.run_test() as pilot:
        await submit(app, pilot, "2048 是闰年吗")
        await wait_idle(app, pilot)

        assert any(child.has_class("tool") for child in app._chat.children)
        assert session.history[-1]["content"] == "是闰年"


def _plain(widget) -> str:
    render = widget.render()
    return getattr(render, "plain", str(render))


async def test_tool_card_renders_call_details(make_session, tmp_path) -> None:
    from tui.widgets.chat_log import ToolCard

    backend = FakeBackend(
        [tool_script("call-1", "isLeapyear", '{"year": 2048}'), text_chunks("是闰年")]
    )
    app = make_app(make_session(backend), tmp_path)

    async with app.run_test(size=(100, 30)) as pilot:
        await submit(app, pilot, "2048 是闰年吗")
        await wait_idle(app, pilot)

        cards = list(app._chat.query(ToolCard))
        assert len(cards) == 1
        card = cards[0]
        assert _plain(card.query_one(".tool-title")).strip() == "isLeapyear(year=2048)"
        assert "ms" in _plain(card.query_one(".tool-time"))
        assert "year" in _plain(card.query_one(".tool-args"))
        assert _plain(card.query_one(".tool-result")).strip() == "2048 年是闰年"

        # 默认展开，点击标题后折叠成一行
        assert card._body.display
        await pilot.click(".tool-header")
        await pilot.pause()
        assert not card._body.display
        assert _plain(card.query_one(".tool-arrow")).strip() == "▶"


async def test_request_error_is_rendered(make_session, tmp_path) -> None:
    session = make_session(RaisingBackend(LlmRequestError(ErrorCode.REQUEST_FAILED, "boom")))
    app = make_app(session, tmp_path)

    async with app.run_test() as pilot:
        await submit(app, pilot, "hi")
        await wait_idle(app, pilot)

        assert session.history == []
        assert any(child.has_class("error") for child in app._chat.children)
        assert not app._prompt.read_only


async def test_help_clear_and_reset_commands(make_session, tmp_path) -> None:
    app = make_app(make_session(FakeBackend()), tmp_path)

    async with app.run_test() as pilot:
        assert len(app._chat.children) == 1  # 欢迎语

        await submit(app, pilot, "/help")
        assert len(app._chat.children) == 2

        await submit(app, pilot, "/clear")
        assert len(app._chat.children) == 0

        await submit(app, pilot, "/reset")
        assert len(app._chat.children) == 1

        await submit(app, pilot, "/nope")
        assert len(app._chat.children) == 2


async def test_model_command_switches_model_and_keeps_context(
    make_session, tmp_path
) -> None:
    backend = FakeBackend([text_chunks("好"), text_chunks("嗯")])
    session = make_session(backend)
    app = make_app(session, tmp_path)

    async with app.run_test() as pilot:
        await submit(app, pilot, "hi")
        await wait_idle(app, pilot)

        await submit(app, pilot, "/model")
        assert session.config.model_name == "test-model"

        await submit(app, pilot, "/model next-model")
        assert session.config.model_name == "next-model"
        saved = (tmp_path / "config.ini").read_text(encoding="utf-8")
        assert "next-model" in saved
        assert "test-key" in saved

        await submit(app, pilot, "again")
        await wait_idle(app, pilot)
        assert backend.requests[-1].model == "next-model"
        assert [item["content"] for item in session.history][:2] == ["hi", "好"]


async def test_reply_streams_incrementally(make_session, tmp_path) -> None:
    """回复必须逐块出现在界面上，而不是等整段结束才显示。"""

    class SlowBackend:
        def stream(self, request):
            def generate():
                for text in ("一", "二", "三"):
                    time.sleep(0.2)
                    yield LlmChunk(content=text)

            return generate()

    session = make_session(SlowBackend())
    app = make_app(session, tmp_path)

    async with app.run_test() as pilot:
        await submit(app, pilot, "hi")

        seen: set[str] = set()
        for _ in range(60):
            await pilot.pause(0.04)
            seen.add(app._chat._stream_text)
            if not app._turn_busy:
                break

        assert any(0 < len(text) < 3 for text in seen), seen
        assert session.history[-1]["content"] == "一二三"


async def test_first_run_opens_config_screen_and_builds_session(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    app = YenaiApp(
        config_path=tmp_path / "config.ini",
        history_dir=tmp_path / "history",
        workspace_root=workspace,
    )

    async with app.run_test() as pilot:
        assert isinstance(app.screen, ConfigScreen)
        labels = "".join(str(widget.render()) for widget in app.screen.query(".label"))
        assert "接口地址" in labels
        assert "API 密钥" in labels
        assert "模型名称" in labels

        app.screen.query_one("#base-url", Input).value = "http://example.test/v1"
        app.screen.query_one("#api-key", Input).value = "secret"
        app.screen.query_one("#model-name", Input).value = "test-model"
        await pilot.click("#save")
        await pilot.pause()

        assert not isinstance(app.screen, ConfigScreen)
        assert app._session is not None
        assert app._session.config.model_name == "test-model"
        assert (tmp_path / "config.ini").is_file()