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

WELCOME = "输入问题开始对话（Enter 发送，Ctrl+J 换行）；输入 / 选择命令，/help 查看说明。"
INPUT_PLACEHOLDER = "输入问题：Enter 发送，Ctrl+J 换行（可粘贴多行文本）"
READY = "就绪"
THINKING = "思考中…"
CANCELLING = "正在中断…（等当前工具结束，最长约 30 秒）"
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
WORKSPACE_USAGE = "当前工作区：%s；用 /workspace 目录路径 切换（相对路径按当前进程目录解析）。"
WORKSPACE_SWITCHED = "工作区已切换：%s；文件工具沙箱与 RunCli 工作目录随之改变，上下文保留。"
WORKSPACE_SWITCH_FAILED = "切换工作区失败：%s"
SKILLS_NEED_SESSION = "尚未创建会话（先完成模型配置），无法查看技能。"
SKILLS_HEADER = "技能扫描目录：%s（启动时确定，切换工作区不影响）"
SKILLS_ROOTS_HEADER = "技能扫描目录（%d 个，启动时确定，切换工作区不影响）："
SKILLS_ROOT_ITEM = "  - %s"
SKILLS_LOADED = "已加载 %d 个技能："
SKILLS_ITEM = "  - %s：%s"
SKILLS_NONE = "没有发现任何技能。"
SKILLS_ADD_HINT = (
    "在技能目录下建 <技能名>\\SKILL.md（frontmatter 含 name 与 description）后重启即可；"
    "也可以直接让 Agent 用 createSkill 新建（当轮生成立即可用，无需重启）。"
)
SKILLS_SKIPPED = "跳过 %d 个目录："
MCP_NEED_SESSION = "尚未创建会话（先完成模型配置），无法查看 MCP 服务。"
MCP_NONE = (
    "没有配置 MCP Server：默认读取技能目录里的 .mcp.json"
    "（缺失时会自动生成模板），也可用环境变量 YENAI_MCP_CONFIG 指定配置文件。"
)
MCP_HEADER = "MCP 服务（%d 个，配置：%s）："
MCP_ITEM = "  - %s [%s]：%s，工具 %d 个"
MCP_ITEM_DISABLED = "  - %s：未启用"
MCP_ITEM_FAILED = "  - %s [%s]：%s，连接失败：%s"
MCP_ISSUES = "配置问题（%d 处）："
MCP_ISSUE_ITEM = "  - %s"
MCP_STARTUP_OK = "MCP：已连接 %d 个服务，共 %d 个工具（/mcp 查看详情）。"
MCP_STARTUP_FAILED = "MCP：%d 个服务连接失败（%s），本地工具不受影响；/mcp 查看详情。"
MCP_TEMPLATE_CREATED = "MCP：首次运行已生成配置模板 %s，改完重启生效。"

# 右侧边栏：MCP 服务器与它们注册进 Agent 的工具
MCP_SIDEBAR_TITLE = "MCP 服务与工具"
MCP_SIDEBAR_LOADING = "正在连接 MCP 服务…\n（界面已可用，连上后自动刷新）"
MCP_SIDEBAR_NONE = "未配置 MCP 服务。\n可在技能目录的 .mcp.json 里添加。"
MCP_SIDEBAR_SERVER_OK = "● %s（%d 个工具）"
MCP_SIDEBAR_SERVER_DISABLED = "○ %s（未启用）"
MCP_SIDEBAR_SERVER_FAILED = "× %s（连接失败）"
MCP_SIDEBAR_TOOL = "    · %s"

# 首次运行：配置文件由程序生成，填的是示例值
FIRST_RUN_TITLE = "首次运行：已生成配置文件"
FIRST_RUN_BODY = (
    "已创建配置文件：\n  %s\n\n"
    "里面的接口地址、API 密钥、模型名称都是示例值（mock），"
    "必须先改成真实配置，程序才能连上模型。"
)
FIRST_RUN_HINT = "修改并保存后重新启动 YenaiAgent；下次启动会直接读取这份配置。"

# 会话管理（/new /save /resume /sessions /export）
SESSION_NEED_SESSION = "尚未创建会话（先完成模型配置）。"
SESSION_SAVE_NONE = "当前还没有会话记录可保存（先提问一次）。"
SESSION_SAVED = "会话已保存：%s"
SESSION_SAVE_FAILED = "保存会话失败：%s"
SESSION_NEW_PLAIN = "已新建会话（会话日志未启用，历史仅保留在内存）。"
SESSION_NEW_OK = "已新建会话 %s；上一份会话已保存。"
SESSION_RESTORED = "已恢复会话 %s：载入 %d 条消息。"
SESSION_RESTORE_FAILED = "恢复会话失败：%s"
SESSION_LIST_HEADER = "历史会话（%d 个，目录：%s）："
SESSION_LIST_ROW = "  %s %s · %d 条 · %s（更新 %s）"
SESSION_EXPORT_OK = "会话已导出：%s"
SESSION_EXPORT_FAILED = "导出会话失败：%s"
SESSION_LIST_TITLE = "恢复历史会话"
SESSION_LIST_HINT = "↑↓ 选择、Enter 恢复、Esc 取消；恢复会替换当前上下文，当前会话已自动保存。"
SESSION_LIST_ITEM = "%s %s · %d 条 · %s"
SESSION_LIST_EMPTY = "（没有历史会话）"
SESSION_LOG_OFF = "会话日志未启用，无法列出或恢复历史会话。"
SESSION_RESUME_HINT = "用 /resume 打开历史会话面板（↑↓ 选择、Enter 恢复、Esc 取消）。"
STATUS_ENABLED = "启用"
STATUS_DISABLED = "未启用"
STATUS_NONE = "—"
CONFIG_WRITE_FAILED = "无法生成配置文件：%s"
BUSY_TURN = "正在处理中，等本轮结束后再执行该命令。"
STATUS_BLOCKED = "已达阈值，等待 /compact"
STATUS_OK = "正常"
STATUS_LOADING = "加载中"
MOCK_CONFIG_WARNING = (
    "配置文件里仍是示例值（接口地址 / API 密钥 / 模型名称），"
    "请修改 %s 后重启，否则请求会失败。"
)

# 状态与工具清单（/status /tools）
STATUS_HEADER = "会话状态："
STATUS_ROW = "  %s：%s"
TOOLS_HEADER = "已注册工具（%d 个）："
TOOLS_ROW = "  - %s：%s"

# AGENTS.md 项目约定
AGENTS_MD_LOADED = (
    "已注入项目约定：%s（%d 字符）；会话首次加载时写入历史并持久化，后续轮次复用同一段文本。"
)
AGENTS_MD_NONE = "未注入 AGENTS.md：工作区 %s 下没有该文件。"

# 上下文占用条：值形如 "12.3k / 128k（默认）· 9.6%"
CONTEXT_BAR = "上下文 %s / %s · 已占用 %s"
CONTEXT_BAR_DEFAULT = "上下文 %s / %s（默认）· 已占用 %s"
CONTEXT_BAR_EMPTY = "上下文 —（尚未创建会话）"
CONTEXT_BAR_HINT = "（%s 为模型上下文窗口，超过 70%% 需 /compact）"
CONTEXT_WARNING = (
    "上下文已占用 %d/%d tokens（%.1f%%），达到阈值，已暂停接受新的提示词。"
    "请执行 /compact 压缩上下文后再继续。"
)
CONTEXT_PAUSED = "上下文已超过阈值，暂时不接受新提示词；请先执行 /compact 压缩上下文。"
COMPACT_NEED_SESSION = "尚未创建会话（先完成模型配置），无法压缩上下文。"
COMPACT_BUSY = "正在处理中，等本轮结束后再执行 /compact。"
COMPACT_USAGE = "用 /compact 把当前对话压缩成摘要；原始上下文会先归档到 .agents/context/。"
COMPACT_STARTED = "开始压缩上下文：先归档原始记录，再由模型生成摘要…"
COMPACT_RUNNING = "正在压缩上下文…（期间不调用任何工具）"
COMPACT_ARCHIVED = "原始上下文已归档：%s（%d 条消息，%.1f KB）"
COMPACT_DONE = (
    "压缩完成：摘要已替换历史，当前占用约 %d tokens；"
    "原始上下文归档编号 %s，需要历史细节时 Agent 可用 recallContext 检索。"
)
COMPACT_FAILED_HINT = "压缩失败，原上下文保持不变；可以重新执行 /compact。"

HELP_TEXT = """可用命令：
  会话
  /new        新建会话（自动保存当前会话）
  /resume     选择历史会话恢复；/resume 编号 直接恢复
  /sessions   列出历史会话
  /save       保存当前会话到 .agents/sessions/
  /export     导出当前会话为 Markdown；/export 目录 指定目录
  /reset      清空上下文并另起存档
  /clear      清空聊天显示
  上下文
  /compact    压缩上下文（原始记录归档到 .agents/context/，摘要替换历史）
  /status     查看模型、工作区、会话编号、上下文占用与 MCP 状态
  配置与能力
  /tools      查看当前注册的工具（含 MCP 工具）
  /model      查看当前模型；/model 名称 切换模型（保留上下文）
  /workspace  查看当前工作区；/workspace 目录 切换（文件工具与命令的范围）
  /skills     查看已加载的 Agent Skills 技能与跳过原因
  /mcp        查看 MCP Server 连接状态与注册的工具数量
  /config     修改模型配置（会开始新会话）
  /quit       退出程序（同 /exit）
  /help       显示本帮助
补全：输入 / 弹出命令候选，↑↓ 选择、Tab 补全、Enter 直接执行、Esc 收起
配置：所有可调参数都写在 config.ini；文件缺失时自动生成模板并提示修改后重启
项目约定：工作区的 AGENTS.md 在会话首次加载时注入并持久化，后续轮次复用
占用条：已用 / 窗口（百分比）；数字带 ~ 表示还没拿到接口用量，为本地估算
快捷键：Enter 发送、Ctrl+J 换行（部分终端也可用 Shift+Enter / Ctrl+Enter 换行）、Ctrl+C 中断/退出、Ctrl+Q 退出、Ctrl+L 清屏"""

# 与旧版终端程序保持一致的失败文案
_ERROR_TEMPLATES = {
    ErrorCode.CONFIG_MISSING: "缺少配置文件：%s",
    ErrorCode.CONFIG_INVALID: "配置错误：%s",
    ErrorCode.REQUEST_FAILED: "请求失败：%s",
    ErrorCode.TOOL_ROUND_LIMIT: "工具调用次数过多，本轮已中止。",
    ErrorCode.INTERRUPTED: "请求已中断。",
    ErrorCode.CONTEXT_LIMIT: "上下文已达阈值：%s",
    ErrorCode.ARCHIVE_FAILED: "上下文归档失败：%s",
    ErrorCode.COMPACT_FAILED: "上下文压缩失败：%s",
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