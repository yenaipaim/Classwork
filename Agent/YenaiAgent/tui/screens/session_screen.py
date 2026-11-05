"""历史会话选择面板：上下键选择、Enter 恢复、Esc 取消。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from core.sessions import SessionInfo, SessionStore

from ..i18n import (
    SESSION_LIST_EMPTY,
    SESSION_LIST_HINT,
    SESSION_LIST_ITEM,
    SESSION_LIST_TITLE,
)


class SessionScreen(ModalScreen[str | None]):
    """列出历史会话；选中返回会话编号，取消返回 None。"""

    BINDINGS = [Binding("escape", "cancel", "取消")]

    def __init__(
        self,
        store: SessionStore,
        *,
        current: str | None = None,
    ) -> None:
        super().__init__()
        self._store = store
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog session-dialog"):
            yield Static(SESSION_LIST_TITLE, classes="title")
            yield Static(SESSION_LIST_HINT, classes="hint", markup=False)
            yield OptionList(id="session-list")

    def on_mount(self) -> None:
        try:
            items = tuple(self._store.list())
        except OSError:
            items = ()
        listing = self.query_one("#session-list", OptionList)
        if not items:
            listing.add_option(Option(SESSION_LIST_EMPTY, disabled=True))
            return
        for index, info in enumerate(items):
            label = SESSION_LIST_ITEM % (
                "▶" if info.id == self._current else " ",
                info.id,
                info.message_count,
                info.title,
            )
            listing.add_option(Option(label, id=info.id))
            if info.id == self._current:
                listing.highlighted = index
        listing.focus()

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        session_id = event.option.id
        if session_id is None:
            return
        self.dismiss(session_id)

    def action_cancel(self) -> None:
        self.dismiss(None)
