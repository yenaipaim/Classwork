"""RunCli 工具：以参数列表方式执行本地命令行程序。

调用方式固定为 ``[command, *args]`` 且 ``shell=False``，模型给出的参数只会
作为单个参数传给程序，不会经过 Shell 解析。退出码、stdout、stderr 原样交回
模型；输出过长会截断并标注，执行超时会终止进程并说明。

注意：该工具以运行本程序的用户权限执行命令，没有白名单或审批，仅建议在
受控的教学环境中使用。
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from typing import Any, Callable

from ..constants import CLI_MAX_OUTPUT, CLI_MAX_TIMEOUT, CLI_TIMEOUT
from ..errors import ToolError
from .spec import ToolSpec

# (argv, timeout, cwd) -> 带 returncode/stdout/stderr 的结果；测试里可替换
Runner = Callable[[list[str], float, str | None], Any]

# 命令展示时最多保留的字符数，避免把超长参数整个写进结果
DISPLAY_LIMIT = 200


class CommandRunner:
    """执行命令行程序，并把结果整理成模型容易判断的字典。"""

    def __init__(
        self,
        *,
        cwd: str | None = None,
        timeout: float = CLI_TIMEOUT,
        max_output: int = CLI_MAX_OUTPUT,
        runner: Runner | None = None,
    ) -> None:
        self._cwd = cwd
        self._timeout = float(timeout)
        self._max_output = int(max_output)
        self._runner = runner or _run_process

    def run(
        self, command: str, args: Sequence[Any] | None = None, timeout: Any = None
    ) -> dict[str, Any]:
        """执行一次命令；正常结束返回 ok 与输出，异常也返回结构化结果。"""
        argv = _build_argv(command, args)
        limit = _clamp_timeout(timeout if timeout is not None else self._timeout)
        display = _display(argv)

        try:
            completed = self._runner(argv, limit, self._cwd)
        except FileNotFoundError:
            return _failure(
                display,
                "找不到程序：%s（请确认已安装并加入 PATH，或传入完整路径）" % command,
            )
        except subprocess.TimeoutExpired as exc:
            payload = _result(
                display,
                None,
                _decode(exc.stdout),
                _decode(exc.stderr),
                self._max_output,
            )
            payload["ok"] = False
            payload["timeout"] = True
            payload["error"] = "命令执行超时（超过 %g 秒），进程已终止" % limit
            return payload
        except OSError as exc:
            return _failure(display, "无法启动程序：%s" % exc)

        code = int(getattr(completed, "returncode", 0) or 0)
        payload = _result(
            display,
            code,
            _decode(getattr(completed, "stdout", b"")),
            _decode(getattr(completed, "stderr", b"")),
            self._max_output,
        )
        payload["ok"] = code == 0
        return payload


def build_cli_tool(runner: CommandRunner) -> ToolSpec:
    """把命令执行器包成一个函数调用工具。"""

    def handler(
        command: str, args: Sequence[Any] | None = None, timeout: Any = None
    ) -> dict[str, Any]:
        return runner.run(command, args, timeout)

    return ToolSpec(
        name="RunCli",
        description=(
            "在本机执行命令行程序：传入程序名 command 与参数列表 args，"
            "返回退出码、标准输出 stdout 和标准错误 stderr。"
            "参数逐个传递、不经过 Shell；输出过长会截断，超时会终止进程。"
            "以当前用户权限运行，仅用于受控教学环境。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "程序名或可执行文件路径，例如 python、git、curl",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": '参数列表，例如 ["--version"]、"["status", "--short"]',
                },
                "timeout": {
                    "type": "number",
                    "description": "超时秒数，默认 30，范围 1–120",
                    "minimum": 1,
                    "maximum": CLI_MAX_TIMEOUT,
                },
            },
            "required": ["command"],
        },
        handler=handler,
    )


def _run_process(argv: list[str], timeout: float, cwd: str | None) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        shell=False,
        capture_output=True,
        timeout=timeout,
        cwd=cwd,
        check=False,
    )


def _build_argv(command: Any, args: Sequence[Any] | None) -> list[str]:
    if not isinstance(command, str) or not command.strip():
        raise ToolError("参数错误：command 必须是非空的程序名")

    name = command.strip()
    if " " in name and not _looks_like_path(name):
        raise ToolError(
            "参数错误：command 只能是程序名或路径，"
            "参数请放进 args 列表，例如 command=\"git\"、args=[\"status\"]"
        )

    if args is None:
        items: list[Any] = []
    elif isinstance(args, (str, bytes)) or not isinstance(args, Sequence):
        raise ToolError("参数错误：args 必须是字符串数组")
    else:
        items = list(args)

    argv = [name] + [_arg_text(item) for item in items]
    return argv


def _arg_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    raise ToolError("参数错误：args 中的每一项都必须是字符串")


def _looks_like_path(command: str) -> bool:
    return any(sep in command for sep in ("/", "\\")) or (
        len(command) > 1 and command[1] == ":"
    )


def _clamp_timeout(value: Any) -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return CLI_TIMEOUT
    if seconds <= 0 or seconds != seconds:  # 含 NaN
        return CLI_TIMEOUT
    return min(float(CLI_MAX_TIMEOUT), max(1.0, seconds))


def _result(
    display: str,
    code: int | None,
    stdout: str,
    stderr: str,
    max_output: int,
) -> dict[str, Any]:
    out, out_cut = _clip(stdout, max_output)
    err, err_cut = _clip(stderr, max_output)
    return {
        "command": display,
        "exit_code": code,
        "stdout": out,
        "stdout_truncated": out_cut,
        "stderr": err,
        "stderr_truncated": err_cut,
    }


def _failure(display: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "command": display,
        "exit_code": None,
        "stdout": "",
        "stdout_truncated": False,
        "stderr": "",
        "stderr_truncated": False,
        "error": message,
    }


def _clip(text: str, limit: int) -> tuple[str, bool]:
    """超长输出保留头尾：头部留有 3/4，尾部常放错误信息，截断处写明省略量。"""
    if len(text) <= limit:
        return text, False
    head = max(1, limit * 3 // 4)
    tail = max(0, limit - head)
    omitted = len(text) - head - tail
    clipped = text[:head] + "\n…（已截断 %d 字符）…\n" % omitted
    if tail:
        clipped += text[-tail:]
    return clipped, True


def _display(argv: list[str]) -> str:
    text = " ".join(_quote(item) for item in argv)
    if len(text) <= DISPLAY_LIMIT:
        return text
    return text[:DISPLAY_LIMIT] + "…"


def _quote(value: str) -> str:
    return '"%s"' % value if " " in value else value


def _decode(raw: bytes | None) -> str:
    if not raw:
        return ""
    if isinstance(raw, str):  # 某些实现会直接返回文本
        return raw
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")