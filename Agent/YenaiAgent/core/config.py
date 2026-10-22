"""配置读取与保存。

配置是运行数据，不是界面交互：本模块不读取终端输入，也不打印，
缺失配置时由界面层负责引导用户填写。
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path

from .constants import (
    HISTORY_TURNS,
    MAX_TOKENS,
    MAX_TOOL_ROUNDS,
    REQUEST_TIMEOUT,
    SYSTEM_PROMPT,
)
from .errors import AgentError, ConfigError, ErrorCode
from .paths import DEFAULT_CONFIG_PATH

SECTION = "llm"
REQUIRED_KEYS = ("base_url", "api_key", "model_name")
# 报错时用中文名称，避免把英文键名直接抛给用户
KEY_LABELS = {
    "base_url": "接口地址",
    "api_key": "API 密钥",
    "model_name": "模型名称",
}


@dataclass(frozen=True, slots=True)
class AppConfig:
    """一次运行所需的全部配置。"""

    base_url: str
    api_key: str
    model_name: str
    request_timeout: float = REQUEST_TIMEOUT
    max_tokens: int = MAX_TOKENS
    history_turns: int = HISTORY_TURNS
    max_tool_rounds: int = MAX_TOOL_ROUNDS
    system_prompt: str = SYSTEM_PROMPT


class ConfigStore:
    """``config.ini`` 的读写门面，格式与 Practice01/02 兼容。"""

    def __init__(self, path: Path | str = DEFAULT_CONFIG_PATH) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        """文件存在且 ``[llm]`` 三个必填项都有值。"""
        if not self._path.is_file():
            return False
        try:
            self.load()
        except AgentError:
            return False
        return True

    def load(self) -> AppConfig:
        """读取配置；缺失或非法时抛 :class:`ConfigError`。"""
        if not self._path.is_file():
            raise ConfigError(ErrorCode.CONFIG_MISSING, str(self._path))

        parser = configparser.ConfigParser()
        try:
            parser.read(self._path, encoding="utf-8")
        except (configparser.Error, UnicodeDecodeError, OSError) as exc:
            raise ConfigError(ErrorCode.CONFIG_INVALID, "无法解析配置文件：%s" % exc) from exc

        if not parser.has_section(SECTION):
            raise ConfigError(ErrorCode.CONFIG_INVALID, "缺少 [llm] 配置段")

        values = {}
        for key in REQUIRED_KEYS:
            value = parser.get(SECTION, key, fallback="").strip()
            if not value:
                raise ConfigError(
                    ErrorCode.CONFIG_INVALID,
                    "配置项“%s”为空" % KEY_LABELS[key],
                )
            values[key] = value
        return AppConfig(**values)

    def save(self, base_url: str, api_key: str, model_name: str) -> AppConfig:
        """写入配置文件并返回对应配置。"""
        values = {
            "base_url": (base_url or "").strip(),
            "api_key": (api_key or "").strip(),
            "model_name": (model_name or "").strip(),
        }
        for key, value in values.items():
            if not value:
                raise ConfigError(
                    ErrorCode.CONFIG_INVALID,
                    "配置项“%s”不能为空" % KEY_LABELS[key],
                )

        parser = configparser.ConfigParser()
        parser[SECTION] = values
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("w", encoding="utf-8") as handle:
                parser.write(handle)
        except OSError as exc:
            raise ConfigError(ErrorCode.CONFIG_INVALID, "无法写入配置文件：%s" % exc) from exc
        return AppConfig(**values)