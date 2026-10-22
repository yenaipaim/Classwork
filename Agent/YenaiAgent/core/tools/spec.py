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

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def describe(self) -> str:
        """供 list_tools 工具回给模型的清单文本。"""
        return "\n".join(
            "%s：%s" % (tool.name, tool.description) for tool in self._tools.values()
        )

    def execute(self, name: str, arguments: str) -> ToolOutcome:
        """执行一次工具调用；任何可预期错误都转成 ok=False 的结果。"""
        tool = self._tools.get(name)
        if tool is None:
            return _failure("未知工具：%s" % name)

        try:
            payload = json.loads(arguments) if arguments and arguments.strip() else {}
        except json.JSONDecodeError as exc:
            return _failure("工具参数不是合法 JSON：%s" % exc)

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