"""模型访问层：协议、OpenAI 兼容实现与流式拼装。"""

from .backend import LlmBackend, OpenAIBackend
from .collector import ToolCallInvocation, TurnCollector
from .types import LlmChunk, LlmRequest, ToolCallDelta

__all__ = [
    "LlmBackend",
    "LlmChunk",
    "LlmRequest",
    "OpenAIBackend",
    "ToolCallDelta",
    "ToolCallInvocation",
    "TurnCollector",
]