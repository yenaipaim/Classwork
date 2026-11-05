"""TUI 无头测试：用 Textual 的 run_test 驱动，不碰网络。"""

from __future__ import annotations

import time

import pytest
from textual.screen import Screen
from textual.widgets import Input, OptionList, Static

from core.config import ConfigStore
from core.errors import ErrorCode, LlmRequestError
from core.sessions import SessionStore
from core.llm.types import LlmChunk
from support import FakeBackend, RaisingBackend, text_chunks, tool_script
from tui.app import YenaiApp
from tui.screens.config_screen import ConfigScreen
from tui.screens.first_run_screen import FirstRunScreen
from tui.screens.session_screen import SessionScreen
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


class _SlowBackend:
    """故意拖延几秒才给出内容，用来观察状态栏的等待计时。"""

    def __init__(self, seconds: float = 3.0) -> None:
        self.seconds = seconds

    def stream(self, request):
        def generate():
            time.sleep(self.seconds)
            yield LlmChunk(content="好")

        return generate()


async def test_status_shows_elapsed_time_while_waiting(make_session, tmp_path) -> None:
    """忙碌时状态栏每秒刷新等待秒数，让用户知道程序还活着。"""
    app = make_app(make_session(_SlowBackend(3.0)), tmp_path)

    async with app.run_test() as pilot:
        await submit(app, pilot, "hi")
        await pilot.pause(1.4)

        status = str(app._status.content)
        assert "思考中" in status
        assert "秒" in status

        await wait_idle(app, pilot, timeout=10.0)


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


async def test_first_run_creates_template_and_shows_notice(tmp_path) -> None:
    """没有 config.ini 时：生成带示例值的完整模板，并弹框提示改完重启。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_path = tmp_path / "config.ini"
    app = YenaiApp(
        config_path=config_path,
        history_dir=tmp_path / "history",
        workspace_root=workspace,
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, FirstRunScreen)
        text = "".join(str(widget.render()) for widget in app.screen.query(Static))
        assert str(config_path) in text
        assert "重新启动" in text

        assert app._session is None
        assert config_path.is_file()
        body = config_path.read_text(encoding="utf-8")
        assert "sk-mock-replace-me" in body
        for section in ("[llm]", "[context]", "[session]", "[tools]", "[mcp]"):
            assert section in body

        await pilot.press("escape")
        await pilot.pause()

    assert app._session is None


async def test_second_run_reads_template_and_builds_session(tmp_path) -> None:
    """模板改好后再启动：直接读取配置并建会话，不再弹提示框。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_path = tmp_path / "config.ini"
    store = ConfigStore(config_path)
    store.ensure_template()
    store.save("http://example.test/v1", "secret", "test-model")

    app = YenaiApp(
        config_path=config_path,
        history_dir=tmp_path / "history",
        workspace_root=workspace,
        backend=FakeBackend(),
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, Screen)
        assert app._session is not None
        assert app._session.config.model_name == "test-model"
        assert app._session.config.model_name != "mock-model"


def _system_texts(app: YenaiApp) -> list[str]:
    return [
        _plain(child)
        for child in app._chat.children
        if child.has_class("system")
    ]


async def test_workspace_command_reports_switch_and_errors(make_session, tmp_path) -> None:
    """`/workspace` 查看、切换，目录不存在时报错且不改变工作区。"""
    new_ws = tmp_path / "ws_b"
    new_ws.mkdir()
    app = make_app(make_session(FakeBackend()), tmp_path)

    async with app.run_test() as pilot:
        await submit(app, pilot, "/workspace")
        assert any("当前工作区" in text for text in _system_texts(app))

        await submit(app, pilot, "/workspace %s" % new_ws)
        texts = _system_texts(app)
        assert any(
            "工作区已切换" in text and str(new_ws.resolve()) in text for text in texts
        )
        assert app._workspace_root == new_ws.resolve()

        await submit(app, pilot, "/workspace %s" % (tmp_path / "missing_ws"))
        assert any("切换工作区失败" in text for text in _system_texts(app))
        assert app._workspace_root == new_ws.resolve()  # 失败不改变工作区


async def test_skills_command_lists_loaded_and_skipped(
    config, workspace, history_dir, tmp_path
) -> None:
    """/skills 显示扫描目录、已加载技能与跳过原因，且不泄露正文。"""
    from core.factory import create_session
    from core.skills import SkillLibrary
    from tui.i18n import HELP_TEXT

    project = tmp_path / "proj"
    skill_dir = project / ".agents" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: 演示技能\n---\n正文内容不应出现在提示里\n",
        encoding="utf-8",
    )
    # 目录里没有 SKILL.md，会被跳过并给出原因
    (project / ".agents" / "skills" / "broken").mkdir()

    session = create_session(
        config,
        workspace_root=workspace,
        history_dir=history_dir,
        backend=FakeBackend(),
        skills=SkillLibrary(project),
    )
    app = make_app(session, tmp_path)

    async with app.run_test() as pilot:
        await submit(app, pilot, "/skills")
        joined = "\n".join(_system_texts(app))

    assert str(project / ".agents" / "skills") in joined
    assert "demo" in joined and "演示技能" in joined
    assert "broken" in joined and "目录内没有 SKILL.md" in joined
    assert "正文内容不应出现在提示里" not in joined
    assert "/skills" in HELP_TEXT


def test_parser_accepts_repeated_skills_dir() -> None:
    from tui.__main__ import build_parser

    parser = build_parser()
    assert parser.parse_args([]).skills_dirs is None
    args = parser.parse_args(["--skills-dir", "a", "--skills-dir", "b"])
    assert args.skills_dirs == ["a", "b"]


async def test_sidebar_shows_mcp_placeholder(make_session, tmp_path) -> None:
    """边栏常驻；没有 MCP 配置时给出提示而不是留白。"""
    app = make_app(make_session(FakeBackend()), tmp_path)

    async with app.run_test() as pilot:
        await pilot.pause()
        body = app.query_one("#mcp-sidebar-body", Static)
        text = str(body.render())
        assert "MCP" in text
        assert "未配置" in text


async def test_save_command_writes_session_log(make_session, tmp_path) -> None:
    store = SessionStore(tmp_path / "sessions", "test-model")
    session = make_session(FakeBackend([text_chunks("好")]), sessions=store)
    app = make_app(session, tmp_path)

    async with app.run_test() as pilot:
        await submit(app, pilot, "记录一句")
        await wait_idle(app, pilot)
        await submit(app, pilot, "/save")

        assert any("会话已保存" in text for text in _system_texts(app))
        assert store.path is not None and store.path.is_file()
        assert store.messages(store.session_id)[-1] == {"role": "assistant", "content": "好"}


async def test_new_command_rotates_session_log(make_session, tmp_path) -> None:
    store = SessionStore(tmp_path / "sessions", "test-model")
    session = make_session(FakeBackend([text_chunks("好")]), sessions=store)
    app = make_app(session, tmp_path)

    async with app.run_test() as pilot:
        await submit(app, pilot, "第一问")
        await wait_idle(app, pilot)
        first = store.session_id
        assert first is not None

        await submit(app, pilot, "/new")
        await pilot.pause()

        second = store.session_id
        assert second is not None and second != first
        assert store.path_for(first).is_file()  # 上一份已保存
        assert store.path_for(second).is_file()
        assert session.history == []
        assert any("已新建会话" in text for text in _system_texts(app))


async def test_resume_panel_lists_and_restores_session(make_session, tmp_path) -> None:
    """斜杠命令 /resume 弹出面板：上下键选择、Enter 恢复。"""
    old_store = SessionStore(tmp_path / "sessions", "test-model")
    old_id = old_store.start()
    old_store.append_message("user", "旧问题的正文")
    old_store.append_message("assistant", "旧回答")

    store = SessionStore(tmp_path / "sessions", "test-model")
    store.start()
    store.append_message("user", "当前会话")
    session = make_session(FakeBackend(), sessions=store)
    app = make_app(session, tmp_path)

    async with app.run_test() as pilot:
        await submit(app, pilot, "/resume")
        await pilot.pause()

        assert isinstance(app.screen, SessionScreen)
        options = app.screen.query_one("#session-list", OptionList)
        assert options.option_count == 2
        assert "▶" in str(options.get_option_at_index(0).prompt)

        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause()

        assert not isinstance(app.screen, SessionScreen)
        assert session.session_id == old_id
        assert session.history[0]["content"] == "旧问题的正文"
        assert any("已恢复会话" in text for text in _system_texts(app))


async def test_resume_escape_keeps_current_session(make_session, tmp_path) -> None:
    """Esc 取消面板，不动当前上下文。"""
    store = SessionStore(tmp_path / "sessions", "test-model")
    store.start()
    store.append_message("user", "当前会话")
    session = make_session(FakeBackend(), sessions=store)
    app = make_app(session, tmp_path)
    current = store.session_id

    async with app.run_test() as pilot:
        await submit(app, pilot, "/resume")
        await pilot.pause()
        assert isinstance(app.screen, SessionScreen)

        await pilot.press("escape")
        await pilot.pause()

        assert not isinstance(app.screen, SessionScreen)
        assert store.session_id == current


async def test_sessions_command_lists_archive(make_session, tmp_path) -> None:
    store = SessionStore(tmp_path / "sessions", "test-model")
    store.start()
    store.append_message("user", "列出来的这一条")
    session = make_session(FakeBackend(), sessions=store)
    app = make_app(session, tmp_path)

    async with app.run_test() as pilot:
        await submit(app, pilot, "/sessions")

        text = "\n".join(_system_texts(app))
        assert "历史会话" in text
        assert "列出来的这一条" in text
        assert "▶" in text


async def test_export_command_writes_markdown(make_session, tmp_path) -> None:
    store = SessionStore(tmp_path / "sessions", "test-model")
    session = make_session(FakeBackend([text_chunks("好")]), sessions=store)
    target = tmp_path / "dump"
    app = make_app(session, tmp_path)

    async with app.run_test() as pilot:
        await submit(app, pilot, "导出这句")
        await wait_idle(app, pilot)
        await submit(app, pilot, "/export %s" % target)

        assert any("会话已导出" in text for text in _system_texts(app))
        exported = list(target.glob("*.md"))
        assert exported and "导出这句" in exported[0].read_text(encoding="utf-8")


async def test_status_lists_model_and_project_prompt(make_session, workspace, tmp_path) -> None:
    (workspace / "AGENTS.md").write_text("# 约定\n短回答", encoding="utf-8")
    store = SessionStore(tmp_path / "sessions", "test-model")
    session = make_session(FakeBackend(), sessions=store, project_root=workspace)
    app = make_app(session, tmp_path)

    async with app.run_test() as pilot:
        await submit(app, pilot, "/status")

        text = "\n".join(_system_texts(app))
        assert "会话状态" in text
        assert "test-model" in text
        assert "上下文" in text
        assert "已注入项目约定" in text
        assert "AGENTS.md" in text


async def test_tools_command_lists_registry(make_session, tmp_path) -> None:
    app = make_app(make_session(FakeBackend()), tmp_path)

    async with app.run_test() as pilot:
        await submit(app, pilot, "/tools")

        text = "\n".join(_system_texts(app))
        assert "已注册工具" in text
        assert "read_text_file" in text
