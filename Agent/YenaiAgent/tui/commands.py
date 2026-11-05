"""斜杠命令清单：`/` 补全菜单与帮助文案共用同一份定义。

这里只描述「命令名 + 一句话说明 + 是否带参数」，真正的执行仍在
`tui/app.py:_run_command` 里，避免出现两套各自维护的命令列表。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """一个斜杠命令的展示信息。"""

    name: str
    summary: str
    argument: str = ""
    accepts_argument: bool = False

    @property
    def label(self) -> str:
        """菜单里显示的写法：带参数的命令补上占位，如 `/model 名称`。"""
        return "%s %s" % (self.name, self.argument) if self.argument else self.name


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec("/help", "显示可用命令与快捷键"),
    CommandSpec("/new", "新建会话：先保存当前会话，再清空上下文"),
    CommandSpec("/resume", "从历史会话列表恢复一个会话", argument="编号", accepts_argument=True),
    CommandSpec("/save", "保存当前会话到 .agents/sessions"),
    CommandSpec("/sessions", "列出历史会话"),
    CommandSpec("/export", "把当前会话导出成 Markdown", argument="目录", accepts_argument=True),
    CommandSpec("/clear", "清空屏幕上的消息（保留上下文）"),
    CommandSpec("/reset", "清空上下文并另起会话"),
    CommandSpec("/compact", "压缩上下文：归档原始记录并生成摘要"),
    CommandSpec("/status", "查看会话编号、模型、上下文与工作区"),
    CommandSpec("/tools", "列出当前注册的全部工具"),
    CommandSpec("/model", "查看或切换模型", argument="名称", accepts_argument=True),
    CommandSpec("/workspace", "查看或切换工作区", argument="目录", accepts_argument=True),
    CommandSpec("/skills", "查看已加载的技能与跳过原因"),
    CommandSpec("/mcp", "查看 MCP Server 状态与工具数"),
    CommandSpec("/config", "修改模型配置（会开始新会话）"),
    CommandSpec("/quit", "退出程序（与 /exit 相同）"),
    CommandSpec("/exit", "退出程序"),
)


def matching(prefix: str) -> tuple[CommandSpec, ...]:
    """按前缀过滤命令（大小写不敏感）；空前缀返回全部。"""
    lowered = prefix.lower()
    return tuple(spec for spec in COMMANDS if spec.name.lower().startswith(lowered))


def find(name: str) -> CommandSpec | None:
    """按完整命令名查找；大小写不敏感。"""
    lowered = name.lower()
    for spec in COMMANDS:
        if spec.name.lower() == lowered:
            return spec
    return None
