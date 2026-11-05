"""recallContext 工具：在本地上下文归档里做全文关键词检索。

压缩摘要可能漏掉细节，模型可以随时用这个工具把原文片段捞回来。
本阶段只用 Python 自带的字符串匹配，不引入向量库或 Embedding。
"""

from __future__ import annotations

from typing import Any

from .archive import ContextArchive, RecallResult
from .errors import ToolError
from .tools.spec import ToolSpec

RECALL_TOOL_NAME = "recallContext"

RECALL_DESCRIPTION = (
    "检索此前被压缩归档的原始上下文（本地全文关键词检索）。"
    "id 可选：指定归档编号（如 20261022-153000），不填则检索全部归档；"
    "text 必填：要查找的关键词或文本。"
    "返回相关片段、所在归档编号与行号；结果已按相关度截断，不会撑爆上下文。"
)

RECALL_PARAMETERS = {
    "type": "object",
    "properties": {
        "id": {
            "type": "string",
            "description": "归档编号，例如 20261022-153000；省略表示检索全部归档",
        },
        "text": {
            "type": "string",
            "description": "要查找的关键词或文本内容",
        },
    },
    "required": ["text"],
}


def build_recall_tool(archive: ContextArchive) -> ToolSpec:
    """按归档目录生成 recallContext 工具。"""

    def recall(text: str, id: str | None = None) -> dict[str, Any]:
        query = (text or "").strip()
        if not query:
            raise ToolError("参数错误：text 不能为空")
        archive_id = (id or "").strip() or None
        try:
            result = archive.search(query, archive_id=archive_id)
        except ValueError as exc:
            raise ToolError(str(exc)) from None
        return _render(result)

    return ToolSpec(
        name=RECALL_TOOL_NAME,
        description=RECALL_DESCRIPTION,
        parameters=RECALL_PARAMETERS,
        handler=recall,
    )


def _render(result: RecallResult) -> dict[str, Any]:
    """工具结果：命中片段 + 来源位置；没命中时给出可用归档编号。"""
    payload: dict[str, Any] = {
        "ok": True,
        "query": result.query,
        "searched_archives": result.archives_searched,
        "matched": result.matched,
        "returned": len(result.hits),
        "truncated": result.truncated,
        "mode": result.mode,
        "hits": [
            {
                "archive": hit.archive,
                "line": hit.line,
                "role": hit.role,
                "score": hit.score,
                "snippet": hit.snippet,
            }
            for hit in result.hits
        ],
    }
    if not result.hits:
        payload["note"] = "没有匹配内容；可以换关键词，或确认归档编号是否存在。"
    elif result.truncated:
        payload["note"] = (
            "命中较多，只返回相关度最高的前 %d 条；可以加 id 限定归档或换更精确的关键词。"
            % len(result.hits)
        )
    return payload
