"""输入框上方的斜杠命令补全菜单。

只做三件事：按前缀列出候选、上下移动高亮、把选中的命令交回输入框。
键盘事件由 `ChatInput` 拦截后转进来（见 `ChatInput._handle_menu_key`）。
"""

from __future__ import annotations

from textual.widgets import OptionList
from textual.widgets.option_list import Option

from ..commands import CommandSpec, find, matching


class CommandMenu(OptionList):
    """命令候选列表；没有候选时自己收起，不占界面空间。"""

    #: 焦点始终留在输入框：点击候选不会把键盘抢走，Tab / Enter 仍归 ChatInput
    can_focus = False

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id, compact=True)
        self._prefix = ""

    # ---------------------------------------------------------------- 状态

    @property
    def is_open(self) -> bool:
        """当前是否真的显示着候选（显示但空列表算关闭）。"""
        return bool(self.display) and self.option_count > 0

    @property
    def prefix(self) -> str:
        return self._prefix

    @property
    def commands(self) -> tuple[CommandSpec, ...]:
        """当前前缀对应的候选命令。"""
        return matching(self._prefix)

    @property
    def selected(self) -> CommandSpec | None:
        """高亮项对应的命令；没有高亮时返回 None。"""
        index = self.highlighted
        if index is None or not self.option_count:
            return None
        option = self.get_option_at_index(index)
        return find(str(option.id)) if option.id else None

    # ---------------------------------------------------------------- 操作

    def open_for(self, prefix: str) -> bool:
        """按前缀刷新候选，返回是否显示。

        `/` 开头的半截命令才弹菜单：已经完整输入（`/help`）或没有候选时收起，
        免得用户按下 Enter 时被菜单“抢”掉这一次发送。
        """
        specs = matching(prefix)
        if not specs or find(prefix) is not None:
            self.close()
            return False
        self._prefix = prefix
        self.set_options(
            [Option("%s  ·  %s" % (spec.label, spec.summary), id=spec.name) for spec in specs]
        )
        self.highlighted = 0
        self.display = True
        return True

    def move(self, delta: int) -> None:
        """上下移动高亮，越界时循环。"""
        if not self.option_count:
            return
        current = self.highlighted if self.highlighted is not None else -1
        self.highlighted = (current + delta) % self.option_count

    def close(self) -> None:
        """收起菜单并清空候选。"""
        self.display = False
        self.clear_options()
        self._prefix = ""
