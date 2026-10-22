"""项目内固定路径。

统一从本文件推算，避免各模块各自用 ``__file__`` 拼路径时算错层级。
"""

from __future__ import annotations

from pathlib import Path

# Agent/YenaiAgent/
PACKAGE_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG_PATH = PACKAGE_ROOT / "config.ini"
DEFAULT_HISTORY_DIR = PACKAGE_ROOT / "chat_history"
# 文件工具的沙箱根：默认整个工程目录，可由 --workspace 覆盖
DEFAULT_WORKSPACE_ROOT = PACKAGE_ROOT