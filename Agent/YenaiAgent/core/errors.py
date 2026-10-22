"""core 的错误定义。

core 不产出用户文案：只给出稳定的 :class:`ErrorCode` 和可选诊断细节，
由界面层决定怎么显示（tui 里维护中文映射）。
"""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """可在界面层映射为提示语的错误分类。"""

    CONFIG_MISSING = "config_missing"
    CONFIG_INVALID = "config_invalid"
    REQUEST_FAILED = "request_failed"
    TOOL_ROUND_LIMIT = "tool_round_limit"
    INTERRUPTED = "interrupted"
    UNKNOWN = "unknown"


class AgentError(Exception):
    """core 的可预期错误基类。"""

    def __init__(self, code: ErrorCode, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(self._message())

    def _message(self) -> str:
        if self.detail:
            return "%s: %s" % (self.code.value, self.detail)
        return self.code.value

    def __str__(self) -> str:
        return self._message()


class ConfigError(AgentError):
    """配置缺失或非法。"""


class LlmRequestError(AgentError):
    """模型请求失败。"""


class ToolError(ValueError):
    """工具的可预期错误，错误文本会直接回给模型。"""