"""首次运行提示框：已生成 config.ini 模板，改完重启才能用。"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from ..i18n import FIRST_RUN_BODY, FIRST_RUN_HINT, FIRST_RUN_TITLE


class FirstRunScreen(ModalScreen[None]):
    """告知用户模板已生成；关闭后程序退出，等用户改完配置再启动。"""

    BINDINGS = [Binding("escape", "close", "关闭")]

    def __init__(self, path: Path | str) -> None:
        super().__init__()
        self._path = Path(path)

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog first-run-dialog"):
            yield Static(FIRST_RUN_TITLE, classes="title")
            yield Static(FIRST_RUN_BODY % str(self._path), markup=False)
            yield Static(FIRST_RUN_HINT, classes="hint", markup=False)
            with Horizontal(classes="buttons"):
                yield Button("退出", variant="primary", id="close")

    def on_mount(self) -> None:
        self.query_one("#close", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)
