"""上下文压缩：压缩专用 Prompt、历史渲染与摘要拼装。

这里只做纯文本处理：把历史渲染成模型能读的文本、把摘要拼成新的上下文。
真正的「归档 → 调模型 → 替换历史」由 :class:`core.session.AgentSession` 编排。
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from .constants import COMPACT_TARGET_TOKENS

#: 压缩专用 Prompt：要求模型输出一份能让「没读过原文的 Agent」接手工作的摘要
COMPACTION_PROMPT = """你是一名 AI Agent 的上下文管理助手。当前会话即将达到上下文窗口限制，需要将历史对话压缩为一份高质量的工作摘要，以便 Agent 在新的上下文中继续执行任务。

请认真阅读提供的历史上下文，提取对后续工作仍然有价值的信息，并生成一份约 5,000 Tokens 的 Markdown 摘要。

摘要应重点保留以下内容：

1. **用户目标与要求**：用户希望完成什么任务？有哪些必须遵守的约束、偏好和验收条件？
2. **已经完成的工作**：哪些任务已经完成？实现了哪些功能？获得了哪些已经验证的结果？
3. **当前工作状态**：Agent 正在处理什么任务？当前进展到哪一步？是否存在尚未解决的问题？
4. **关键技术信息**：保留重要的文件路径、函数名称、接口定义、配置项、执行命令、错误信息和必要的代码片段。
5. **关键决策与原因**：记录用户和 Agent 已经确定的技术方案，以及重要的设计取舍。
6. **下一步任务**：明确接下来应该执行的操作，以及需要继续验证的事项。

请遵守以下要求：

- 优先保留对后续任务有直接影响的信息，删除寒暄、重复讨论、过时的尝试和无关内容。
- 对已经验证的事实与尚未验证的推测作出明确区分。
- 不要将计划完成的任务描述为已经完成。
- 重要的文件路径、函数名称、配置名称和命令应保留准确原文。
- 对失败的尝试，只保留有助于避免重复错误的信息。
- 如果信息存在冲突，应优先保留用户最新确认的要求，并简要说明仍然存在的冲突。
- 如果某些历史细节无法在摘要中完整保留，可简要说明它们已保存到原始上下文归档中，后续可以通过 recallContext 工具重新检索。
- 使用清晰的 Markdown 结构输出摘要，不要附加解释或无关内容。

最终目标：使一个从未阅读过原始对话的 Agent，仅凭这份摘要，就能够理解当前任务、继承关键决策，并继续开展工作。"""

#: 摘要开头，方便人和模型一眼看出这是压缩结果
SUMMARY_HEADER = "# 上下文压缩摘要"

#: 摘要被当作「用户交给 Agent 的交接说明」之后的确认语
SUMMARY_ACK = "已读取上述上下文摘要，继续执行任务。"

#: 单条消息渲染进压缩 Prompt 时的长度上限：工具结果动辄上万字，全塞进去反而超窗
MAX_MESSAGE_CHARS = 4000

ROLE_LABELS = {
    "system": "系统",
    "user": "用户",
    "assistant": "助手",
    "tool": "工具结果",
}


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    try:
        return json.dumps(content, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(content)


def render_message(message: Mapping[str, Any]) -> str:
    """把一条消息渲染成「角色 + 正文 + 工具调用 + 工具结果编号」的文本。"""
    role = str(message.get("role") or "unknown")
    label = ROLE_LABELS.get(role, role)
    lines: list[str] = []
    body = _content_text(message.get("content"))
    if body:
        lines.append(body)
    for call in message.get("tool_calls") or ():
        function = call.get("function") if isinstance(call, Mapping) else None
        if not isinstance(function, Mapping):
            continue
        lines.append(
            "调用工具 %s，参数：%s"
            % (function.get("name") or "", function.get("arguments") or "{}")
        )
    if message.get("tool_call_id"):
        lines.append("（对应调用 %s）" % message["tool_call_id"])

    text = "\n".join(lines).strip() or "（空）"
    if len(text) > MAX_MESSAGE_CHARS:
        text = (
            text[:MAX_MESSAGE_CHARS]
            + "\n……（本条过长已截断；完整内容保留在原始上下文归档中）"
        )
    return "### %s\n%s" % (label, text)


def render_transcript(messages: Sequence[Mapping[str, Any]]) -> str:
    """把历史消息按原顺序渲染成一段带编号的文本，交给 LLM 压缩。"""
    blocks = []
    for index, message in enumerate(messages, 1):
        blocks.append("[%d] %s" % (index, render_message(message)))
    return "\n\n".join(blocks)


def build_compaction_messages(
    messages: Sequence[Mapping[str, Any]],
    target_tokens: int = COMPACT_TARGET_TOKENS,
) -> list[dict[str, Any]]:
    """压缩请求的 messages：system 是压缩专用 Prompt，user 是待压缩的历史。"""
    user = (
        "请把下面这段历史上下文压缩成一份约 %d Tokens 的 Markdown 摘要。"
        "\n\n=== 历史上下文开始 ===\n%s\n=== 历史上下文结束 ==="
        % (target_tokens, render_transcript(messages))
    )
    return [
        {"role": "system", "content": COMPACTION_PROMPT},
        {"role": "user", "content": user},
    ]


def archive_note(created_at: str, archive_id: str) -> str:
    """摘要末尾的归档说明：告诉后续的 Agent 原文在哪、怎么找。"""
    return (
        "此前上下文已于 %s 完成压缩，原始上下文保存在编号为 %s 的归档文件中。"
        "如需查找历史信息，请使用 recallContext 工具。" % (created_at, archive_id)
    )


def compose_summary(summary: str, archive_id: str, created_at: str) -> str:
    """摘要正文 + 归档说明；摘要已自带标题时不再重复加。"""
    body = summary.strip()
    if not body.startswith(SUMMARY_HEADER):
        body = SUMMARY_HEADER + "\n\n" + body
    return "%s\n\n---\n\n%s" % (body, archive_note(created_at, archive_id))


def summary_history(summary_text: str) -> list[dict[str, Any]]:
    """把摘要变成新的上下文：一问一答，保持 user/assistant 成对。"""
    return [
        {"role": "user", "content": summary_text},
        {"role": "assistant", "content": SUMMARY_ACK},
    ]
