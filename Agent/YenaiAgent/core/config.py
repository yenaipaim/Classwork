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
    SEARCH_ENDPOINT,
    SYSTEM_PROMPT,
)
from .errors import AgentError, ConfigError, ErrorCode
from .paths import DEFAULT_CONFIG_PATH
from .skills import SKILLS_ROOTS_KEY, SKILLS_SECTION, split_skill_roots

SECTION = "llm"
REQUIRED_KEYS = ("base_url", "api_key", "model_name")
# 报错时用中文名称，避免把英文键名直接抛给用户
KEY_LABELS = {
    "base_url": "接口地址",
    "api_key": "API 密钥",
    "model_name": "模型名称",
}

# 可选的高级设置：不写就用 constants 里的默认值
OPTIONAL_INT_KEYS = ("max_tool_rounds", "history_turns", "max_tokens")
SEARCH_SECTION = "search"
SEARCH_KEY = "baidu_qianfan_api_key"
SEARCH_ENDPOINT_KEY = "endpoint"


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
    search_api_key: str = ""
    search_endpoint: str = SEARCH_ENDPOINT
    # 额外的技能根目录（[skills] roots）；空表示用默认的 <启动目录>/.agents/skills
    skill_roots: tuple[str, ...] = ()


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

        # interpolation=None：路径里的 %VAR% 不能被当成 configparser 的插值语法
        parser = configparser.ConfigParser(interpolation=None)
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

        search_api_key = ""
        search_endpoint = SEARCH_ENDPOINT
        if parser.has_section(SEARCH_SECTION):
            search_api_key = parser.get(SEARCH_SECTION, SEARCH_KEY, fallback="").strip()
            endpoint = parser.get(SEARCH_SECTION, SEARCH_ENDPOINT_KEY, fallback="").strip()
            if endpoint:
                search_endpoint = endpoint
        skill_roots: tuple[str, ...] = ()
        if parser.has_section(SKILLS_SECTION):
            skill_roots = tuple(
                split_skill_roots(
                    parser.get(SKILLS_SECTION, SKILLS_ROOTS_KEY, fallback="")
                )
            )
        return AppConfig(
            **values,
            search_api_key=search_api_key,
            search_endpoint=search_endpoint,
            skill_roots=skill_roots,
            max_tool_rounds=_optional_int(parser, "max_tool_rounds", MAX_TOOL_ROUNDS),
            history_turns=_optional_int(parser, "history_turns", HISTORY_TURNS),
            max_tokens=_optional_int(parser, "max_tokens", MAX_TOKENS),
        )

    def save(self, base_url: str, api_key: str, model_name: str) -> AppConfig:
        """写入配置文件并返回对应配置。

        界面上只编辑 ``[llm]``；``[search]`` 属于运行数据，原样保留。
        """
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

        parser = configparser.ConfigParser(interpolation=None)
        parser[SECTION] = values
        for key, raw in self._read_optional_llm_values().items():
            parser.set(SECTION, key, raw)
        search_section = self._read_search_section()
        if search_section:
            parser[SEARCH_SECTION] = search_section
        # 技能根目录属于用户环境配置，保存模型设置时原样保留
        skills_section = self._read_skills_section()
        if skills_section:
            parser[SKILLS_SECTION] = skills_section
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("w", encoding="utf-8") as handle:
                parser.write(handle)
        except OSError as exc:
            raise ConfigError(ErrorCode.CONFIG_INVALID, "无法写入配置文件：%s" % exc) from exc
        return AppConfig(
            **values,
            search_api_key=search_section.get(SEARCH_KEY, ""),
            search_endpoint=search_section.get(SEARCH_ENDPOINT_KEY, "") or SEARCH_ENDPOINT,
            skill_roots=tuple(
                split_skill_roots(skills_section.get(SKILLS_ROOTS_KEY, ""))
            ),
            max_tool_rounds=int(
                self._read_optional_llm_values().get(
                    "max_tool_rounds", MAX_TOOL_ROUNDS
                )
            ),
            history_turns=int(
                self._read_optional_llm_values().get("history_turns", HISTORY_TURNS)
            ),
            max_tokens=int(
                self._read_optional_llm_values().get("max_tokens", MAX_TOKENS)
            ),
        )

    def _read_search_section(self) -> dict[str, str]:
        """读取已有的 ``[search]`` 段；文件损坏时按「没有」处理，不阻塞保存。"""
        return self._read_section(SEARCH_SECTION)

    def _read_section(self, section: str) -> dict[str, str]:
        """读取某个段的全部非空键值；文件缺失或损坏时返回空字典。"""
        if not self._path.is_file():
            return {}
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(self._path, encoding="utf-8")
        except (configparser.Error, UnicodeDecodeError, OSError):
            return {}
        if not parser.has_section(section):
            return {}
        return {key: value for key, value in parser.items(section) if value.strip()}

    def _read_skills_section(self) -> dict[str, str]:
        """读取已有的 ``[skills]`` 段；缺文件或损坏时按「没有」处理。"""
        return self._read_section(SKILLS_SECTION)

    def _read_optional_llm_values(self) -> dict[str, str]:
        """读取 ``[llm]`` 里的可选高级设置，保存时原样写回。"""
        if not self._path.is_file():
            return {}
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read(self._path, encoding="utf-8")
        except (configparser.Error, UnicodeDecodeError, OSError):
            return {}
        if not parser.has_section(SECTION):
            return {}
        result: dict[str, str] = {}
        for key in OPTIONAL_INT_KEYS:
            raw = parser.get(SECTION, key, fallback="").strip()
            if raw:
                result[key] = str(_parse_positive_int(key, raw))
        return result


def _parse_positive_int(key: str, raw: str) -> int:
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(
            ErrorCode.CONFIG_INVALID,
            "配置项“%s”必须是整数" % key,
        ) from None
    if value <= 0:
        raise ConfigError(
            ErrorCode.CONFIG_INVALID,
            "配置项“%s”必须是正整数" % key,
        )
    return value


def _optional_int(parser: configparser.ConfigParser, key: str, default: int) -> int:
    raw = parser.get(SECTION, key, fallback="").strip()
    if not raw:
        return default
    return _parse_positive_int(key, raw)