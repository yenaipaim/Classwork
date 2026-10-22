"""首次运行或 /config 时使用的配置对话框。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from core.config import AppConfig, ConfigStore
from core.errors import ConfigError


class ConfigScreen(ModalScreen[AppConfig | None]):
    """填写三项配置；保存成功返回 :class:`AppConfig`，取消返回 ``None``。"""

    BINDINGS = [Binding("escape", "cancel", "取消")]

    def __init__(
        self,
        store: ConfigStore,
        *,
        base_url: str = "",
        api_key: str = "",
        model_name: str = "",
    ) -> None:
        super().__init__()
        self._store = store
        self._base_url = base_url
        self._api_key = api_key
        self._model_name = model_name

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static("模型设置", classes="title")
            yield Static(
                "首次使用请先填写下面三项，保存后写入 config.ini。",
                classes="hint",
                markup=False,
            )
            yield Static("接口地址", classes="label")
            yield Input(
                value=self._base_url,
                placeholder="例如：https://api.example.com/v1",
                id="base-url",
            )
            yield Static("API 密钥", classes="label")
            yield Input(
                value=self._api_key,
                password=True,
                placeholder="粘贴你的 API 密钥",
                id="api-key",
            )
            yield Static("模型名称", classes="label")
            yield Input(
                value=self._model_name,
                placeholder="例如：mimo-v2.6-flash",
                id="model-name",
            )
            yield Static("", id="form-error", markup=False)
            with Horizontal(classes="buttons"):
                yield Button("保存", variant="primary", id="save")
                yield Button("取消", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#base-url", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self._save()
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _save(self) -> None:
        try:
            config = self._store.save(
                self.query_one("#base-url", Input).value,
                self.query_one("#api-key", Input).value,
                self.query_one("#model-name", Input).value,
            )
        except ConfigError as exc:
            self.query_one("#form-error", Static).update(exc.detail or str(exc))
            return
        self.dismiss(config)