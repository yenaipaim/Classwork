"""聊天记录视图：只负责显示，不发起任何请求。"""

from __future__ import annotations

import json

from textual import events
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Markdown, Static

from ..i18n import (
    ASSISTANT_LABEL,
    TOOL_ARGS_LABEL,
    TOOL_RESULT_LABEL,
    USER_LABEL,
)

_MAX_DETAIL = 400
_MAX_ARG = 120


def _shorten(text: str, limit: int = _MAX_DETAIL) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "…（共 %d 字符）" % len(text)


def _pretty_arguments(arguments: str) -> str:
    """把工具参数 JSON 排版成缩进格式，解析失败时原样返回。"""
    raw = (arguments or "").strip() or "{}"
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return _shorten(raw, 500)
    return json.dumps(data, ensure_ascii=False, indent=2)


def _format_value(value) -> str:
    if isinstance(value, str):
        return _shorten(value, 40)
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return repr(value)


def _call_title(name: str, arguments: str) -> str:
    """工具标题：``isLeapyear(year=2026)``。"""
    raw = (arguments or "").strip() or "{}"
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return "%s(%s)" % (name, _shorten(raw, 60))
    if not isinstance(data, dict) or not data:
        return "%s()" % name
    parts = ["%s=%s" % (key, _format_value(value)) for key, value in data.items()]
    return "%s(%s)" % (name, _shorten(", ".join(parts), _MAX_ARG))


class _Message(Vertical):
    """一条带角色标签的消息：标签在上、正文在下，左侧有角色色条。"""

    def __init__(self, role: str, body) -> None:
        label = USER_LABEL if role == "user" else ASSISTANT_LABEL
        super().__init__(
            Static(label, classes="role", markup=False),
            body,
            classes="message " + role,
        )


class ToolCard(Vertical):
    """工具调用卡片：状态、耗时、参数与结果；点击标题折叠或展开。"""

    def __init__(
        self,
        name: str,
        arguments: str,
        output: str,
        ok: bool,
        duration_ms: int = 0,
        *,
        expanded: bool = True,
    ) -> None:
        self._expanded = expanded
        self._arrow = Static("▼" if expanded else "▶", classes="tool-arrow")
        self._body = Vertical(
            Static(TOOL_ARGS_LABEL, classes="tool-section"),
            Static(_pretty_arguments(arguments), classes="tool-args", markup=False),
            Static(TOOL_RESULT_LABEL, classes="tool-section"),
            Static(_shorten(output), classes="tool-result", markup=False),
            classes="tool-body",
        )
        header = Horizontal(
            self._arrow,
            Static("✓" if ok else "✗", classes="tool-icon"),
            Static(_call_title(name, arguments), classes="tool-title", markup=False),
            Static("· %d ms" % max(duration_ms, 0), classes="tool-time"),
            classes="tool-header",
        )
        super().__init__(header, self._body, classes="tool" if ok else "tool failed")
        self._body.display = expanded

    def on_click(self, event: events.Click) -> None:
        self.toggle()

    def toggle(self) -> None:
        self._expanded = not self._expanded
        self._body.display = self._expanded
        self._arrow.update("▼" if self._expanded else "▶")


class ChatLog(VerticalScroll):
    """消息流：用户提问、助手回复、工具调用与系统提示。

    流式阶段用 ``Static`` 追加纯文本，回复结束后换成 ``Markdown``
    渲染，避免在挂载完成前反复调用 ``Markdown.update`` 造成的竞态。
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._stream: _Message | None = None
        self._stream_body: Static | None = None
        self._stream_text = ""

    # ---------------------------------------------------------------- 消息

    def add_user(self, text: str) -> None:
        self.mount(_Message("user", Static(text, markup=False)))
        self.scroll_end(animate=False)

    def set_stream(self, text: str) -> None:
        """流式更新当前助手消息（没有就创建）。"""
        if self._stream is None:
            self._stream_body = Static("", markup=False)
            self._stream = _Message("assistant", self._stream_body)
            self.mount(self._stream)
        self._stream_text = text
        if self._stream_body is not None:
            self._stream_body.update(text)
        self.scroll_end(animate=False)

    def finish_assistant(self) -> None:
        """结束当前助手消息：纯文本换成 Markdown 渲染，下一段文字会新建一块。"""
        message = self._stream
        text = self._stream_text
        self._stream = None
        self._stream_body = None
        self._stream_text = ""
        if message is None:
            return
        message.remove()
        if text.strip():
            self.mount(_Message("assistant", Markdown(text)))
        self.scroll_end(animate=False)

    def add_tool(
        self,
        name: str,
        arguments: str,
        output: str,
        ok: bool,
        duration_ms: int = 0,
    ) -> None:
        self.finish_assistant()
        self.mount(ToolCard(name, arguments, output, ok, duration_ms))
        self.scroll_end(animate=False)

    def add_system(self, text: str, kind: str = "info") -> None:
        self.finish_assistant()
        classes = "system" if kind == "info" else "system " + kind
        self.mount(Static(text, classes=classes, markup=False))
        self.scroll_end(animate=False)

    def clear_messages(self) -> None:
        self.finish_assistant()
        self.remove_children()