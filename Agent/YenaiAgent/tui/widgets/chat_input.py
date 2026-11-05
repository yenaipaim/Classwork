"""多行聊天输入框："Enter 发送、Ctrl+J 换行"。

Enter 是最顺手的发送键；换行用 Ctrl+J（Windows 控制台里唯一可靠、
能被程序区分出来的换行组合），部分支持增强键盘协议的终端里
Ctrl+Enter / Shift+Enter 也能换行。注意 Windows 控制台会丢掉 Ctrl 修饰，
Ctrl+Enter 会退化成普通 Enter（也就是发送），所以文案里把 Ctrl+J 作为
主要换行方式。

输入以 `/` 开头时，把候选命令交给 :class:`CommandMenu` 显示：↑↓ 选择、
Tab 补全（带参数的命令补出空格）、Enter 直接执行、Esc 收起。
"""

from __future__ import annotations

from textual import events
from textual.message import Message
from textual.widgets import TextArea

from .command_menu import CommandMenu

#: 这些按键插入换行；Ctrl+J 是 Windows 控制台上唯一可靠的组合
NEWLINE_KEYS = frozenset({"ctrl+j", "ctrl+enter", "shift+enter", "alt+enter"})

#: 这些按键把内容交给上层发送
SUBMIT_KEYS = frozenset({"enter"})

#: 菜单展开时由输入框截走的按键
MENU_KEYS = frozenset({"up", "down", "tab", "escape", "enter"})

#: `/` 后面最多允许这么多字符再判定“不再像命令名”
MAX_PREFIX_LENGTH = 32


class ChatInput(TextArea):
    """支持多行的聊天输入框。"""

    class Submitted(Message):
        """用户按下发送键：请求把文本作为一条消息发送。"""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def __init__(
        self,
        *,
        placeholder: str = "",
        id: str | None = None,
        menu: CommandMenu | None = None,
    ) -> None:
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
        self.menu = menu

    def submit(self) -> None:
        """把当前文本作为消息发送出去。"""
        self.post_message(self.Submitted(self.text))

    def reset(self) -> None:
        """清空输入并回到行首，供发送后调用。"""
        self.load_text("")
        self.sync_menu()

    # ------------------------------------------------------------ 命令补全

    def sync_menu(self) -> None:
        """按当前输入刷新命令候选；不像命令时收起菜单。"""
        menu = self.menu
        if menu is None:
            return
        prefix = self._command_prefix()
        if prefix is None:
            menu.close()
        else:
            menu.open_for(prefix)

    def _command_prefix(self) -> str | None:
        """返回需要补全的命令前缀；当前输入不是半截命令时返回 None。"""
        if self.read_only:
            return None
        text = self.text
        if not text.startswith("/") or len(text) > MAX_PREFIX_LENGTH:
            return None
        if any(ch in text for ch in (" ", "\t", "\n", "\r")):
            return None
        row, column = self.cursor_location
        if row != 0 or column != len(text):
            return None
        return text

    def _handle_menu_key(self, event: events.Key) -> bool:
        """菜单展开时处理 ↑↓ / Tab / Enter / Esc；返回是否已消费该按键。"""
        menu = self.menu
        if menu is None or not menu.is_open:
            return False
        key = event.key
        if key in ("up", "down"):
            menu.move(-1 if key == "up" else 1)
        elif key == "tab":
            spec = menu.selected
            if spec is None:
                return False
            self.load_text(spec.name + (" " if spec.accepts_argument else ""))
            self.move_cursor(self.document.end)
            menu.close()
        elif key == "enter":
            spec = menu.selected
            if spec is None:
                return False
            self.load_text(spec.name)
            self.move_cursor(self.document.end)
            menu.close()
            event.stop()
            event.prevent_default()
            self.submit()
            return True
        elif key == "escape":
            menu.close()
        else:
            return False
        event.stop()
        event.prevent_default()
        return True

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """自身内容变化（键入、粘贴、程序回填）后同步候选。

        消息先投给发送者自己再冒泡，因此这里不依赖 App 再转一次；
        `load_text` 这类不经过按键的改动也能照顾到。
        """
        if event.text_area is self:
            self.sync_menu()

    async def _on_key(self, event: events.Key) -> None:
        if not self.read_only and self._handle_menu_key(event):
            return
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
                self.sync_menu()
                return
        await super()._on_key(event)
        self.sync_menu()
