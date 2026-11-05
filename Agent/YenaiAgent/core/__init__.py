"""YenaiAgent 的核心层。

这一层不依赖任何界面技术（textual / rich / tui），也不做 print / input，
因此可以被 TUI、Web 或桌面端直接复用。
"""

from .archive import ArchiveRecord, ContextArchive, RecallHit, RecallResult
from .budget import ContextUsage, estimate_tokens, measure, resolve_window
from .compaction import COMPACTION_PROMPT
from .config import AppConfig, ConfigStore
from .errors import AgentError, ConfigError, ErrorCode, LlmRequestError, ToolError
from .events import (
    AgentEvent,
    CompactionArchived,
    CompactionCompleted,
    CompactionFailed,
    CompactionStarted,
    ContextWarning,
    TextDelta,
    ToolCallFinished,
    ToolCallRecord,
    ToolCallStarted,
    TurnCancelled,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
)
from .factory import build_registry, create_session
from .session import AgentSession, CancelToken
from .skills import SkillInfo, SkillLibrary

__all__ = [
    "COMPACTION_PROMPT",
    "AgentError",
    "AgentEvent",
    "ArchiveRecord",
    "CompactionArchived",
    "CompactionCompleted",
    "CompactionFailed",
    "CompactionStarted",
    "ContextArchive",
    "ContextUsage",
    "ContextWarning",
    "RecallHit",
    "RecallResult",
    "AgentSession",
    "AppConfig",
    "CancelToken",
    "ConfigError",
    "ConfigStore",
    "ErrorCode",
    "LlmRequestError",
    "SkillInfo",
    "SkillLibrary",
    "TextDelta",
    "ToolCallFinished",
    "ToolCallRecord",
    "ToolCallStarted",
    "ToolError",
    "TurnCancelled",
    "TurnCompleted",
    "TurnFailed",
    "TurnStarted",
    "build_registry",
    "create_session",
    "estimate_tokens",
    "measure",
    "resolve_window",
]