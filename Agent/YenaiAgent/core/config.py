"""配置读取与保存。

配置是运行数据，不是界面交互：本模块不读取终端输入，也不打印，
缺失配置时由界面层负责引导用户填写。

第十二次课起所有可调参数都从 config.ini 读取，缺省值仍放在
core.constants：文件里没写的键自动用默认值，因此老配置文件不需要迁移。
分段含义：[llm] 模型参数、[context] 上下文与压缩、[session] 会话日志与 AGENTS.md、
[tools] 搜索/抓取/命令行、[search] 百度千帆密钥、[mcp] MCP 超时、[skills] 技能根目录。
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path

from .constants import (
    AGENTS_MD_FILENAME,
    AGENTS_MD_MAX_CHARS,
    CLI_MAX_OUTPUT,
    CLI_MAX_TIMEOUT,
    CLI_TIMEOUT,
    COMPACT_MAX_TOKENS,
    COMPACT_TARGET_TOKENS,
    COMPACT_TIMEOUT,
    CONTEXT_ARCHIVE_DIR,
    CONTEXT_WARN_RATIO,
    DEFAULT_CONTEXT_WINDOW,
    FETCH_MAX_CHARS,
    FETCH_TIMEOUT,
    HISTORY_TURNS,
    MAX_REPEATED_TOOL_CALLS,
    MAX_TOKENS,
    MAX_TOOL_ROUNDS,
    MCP_CALL_TIMEOUT,
    MCP_CONNECT_TIMEOUT,
    MCP_MAX_OUTPUT,
    REQUEST_TIMEOUT,
    SEARCH_ENDPOINT,
    SEARCH_TIMEOUT,
    SEARCH_TOP_K,
    SESSIONS_DIR,
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

CONTEXT_SECTION = "context"
SESSION_SECTION = "session"
TOOLS_SECTION = "tools"
SEARCH_SECTION = "search"
SEARCH_KEY = "baidu_qianfan_api_key"
SEARCH_ENDPOINT_KEY = "endpoint"
MCP_SECTION = "mcp"

# 首次运行生成的模板里的占位信息：明显是假的，用户一看就知道要改
MOCK_BASE_URL = "https://api.example.com/v1"
MOCK_API_KEY = "sk-mock-replace-me"
MOCK_MODEL_NAME = "mock-model"
TEMPLATE_HEADER = """# YenaiAgent 配置文件
# 修改后重启程序生效。没写的配置项一律使用内置默认值（注释里即默认值）。
# 首次运行自动生成：[llm] 里是占位信息，请替换成自己的接口地址 / 密钥 / 模型名。
"""


@dataclass(frozen=True, slots=True)
class AppConfig:
    """一次运行所需的全部配置。"""

    base_url: str
    api_key: str
    model_name: str
    # --- [llm]
    request_timeout: float = REQUEST_TIMEOUT
    max_tokens: int = MAX_TOKENS
    history_turns: int = HISTORY_TURNS
    max_tool_rounds: int = MAX_TOOL_ROUNDS
    max_repeated_tool_calls: int = MAX_REPEATED_TOOL_CALLS
    system_prompt: str = SYSTEM_PROMPT
    # --- [search]
    search_api_key: str = ""
    search_endpoint: str = SEARCH_ENDPOINT
    # --- [context]
    context_window: int = 0
    default_context_window: int = DEFAULT_CONTEXT_WINDOW
    warn_ratio: float = CONTEXT_WARN_RATIO
    compact_target_tokens: int = COMPACT_TARGET_TOKENS
    compact_max_tokens: int = COMPACT_MAX_TOKENS
    compact_timeout: float = COMPACT_TIMEOUT
    archive_dir: str = CONTEXT_ARCHIVE_DIR
    recall_max_snippets: int = 6
    recall_max_chars: int = 3600
    # --- [session]
    sessions_dir: str = SESSIONS_DIR
    history_dir: str = ""
    agents_md: str = AGENTS_MD_FILENAME
    agents_md_max_chars: int = AGENTS_MD_MAX_CHARS
    # --- [tools]
    search_timeout: float = SEARCH_TIMEOUT
    search_top_k: int = SEARCH_TOP_K
    fetch_timeout: float = FETCH_TIMEOUT
    fetch_max_chars: int = FETCH_MAX_CHARS
    cli_timeout: float = CLI_TIMEOUT
    cli_max_timeout: float = CLI_MAX_TIMEOUT
    cli_max_output: int = CLI_MAX_OUTPUT
    # --- [mcp]
    mcp_config: str = ""
    mcp_connect_timeout: float = MCP_CONNECT_TIMEOUT
    mcp_call_timeout: float = MCP_CALL_TIMEOUT
    mcp_max_output: int = MCP_MAX_OUTPUT
    # --- [skills]：额外的技能根目录，空表示用默认的 <启动目录>/.agents/skills
    skill_roots: tuple[str, ...] = ()


class ConfigStore:
    """config.ini 的读写门面。"""

    def __init__(self, path: Path | str = DEFAULT_CONFIG_PATH) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        """文件存在且 [llm] 三个必填项都有值。"""
        if not self._path.is_file():
            return False
        try:
            self.load()
        except AgentError:
            return False
        return True

    def ensure_template(self) -> bool:
        """缺少配置文件时写一份带 mock 信息的完整模板；已存在则不动。"""
        if self._path.is_file():
            return False
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(render_config_template(), encoding="utf-8")
        except OSError as exc:
            raise ConfigError(
                ErrorCode.CONFIG_INVALID, "无法写入配置文件：%s" % exc
            ) from exc
        return True

    def load(self) -> AppConfig:
        """读取配置；缺失或非法时抛 ConfigError。"""
        if not self._path.is_file():
            raise ConfigError(ErrorCode.CONFIG_MISSING, str(self._path))

        parser = self._read_parser()
        if not parser.has_section(SECTION):
            raise ConfigError(ErrorCode.CONFIG_INVALID, "缺少 [llm] 配置段")

        required = {}
        for key in REQUIRED_KEYS:
            value = _raw(parser, SECTION, key)
            if not value:
                raise ConfigError(
                    ErrorCode.CONFIG_INVALID,
                    "配置项“%s”为空" % KEY_LABELS[key],
                )
            required[key] = value

        skill_roots: tuple[str, ...] = ()
        if parser.has_section(SKILLS_SECTION):
            skill_roots = tuple(
                split_skill_roots(_raw(parser, SKILLS_SECTION, SKILLS_ROOTS_KEY))
            )

        # 上下文窗口：新版写在 [context] window，老文件写在 [llm] context_window
        if _raw(parser, CONTEXT_SECTION, "window"):
            window = _int(parser, CONTEXT_SECTION, "window", 0, allow_zero=True)
        else:
            window = _int(parser, SECTION, "context_window", 0, allow_zero=True)

        return AppConfig(
            **required,
            request_timeout=_number(parser, SECTION, "request_timeout", REQUEST_TIMEOUT),
            max_tokens=_int(parser, SECTION, "max_tokens", MAX_TOKENS),
            history_turns=_int(parser, SECTION, "history_turns", HISTORY_TURNS),
            max_tool_rounds=_int(parser, SECTION, "max_tool_rounds", MAX_TOOL_ROUNDS),
            max_repeated_tool_calls=_int(
                parser, SECTION, "max_repeated_tool_calls", MAX_REPEATED_TOOL_CALLS
            ),
            system_prompt=_raw(parser, SECTION, "system_prompt") or SYSTEM_PROMPT,
            search_api_key=_raw(parser, SEARCH_SECTION, SEARCH_KEY),
            search_endpoint=(
                _raw(parser, SEARCH_SECTION, SEARCH_ENDPOINT_KEY) or SEARCH_ENDPOINT
            ),
            context_window=window,
            default_context_window=_int(
                parser, CONTEXT_SECTION, "default_window", DEFAULT_CONTEXT_WINDOW
            ),
            warn_ratio=_ratio(parser, CONTEXT_SECTION, "warn_ratio", CONTEXT_WARN_RATIO),
            compact_target_tokens=_int(
                parser, CONTEXT_SECTION, "compact_target_tokens", COMPACT_TARGET_TOKENS
            ),
            compact_max_tokens=_int(
                parser, CONTEXT_SECTION, "compact_max_tokens", COMPACT_MAX_TOKENS
            ),
            compact_timeout=_number(
                parser, CONTEXT_SECTION, "compact_timeout", COMPACT_TIMEOUT
            ),
            archive_dir=(
                _raw(parser, CONTEXT_SECTION, "archive_dir") or CONTEXT_ARCHIVE_DIR
            ),
            recall_max_snippets=_int(parser, CONTEXT_SECTION, "recall_max_snippets", 6),
            recall_max_chars=_int(parser, CONTEXT_SECTION, "recall_max_chars", 3600),
            sessions_dir=_raw(parser, SESSION_SECTION, "dir") or SESSIONS_DIR,
            history_dir=_raw(parser, SESSION_SECTION, "history_dir"),
            agents_md=_raw(parser, SESSION_SECTION, "agents_md") or AGENTS_MD_FILENAME,
            agents_md_max_chars=_int(
                parser, SESSION_SECTION, "agents_md_max_chars", AGENTS_MD_MAX_CHARS
            ),
            search_timeout=_number(parser, TOOLS_SECTION, "search_timeout", SEARCH_TIMEOUT),
            search_top_k=_int(parser, TOOLS_SECTION, "search_top_k", SEARCH_TOP_K),
            fetch_timeout=_number(parser, TOOLS_SECTION, "fetch_timeout", FETCH_TIMEOUT),
            fetch_max_chars=_int(parser, TOOLS_SECTION, "fetch_max_chars", FETCH_MAX_CHARS),
            cli_timeout=_number(parser, TOOLS_SECTION, "cli_timeout", CLI_TIMEOUT),
            cli_max_timeout=_number(
                parser, TOOLS_SECTION, "cli_max_timeout", CLI_MAX_TIMEOUT
            ),
            cli_max_output=_int(parser, TOOLS_SECTION, "cli_max_output", CLI_MAX_OUTPUT),
            mcp_config=_raw(parser, MCP_SECTION, "config"),
            mcp_connect_timeout=_number(
                parser, MCP_SECTION, "connect_timeout", MCP_CONNECT_TIMEOUT
            ),
            mcp_call_timeout=_number(
                parser, MCP_SECTION, "call_timeout", MCP_CALL_TIMEOUT
            ),
            mcp_max_output=_int(parser, MCP_SECTION, "max_output", MCP_MAX_OUTPUT),
            skill_roots=skill_roots,
        )

    def save(self, base_url: str, api_key: str, model_name: str) -> AppConfig:
        """写入配置文件并返回读回后的配置。

        界面上只编辑 [llm] 的三项，其余段（含用户自己加的键）原样保留，
        避免改一次模型就把别的配置洗掉。
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

        parser = self._read_parser()
        if not parser.has_section(SECTION):
            parser.add_section(SECTION)
        for key, value in values.items():
            parser.set(SECTION, key, value)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("w", encoding="utf-8") as handle:
                handle.write("# YenaiAgent 配置（程序保存；原有注释会丢）\n")
                parser.write(handle)
        except OSError as exc:
            raise ConfigError(
                ErrorCode.CONFIG_INVALID, "无法写入配置文件：%s" % exc
            ) from exc
        return self.load()

    def _read_parser(self) -> configparser.ConfigParser:
        """读回整份配置用于改写；文件缺失或损坏时给一个空解析器。

        interpolation=None：路径里的 %VAR% 不能被当成插值语法。
        """
        parser = configparser.ConfigParser(interpolation=None)
        if not self._path.is_file():
            return parser
        try:
            parser.read(self._path, encoding="utf-8")
        except (configparser.Error, UnicodeDecodeError, OSError):
            return configparser.ConfigParser(interpolation=None)
        return parser


def render_config_template() -> str:
    """首运行生成的完整模板：所有段的键都列出来，注释里标默认值。"""
    parts = [TEMPLATE_HEADER, "", "[llm]"]
    parts += [
        "# 兼容 OpenAI 接口的地址",
        "base_url = %s" % MOCK_BASE_URL,
        "# API 密钥（占位，必须替换）",
        "api_key = %s" % MOCK_API_KEY,
        "# 模型名称（占位，必须替换）",
        "model_name = %s" % MOCK_MODEL_NAME,
        "# 单次请求超时（秒）",
        "request_timeout = %g" % REQUEST_TIMEOUT,
        "# 单次回复的输出上限（含 Function Calling 的参数）",
        "max_tokens = %d" % MAX_TOKENS,
        "# 保留的上下文轮数：每轮 = 一次提问 + 一次回答",
        "history_turns = %d" % HISTORY_TURNS,
        "# 单轮内允许的连续工具调用轮数",
        "max_tool_rounds = %d" % MAX_TOOL_ROUNDS,
        "# 同一工具 + 同一组参数连续调用多少次就判定为原地打转",
        "max_repeated_tool_calls = %d" % MAX_REPEATED_TOOL_CALLS,
        "# System Prompt",
        "system_prompt = %s" % SYSTEM_PROMPT,
        "",
        "[context]",
        "# 模型上下文窗口（token）；0 = 自动探测，探测不到按 default_window 并标注「默认」",
        "window = 0",
        "default_window = %d" % DEFAULT_CONTEXT_WINDOW,
        "# 达到窗口的这个比例就警告并暂停普通输入，等待 /compact",
        "warn_ratio = %g" % CONTEXT_WARN_RATIO,
        "# 压缩摘要目标长度、压缩请求自身的输出上限与超时（秒）",
        "compact_target_tokens = %d" % COMPACT_TARGET_TOKENS,
        "compact_max_tokens = %d" % COMPACT_MAX_TOKENS,
        "compact_timeout = %g" % COMPACT_TIMEOUT,
        "# 压缩前原始上下文的归档目录（相对项目根）",
        "archive_dir = %s" % CONTEXT_ARCHIVE_DIR,
        "# recallContext 单次检索返回的片段数与总字符上限",
        "recall_max_snippets = 6",
        "recall_max_chars = 3600",
        "",
        "[session]",
        "# 会话事件日志目录（/new、/resume、/save 使用）",
        "dir = %s" % SESSIONS_DIR,
        "# 旧版 Markdown 历史目录；留空表示程序目录下的 chat_history",
        "history_dir =",
        "# 项目约定文件：存在时在会话首次加载注入一次，之后随历史复用",
        "agents_md = %s" % AGENTS_MD_FILENAME,
        "agents_md_max_chars = %d" % AGENTS_MD_MAX_CHARS,
        "",
        "[tools]",
        "# 联网搜索（百度千帆智能搜索）与网页抓取",
        "search_timeout = %g" % SEARCH_TIMEOUT,
        "search_top_k = %d" % SEARCH_TOP_K,
        "fetch_timeout = %g" % FETCH_TIMEOUT,
        "fetch_max_chars = %d" % FETCH_MAX_CHARS,
        "# 命令行工具：单次超时、允许的最大超时、单路输出上限",
        "cli_timeout = %g" % CLI_TIMEOUT,
        "cli_max_timeout = %g" % CLI_MAX_TIMEOUT,
        "cli_max_output = %d" % CLI_MAX_OUTPUT,
        "",
        "[search]",
        "# 百度千帆 API Key（留给 search 工具；没有就留空）",
        "baidu_qianfan_api_key =",
        "# 接口地址；留空用默认值",
        "endpoint =",
        "",
        "[mcp]",
        "# MCP 配置文件路径；留空 = 技能目录下的 .mcp.json（缺失时自动生成模板）",
        "config =",
        "connect_timeout = %g" % MCP_CONNECT_TIMEOUT,
        "call_timeout = %g" % MCP_CALL_TIMEOUT,
        "max_output = %d" % MCP_MAX_OUTPUT,
        "",
        "[skills]",
        "# 技能扫描根目录（分号分隔）；留空 = <启动目录>/.agents/skills",
        "roots =",
    ]
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------- 解析辅助


def _raw(parser: configparser.ConfigParser, section: str, key: str) -> str:
    if not parser.has_section(section):
        return ""
    return parser.get(section, key, fallback="").strip()


def _int(
    parser: configparser.ConfigParser,
    section: str,
    key: str,
    default: int,
    *,
    allow_zero: bool = False,
) -> int:
    raw = _raw(parser, section, key)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(
            ErrorCode.CONFIG_INVALID, "配置项“%s”必须是整数" % key
        ) from None
    if value < 0 or (value == 0 and not allow_zero):
        raise ConfigError(
            ErrorCode.CONFIG_INVALID,
            "配置项“%s”必须是%s整数" % (key, "非负" if allow_zero else "正"),
        )
    return value


def _number(
    parser: configparser.ConfigParser,
    section: str,
    key: str,
    default: float,
) -> float:
    raw = _raw(parser, section, key)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(
            ErrorCode.CONFIG_INVALID, "配置项“%s”必须是数字" % key
        ) from None
    if value <= 0:
        raise ConfigError(
            ErrorCode.CONFIG_INVALID, "配置项“%s”必须是正数" % key
        )
    return value


def _ratio(
    parser: configparser.ConfigParser, section: str, key: str, default: float
) -> float:
    value = _number(parser, section, key, default)
    if value > 1:
        raise ConfigError(
            ErrorCode.CONFIG_INVALID, "配置项“%s”必须在 0 到 1 之间" % key
        )
    return value
