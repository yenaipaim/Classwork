"""界面文案。

core 只给出错误码，所有面向用户的中文都集中在这里，
将来做 Web/桌面端时可以整体替换而不影响业务层。
"""

from __future__ import annotations

from core.errors import AgentError, ErrorCode

APP_TITLE = "YenaiAgent"
APP_SUBTITLE = "终端界面"

USER_LABEL = "你"
ASSISTANT_LABEL = "AI"
TOOL_ARGS_LABEL = "参数"
TOOL_RESULT_LABEL = "结果"

WELCOME = "输入问题开始对话（Enter 发送，Ctrl+J 换行）；/help 查看命令。"
INPUT_PLACEHOLDER = "输入问题：Enter 发送，Ctrl+J 换行（可粘贴多行文本）"
READY = "就绪"
THINKING = "思考中…"
CANCELLING = "正在中断…（等当前工具结束，最长约 30 秒）"
TOOL_RUNNING = "调用工具"
# 等待时间与工具次数让用户能判断“还活着”而不是卡死
STATUS_THINKING_ELAPSED = "思考中… %d 秒（已调用工具 %d 次）"
STATUS_TOOL_RUNNING = "调用工具：%s · 已 %d 秒（第 %d 次）"

CANCELLED = "已中断，本轮内容不计入上下文。"
CONTEXT_CLEARED = "上下文已清空，下一轮从新对话开始。"
UNKNOWN_COMMAND = "未知命令：%s（/help 查看可用命令）"
NEED_CONFIG = "尚未配置模型，请先填写接口地址 / API 密钥 / 模型名称。"
CONFIG_CANCELLED = "未提供配置，无法继续。"
CONFIG_SAVED = "配置已保存，开始新会话。"
MODEL_USAGE = "当前模型：%s；用“/model 模型名称”切换，上下文会保留。"
MODEL_SWITCHED = "模型已切换为：%s（上下文保留，可继续提问）。"

HELP_TEXT = """可用命令：
  /help    显示本帮助
  /clear   清空聊天显示
  /reset   清空上下文并另起存档
  /model   查看当前模型；/model 名称 切换模型（保留上下文）
  /config  修改模型配置（会开始新会话）
  /exit    退出程序
快捷键：Enter 发送、Ctrl+J 换行（部分终端也可用 Shift+Enter / Ctrl+Enter 换行）、Ctrl+C 中断/退出、Ctrl+Q 退出、Ctrl+L 清屏"""

# 与旧版终端程序保持一致的失败文案
_ERROR_TEMPLATES = {
    ErrorCode.CONFIG_MISSING: "缺少配置文件：%s",
    ErrorCode.CONFIG_INVALID: "配置错误：%s",
    ErrorCode.REQUEST_FAILED: "请求失败：%s",
    ErrorCode.TOOL_ROUND_LIMIT: "工具调用次数过多，本轮已中止。",
    ErrorCode.INTERRUPTED: "请求已中断。",
    ErrorCode.UNKNOWN: "%s",
}

# 异常详情可能带整段响应体，太长反而看不清
_MAX_DETAIL = 300


def _shorten(detail: str) -> str:
    detail = " ".join(detail.split())
    if len(detail) > _MAX_DETAIL:
        return detail[:_MAX_DETAIL] + "…"
    return detail


def describe_error(error: AgentError) -> str:
    """把 core 的错误翻译成一句用户能看懂的话。"""
    template = _ERROR_TEMPLATES.get(error.code, _ERROR_TEMPLATES[ErrorCode.UNKNOWN])
    detail = _shorten(getattr(error, "detail", "") or "")
    if "%s" in template:
        if error.code is ErrorCode.REQUEST_FAILED and not detail:
            detail = "额度不足、网络异常或接口返回错误，请稍后重试"
        return template % (detail or "未知原因")
    return template