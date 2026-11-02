"""读取 `.mcp.json`，把每家 MCP Server 的配置校验成不可变对象。

配置格式与 Claude Code 等主流 MCP 客户端保持一致::

    {
      "mcpServers": {
        "PeiHospitalMCP": {
          "type": "streamable_http",
          "url": "http://127.0.0.1:9000/mcp"
        }
      }
    }

`type` 可以省略：有 `url` 时按 Streamable HTTP（地址以 `/sse` 结尾时按 SSE），
有 `command` 时按 stdio。一家 Server 写错只会进 :attr:`McpConfig.issues`，
不影响其余 Server 连接；整份配置缺失则等于没有 MCP 工具。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from ..constants import (
    MCP_CALL_TIMEOUT,
    MCP_CONFIG_FILENAME,
    MCP_CONNECT_TIMEOUT,
    MCP_MAX_OUTPUT,
)
from ..paths import PACKAGE_ROOT

#: 覆盖配置文件路径的环境变量；设为 off/none/disabled 可整体关闭 MCP。
ENV_MCP_CONFIG = "YENAI_MCP_CONFIG"

TRANSPORT_STDIO = "stdio"
TRANSPORT_HTTP = "streamable_http"
TRANSPORT_SSE = "sse"

_TRANSPORTS = {
    "stdio": TRANSPORT_STDIO,
    "streamable_http": TRANSPORT_HTTP,
    "streamable-http": TRANSPORT_HTTP,
    "streamablehttp": TRANSPORT_HTTP,
    "http": TRANSPORT_HTTP,
    "sse": TRANSPORT_SSE,
}
_DISABLED_VALUES = {"off", "none", "disabled", "0"}
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True, slots=True)
class McpConfigIssue:
    """一份配置里某家 Server 的问题；server 为空表示整份文件的问题。"""

    server: str
    message: str

    def __str__(self) -> str:
        if self.server:
            return "%s：%s" % (self.server, self.message)
        return self.message


@dataclass(frozen=True, slots=True)
class McpServerConfig:
    """一家 MCP Server 的连接参数。"""

    name: str
    transport: str
    enabled: bool = True
    command: str = ""
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    cwd: str = ""
    url: str = ""
    headers: Mapping[str, str] = field(default_factory=dict)
    connect_timeout: float = MCP_CONNECT_TIMEOUT
    call_timeout: float = MCP_CALL_TIMEOUT
    max_output: int = MCP_MAX_OUTPUT

    @property
    def kind(self) -> str:
        """给界面看的传输方式归类：stdio / http。"""
        return "stdio" if self.transport == TRANSPORT_STDIO else "http"

    @property
    def target(self) -> str:
        """一行描述连接目标，用于日志与 /mcp。"""
        if self.transport == TRANSPORT_STDIO:
            return " ".join([self.command, *self.args]).strip()
        return self.url


@dataclass(frozen=True, slots=True)
class McpConfig:
    """一份 `.mcp.json` 的解析结果。"""

    path: Path | None = None
    servers: tuple[McpServerConfig, ...] = ()
    issues: tuple[McpConfigIssue, ...] = ()

    @property
    def configured(self) -> bool:
        """是否读到过任何有效配置（含错误）：界面据此决定要不要提示。"""
        return bool(self.servers or self.issues)

    @property
    def enabled_servers(self) -> tuple[McpServerConfig, ...]:
        return tuple(server for server in self.servers if server.enabled)

    def server(self, name: str) -> McpServerConfig | None:
        for server in self.servers:
            if server.name == name:
                return server
        return None


class _ServerError(ValueError):
    """单家 Server 的配置问题：只跳过它，不拖垮整份配置。"""


def load_mcp_config(path: Path | str) -> McpConfig:
    """读取并解析指定文件；文件不存在或格式错误都返回带 issues 的结果。"""
    path = Path(path).expanduser()
    if not path.is_file():
        return McpConfig(
            path=path,
            issues=(McpConfigIssue("", "MCP 配置文件不存在：%s" % path),),
        )
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return McpConfig(
            path=path,
            issues=(McpConfigIssue("", "读取 MCP 配置文件失败：%s" % exc),),
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return McpConfig(
            path=path,
            issues=(
                McpConfigIssue(
                    "",
                    "MCP 配置 JSON 解析失败（第 %d 行第 %d 列）：%s"
                    % (exc.lineno, exc.colno, exc.msg),
                ),
            ),
        )
    if not isinstance(payload, dict):
        return McpConfig(
            path=path,
            issues=(McpConfigIssue("", "MCP 配置顶层必须是 JSON 对象"),),
        )
    # 兼容两种写法：Claude Code 用 mcpServers，部分客户端用 servers
    section = payload.get("mcpServers", payload.get("servers"))
    if section is None:
        return McpConfig(path=path)
    if not isinstance(section, dict):
        return McpConfig(
            path=path,
            issues=(McpConfigIssue("", "mcpServers 必须是 JSON 对象"),),
        )

    servers: list[McpServerConfig] = []
    issues: list[McpConfigIssue] = []
    base_dir = path.parent
    for raw_name, entry in section.items():
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if not name:
            issues.append(McpConfigIssue(str(raw_name), "Server 名称不能为空"))
            continue
        if not isinstance(entry, Mapping):
            issues.append(McpConfigIssue(name, "配置必须是 JSON 对象"))
            continue
        try:
            enabled = _flag(entry, "enabled", True) and not _flag(
                entry, "disabled", False
            )
        except _ServerError as exc:
            issues.append(McpConfigIssue(name, str(exc)))
            continue
        if not enabled:
            # 被禁用的 Server 允许保留占位配置，不校验连接参数
            servers.append(McpServerConfig(name=name, transport="", enabled=False))
            continue
        try:
            servers.append(_parse_server(name, entry, base_dir))
        except _ServerError as exc:
            issues.append(McpConfigIssue(name, str(exc)))
    return McpConfig(path=path, servers=tuple(servers), issues=tuple(issues))


def discover_mcp_config(project_root: Path | str | None = None) -> McpConfig:
    """按优先级找到 `.mcp.json`：环境变量 → 项目根目录 → 程序目录 → 仓库根目录。

    `YENAI_MCP_CONFIG` 是显式覆盖（相对路径按项目根解析），设为 off 表示
    本次运行不启用 MCP——测试和演示都靠它避免去连真实服务。
    """
    override = os.environ.get(ENV_MCP_CONFIG)
    if override is not None:
        value = override.strip()
        if value.lower() in _DISABLED_VALUES or not value:
            return McpConfig()
        path = Path(os.path.expandvars(value)).expanduser()
        if not path.is_absolute():
            base = Path(project_root) if project_root is not None else Path.cwd()
            path = base / path
        return load_mcp_config(path)

    base = Path(project_root) if project_root is not None else Path.cwd()
    seen: set[Path] = set()
    for candidate in (
        base / MCP_CONFIG_FILENAME,
        PACKAGE_ROOT / MCP_CONFIG_FILENAME,
        # 从仓库根目录 `python Agent/YenaiAgent/main.py` 启动时也能读到
        PACKAGE_ROOT.parent.parent / MCP_CONFIG_FILENAME,
    ):
        try:
            key = candidate.resolve()
        except OSError:  # pragma: no cover - 极端路径问题
            key = candidate
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return load_mcp_config(candidate)
    return McpConfig()


def _parse_server(
    name: str, entry: Mapping[str, Any], base_dir: Path
) -> McpServerConfig:
    transport = _parse_transport(entry)
    connect_timeout = _number(
        entry, ("connect_timeout", "init_timeout"), MCP_CONNECT_TIMEOUT, maximum=600.0
    )
    call_timeout = _number(
        entry, ("timeout", "call_timeout"), MCP_CALL_TIMEOUT, maximum=3600.0
    )
    max_output = _integer(
        entry, "max_output", MCP_MAX_OUTPUT, minimum=1000, maximum=200000
    )

    if transport == TRANSPORT_STDIO:
        command = _expand(_required_text(entry, ("command",)), name)
        args = _string_list(entry.get("args"), "args")
        env = _string_map(entry.get("env"), "env", expand=True)
        cwd = ""
        if entry.get("cwd") is not None:
            cwd_text = _expand(_text(entry.get("cwd"), "cwd"), name)
            cwd_path = Path(cwd_text).expanduser()
            if not cwd_path.is_absolute():
                cwd_path = base_dir / cwd_path
            cwd = str(cwd_path)
        return McpServerConfig(
            name=name,
            transport=transport,
            command=command,
            args=args,
            env=env,
            cwd=cwd,
            connect_timeout=connect_timeout,
            call_timeout=call_timeout,
            max_output=max_output,
        )

    url = _expand(_required_text(entry, ("url",)), name)
    _validate_url(url)
    headers = _string_map(entry.get("headers"), "headers", expand=True)
    return McpServerConfig(
        name=name,
        transport=transport,
        url=url,
        headers=headers,
        connect_timeout=connect_timeout,
        call_timeout=call_timeout,
        max_output=max_output,
    )


def _parse_transport(entry: Mapping[str, Any]) -> str:
    raw = entry.get("type", entry.get("transport"))
    if raw is not None:
        if not isinstance(raw, str):
            raise _ServerError("type 必须是字符串")
        key = raw.strip().lower().replace(" ", "_")
        transport = _TRANSPORTS.get(key)
        if transport is None:
            raise _ServerError(
                "不支持的 MCP 传输方式：%s（可用：stdio、streamable_http、sse）" % raw
            )
        if transport == TRANSPORT_STDIO and entry.get("command") is None:
            raise _ServerError("stdio 方式缺少 command")
        if transport != TRANSPORT_STDIO and entry.get("url") is None:
            raise _ServerError("%s 方式缺少 url" % transport)
        return transport

    # 没写 type 就按字段推断：url 优先，其次 command
    url = entry.get("url")
    if url is not None:
        if isinstance(url, str) and urlsplit(url.strip()).path.rstrip("/").endswith(
            "/sse"
        ):
            return TRANSPORT_SSE
        return TRANSPORT_HTTP
    if entry.get("command") is not None:
        return TRANSPORT_STDIO
    raise _ServerError("缺少连接信息：stdio 需要 command，HTTP/SSE 需要 url")


def _validate_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise _ServerError("url 必须是 http:// 或 https:// 地址：%s" % url)


def _expand(text: str, server: str) -> str:
    """展开 `${VAR}`；缺变量时直接报错，避免带着半个地址去连接。"""

    def replace(match: re.Match[str]) -> str:
        variable = match.group(1)
        value = os.environ.get(variable)
        if value is None:
            raise _ServerError(
                "环境变量 %s 未设置（%s 的配置引用了它）" % (variable, server)
            )
        return value

    return _ENV_PATTERN.sub(replace, text)


def _required_text(entry: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        if entry.get(key) is None:
            continue
        value = entry.get(key)
        if not isinstance(value, str):
            raise _ServerError("%s 必须是字符串" % key)
        value = value.strip()
        if not value:
            raise _ServerError("%s 不能为空" % key)
        return value
    raise _ServerError("缺少必填字段：%s" % keys[0])


def _text(value: Any, key: str) -> str:
    if not isinstance(value, str):
        raise _ServerError("%s 必须是字符串" % key)
    return value.strip()


def _flag(entry: Mapping[str, Any], key: str, default: bool) -> bool:
    value = entry.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
    raise _ServerError("%s 必须是布尔值" % key)


def _number(
    entry: Mapping[str, Any],
    keys: tuple[str, ...],
    default: float,
    *,
    maximum: float,
) -> float:
    key = next((item for item in keys if entry.get(item) is not None), None)
    if key is None:
        return default
    value = entry[key]
    if isinstance(value, bool):
        raise _ServerError("%s 必须是数字（秒）" % key)
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            raise _ServerError("%s 必须是数字（秒）" % key) from None
    if not isinstance(value, (int, float)):
        raise _ServerError("%s 必须是数字（秒）" % key)
    if not 0 < float(value) <= maximum:
        raise _ServerError("%s 必须在 0–%g 秒之间" % (key, maximum))
    return float(value)


def _integer(
    entry: Mapping[str, Any],
    key: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = entry.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        raise _ServerError("%s 必须是整数" % key)
    if isinstance(value, str):
        try:
            value = int(value.strip())
        except ValueError:
            raise _ServerError("%s 必须是整数" % key) from None
    if not isinstance(value, int):
        raise _ServerError("%s 必须是整数" % key)
    if not minimum <= value <= maximum:
        raise _ServerError("%s 必须在 %d–%d 之间" % (key, minimum, maximum))
    return value


def _string_list(value: Any, key: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _ServerError("%s 必须是字符串数组" % key)
    result: list[str] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (str, int, float)):
            raise _ServerError("%s 的每一项都必须是字符串" % key)
        result.append(str(item))
    return tuple(result)


def _string_map(
    value: Any, key: str, *, expand: bool
) -> Mapping[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise _ServerError("%s 必须是 JSON 对象" % key)
    result: dict[str, str] = {}
    for item_key, item_value in value.items():
        if not isinstance(item_key, str) or not item_key.strip():
            raise _ServerError("%s 的键不能为空" % key)
        if isinstance(item_value, bool) or not isinstance(
            item_value, (str, int, float)
        ):
            raise _ServerError("%s.%s 必须是字符串" % (key, item_key))
        text = str(item_value)
        result[item_key.strip()] = _expand(text, key) if expand else text
    return result
