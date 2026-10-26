"""多行聊天输入框："Enter 发送、Ctrl+J 换行"。

Enter 是最顺手的发送键；换行用 Ctrl+J（Windows 控制台里唯一可靠、
能被程序区分出来的换行组合），部分支持增强键盘协议的终端里
Ctrl+Enter / Shift+Enter 也能换行。注意 Windows 控制台会丢掉 Ctrl 修饰，
Ctrl+Enter 会退化成普通 Enter（也就是发送），所以文案里把 Ctrl+J 作为
主要换行方式。
"""

from __future__ import annotations

from textual import events
from textual.message import Message
from textual.widgets import TextArea

#: 这些按键插入换行；Ctrl+J 是 Windows 控制台上唯一可靠的组合
NEWLINE_KEYS = frozenset({"ctrl+j", "ctrl+enter", "shift+enter", "alt+enter"})

#: 这些按键把内容交给上层发送
SUBMIT_KEYS = frozenset({"enter"})


class ChatInput(TextArea):
    """支持多行的聊天输入框。"""

    class Submitted(Message):
        """用户按下发送键：请求把文本作为一条消息发送。"""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def __init__(self, *, placeholder: str = "", id: str | None = None) -> None:
        super().__init__(
            "",
            soft_wrap=True,
            tab_behavior="focus",
            show_line_numbers=False,
            compact=True,
            highlight_cursor_line=False,
            placeholder=placeholder,
            id=id,
        )

    def submit(self) -> None:
        """把当前文本作为消息发送出去。"""
        self.post_message(self.Submitted(self.text))

    def reset(self) -> None:
        """清空输入并回到行首，供发送后调用。"""
        self.load_text("")

    async def _on_key(self, event: events.Key) -> None:
        if not self.read_only:
            key = event.key
            if key in SUBMIT_KEYS:
                event.stop()
                event.prevent_default()
                self.submit()
                return
            if key in NEWLINE_KEYS:
                event.stop()
                event.prevent_default()
                self.insert("\n")
                return
        await super()._on_key(event)