"""斜杠命令补全：输入 `/` 弹出候选、过滤、Tab 补全、Enter 直接执行。

这些用例只驱动界面，不发起真实请求：`/help` 之类的命令完全由 TUI 处理。
"""

from __future__ import annotations

from core.config import ConfigStore
from support import FakeBackend
from tui.app import YenaiApp
from tui.commands import COMMANDS, find, matching
from tui.i18n import HELP_TEXT
from tui.widgets.chat_input import ChatInput
from tui.widgets.command_menu import CommandMenu


def make_app(session, tmp_path) -> YenaiApp:
    return YenaiApp(session=session, store=ConfigStore(tmp_path / "config.ini"))


def menu_ids(menu: CommandMenu) -> list[str]:
    """按显示顺序列出候选命令名。"""
    return [str(menu.get_option_at_index(i).id) for i in range(menu.option_count)]


def test_matching_filters_by_prefix() -> None:
    """前缀过滤大小写不敏感，空前缀给全部命令。"""
    assert matching("") == COMMANDS
    assert [spec.name for spec in matching("/com")] == ["/compact"]
    assert [spec.name for spec in matching("/C")] == [
        "/clear",
        "/compact",
        "/config",
    ]
    assert find("/MODEL") is not None
    assert find("/nope") is None


async def test_slash_opens_menu_with_all_commands(make_session, tmp_path) -> None:
    app = make_app(make_session(FakeBackend()), tmp_path)

    async with app.run_test() as pilot:
        menu = app.query_one("#commands", CommandMenu)
        assert not menu.is_open

        await pilot.press("slash")
        await pilot.pause()

        assert menu.is_open
        assert menu_ids(menu) == [spec.name for spec in COMMANDS]
        assert menu.highlighted == 0


async def test_typing_narrows_candidates(make_session, tmp_path) -> None:
    app = make_app(make_session(FakeBackend()), tmp_path)

    async with app.run_test() as pilot:
        menu = app.query_one("#commands", CommandMenu)
        await pilot.press("slash", "c", "o", "m")
        await pilot.pause()

        assert menu_ids(menu) == ["/compact"]

        await pilot.press("backspace")
        await pilot.pause()
        assert menu_ids(menu) == ["/compact", "/config"]

        await pilot.press("backspace")
        await pilot.pause()
        assert menu_ids(menu) == ["/clear", "/compact", "/config"]


async def test_tab_completes_model_argument(make_session, tmp_path) -> None:
    """带参数的命令补全后留一个空格，方便继续输入。"""
    app = make_app(make_session(FakeBackend()), tmp_path)

    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", ChatInput)
        menu = app.query_one("#commands", CommandMenu)
        await pilot.press("slash", "m", "o")
        await pilot.pause()

        await pilot.press("tab")
        await pilot.pause()

        assert prompt.text == "/model "
        assert prompt.cursor_location == (0, len("/model "))
        assert not menu.is_open


async def test_enter_runs_highlighted_command(make_session, tmp_path) -> None:
    """Enter 直接执行高亮项，并清空输入框。"""
    session = make_session(FakeBackend())
    app = make_app(session, tmp_path)

    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", ChatInput)
        menu = app.query_one("#commands", CommandMenu)
        chat = app.query_one("#chat")
        before = len(list(chat.children))

        await pilot.press("slash", "h")
        await pilot.pause()
        assert menu_ids(menu) == ["/help"]

        await pilot.press("enter")
        await pilot.pause()

        assert not menu.is_open
        assert prompt.text == ""
        assert len(list(chat.children)) > before
        assert session.history == []
        assert app._turn_busy is False

        text = "".join(str(child.render()) for child in chat.children)
        assert "可用命令" in text
        assert HELP_TEXT.splitlines()[0] in text


async def test_arrow_keys_move_highlight(make_session, tmp_path) -> None:
    app = make_app(make_session(FakeBackend()), tmp_path)

    async with app.run_test() as pilot:
        menu = app.query_one("#commands", CommandMenu)
        await pilot.press("slash")
        await pilot.pause()

        await pilot.press("down")
        await pilot.pause()
        assert menu.highlighted == 1
        assert menu.selected is not None and menu.selected.name == "/new"

        await pilot.press("up", "up")
        await pilot.pause()
        # 到顶后循环到最后一条
        assert menu.highlighted == len(COMMANDS) - 1


async def test_escape_closes_menu_but_keeps_text(make_session, tmp_path) -> None:
    app = make_app(make_session(FakeBackend()), tmp_path)

    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", ChatInput)
        menu = app.query_one("#commands", CommandMenu)
        await pilot.press("slash")
        await pilot.pause()
        assert menu.is_open

        await pilot.press("escape")
        await pilot.pause()

        assert not menu.is_open
        assert prompt.text == "/"


async def test_pasted_text_syncs_menu(make_session, tmp_path) -> None:
    """粘贴/程序回填不经过按键，也要刷新候选（靠 TextArea.Changed 兜底）。"""
    app = make_app(make_session(FakeBackend()), tmp_path)

    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", ChatInput)
        menu = app.query_one("#commands", CommandMenu)

        # load_text 会把光标放回开头，真实粘贴则落在末尾，这里手动对齐
        prompt.load_text("/mo")
        prompt.move_cursor(prompt.document.end)
        await pilot.pause()
        assert menu_ids(menu) == ["/model"]

        prompt.load_text("/model 名称\n第二行")
        prompt.move_cursor(prompt.document.end)
        await pilot.pause()
        assert not menu.is_open


async def test_menu_hidden_for_plain_text_and_arguments(
    make_session, tmp_path
) -> None:
    app = make_app(make_session(FakeBackend()), tmp_path)

    async with app.run_test() as pilot:
        menu = app.query_one("#commands", CommandMenu)

        await pilot.press("h", "i")
        await pilot.pause()
        assert not menu.is_open

        await pilot.press("backspace", "backspace", "slash", "w", "o", "r", "k")
        await pilot.pause()
        assert menu_ids(menu) == ["/workspace"]

        # 开始写参数后不再弹菜单
        await pilot.press("space")
        await pilot.pause()
        assert not menu.is_open


async def test_complete_command_name_closes_menu(make_session, tmp_path) -> None:
    """已完整输入的命令不再需要候选，避免 Enter 被菜单抢走。"""
    app = make_app(make_session(FakeBackend()), tmp_path)

    async with app.run_test() as pilot:
        menu = app.query_one("#commands", CommandMenu)
        await pilot.press("slash", "h", "e", "l", "p")
        await pilot.pause()

        assert not menu.is_open


async def test_read_only_does_not_open_menu(make_session, tmp_path) -> None:
    """等待模型回复时输入框只读，不该再弹候选。"""
    app = make_app(make_session(FakeBackend()), tmp_path)

    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", ChatInput)
        menu = app.query_one("#commands", CommandMenu)

        prompt.read_only = True
        prompt.load_text("/")
        prompt.sync_menu()
        await pilot.pause()

        assert not menu.is_open
