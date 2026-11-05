"""工具规格与注册表。

工具层不知道模型是谁、界面长什么样：只负责「名字 + JSON Schema + 处理函数」，
由会话层组装成请求，由界面层决定怎么展示执行过程。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..errors import ToolError

ToolHandler = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """一个可被模型调用的工具。"""

    name: str
    description: str
    parameters: Mapping[str, Any]
    handler: ToolHandler

    def schema(self) -> dict[str, Any]:
        """转成 OpenAI tools 数组里的一项。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": dict(self.parameters),
            },
        }


@dataclass(frozen=True, slots=True)
class ToolOutcome:
    """工具执行结果：文本给模型看，ok 给界面层标记失败。"""

    output: str
    ok: bool


class ToolRegistry:
    """按名字保存工具，保序输出 schema。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> "ToolRegistry":
        if tool.name in self._tools:
            raise ValueError("工具重复注册：%s" % tool.name)
        self._tools[tool.name] = tool
        return self

    def remove(self, name: str) -> bool:
        """按名字摘掉一个工具（MCP 异步加载后重新注册时用）。"""
        return self._tools.pop(name, None) is not None

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def execute(self, name: str, arguments: str) -> ToolOutcome:
        """执行一次工具调用；任何可预期错误都转成 ok=False 的结果。"""
        tool = self._tools.get(name)
        if tool is None:
            return _failure("未知工具：%s" % name)

        try:
            payload = json.loads(arguments) if arguments and arguments.strip() else {}
        except json.JSONDecodeError as exc:
            # 参数被 max_tokens 截断时，报错永远是“字符串没闭合”，
            # 把这条线索直接写进结果，模型和用户才知道该拆小或调大上限。
            hint = ""
            if exc.msg.startswith("Unterminated string") or exc.pos >= len(arguments) - 2:
                hint = "（参数可能被单次输出上限截断，请拆成多次写入，或在 config.ini 调大 max_tokens）"
            return _failure("工具参数不是合法 JSON：%s%s" % (exc, hint))

        if not isinstance(payload, dict):
            return _failure("工具参数必须是 JSON 对象")

        try:
            result = tool.handler(**payload)
        except ToolError as exc:
            return _failure(str(exc))
        except TypeError as exc:
            return _failure("工具参数错误：%s" % exc)
        except (OSError, UnicodeError) as exc:
            return _failure("工具执行失败：%s" % exc)
        except Exception as exc:  # 兜底，保证模型总能拿到一条结果
            return _failure("工具执行失败：%s" % exc)

        return _normalize(result)


def _normalize(result: Any) -> ToolOutcome:
    # MCP 工具直接给出成品的 ToolOutcome（输出可能不是 JSON），原样透传
    if isinstance(result, ToolOutcome):
        return result
    if isinstance(result, str):
        return ToolOutcome(result, True)
    if isinstance(result, Mapping):
        payload = dict(result)
        ok = payload.get("ok", True) is not False
        return ToolOutcome(json.dumps(payload, ensure_ascii=False), ok)
    return ToolOutcome(json.dumps(result, ensure_ascii=False), True)


def _failure(message: str) -> ToolOutcome:
    return ToolOutcome(
        json.dumps({"ok": False, "error": message}, ensure_ascii=False), False
    )