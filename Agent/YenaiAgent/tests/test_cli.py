"""RunCli 工具：参数拼装、超时、截断与结果结构。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.errors import ToolError
from core.factory import build_registry
from core.tools.cli import CommandRunner

PYTHON = sys.executable


def test_runs_program_and_reports_stdout(tmp_path: Path) -> None:
    runner = CommandRunner(cwd=str(tmp_path))

    result = runner.run(PYTHON, ["-c", "print('你好')"])

    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert "你好" in result["stdout"]
    assert result["stdout_truncated"] is False


def test_working_directory_is_injected(tmp_path: Path) -> None:
    runner = CommandRunner(cwd=str(tmp_path))

    result = runner.run(PYTHON, ["-c", "import os; print(os.getcwd())"])

    assert Path(result["stdout"].strip()) == tmp_path


def test_nonzero_exit_is_reported() -> None:
    runner = CommandRunner()

    result = runner.run(PYTHON, ["-c", "import sys; sys.exit(3)"])

    assert result["ok"] is False
    assert result["exit_code"] == 3


def test_stderr_is_captured() -> None:
    runner = CommandRunner()

    result = runner.run(PYTHON, ["-c", "import sys; sys.stderr.write('boom')"])

    assert result["ok"] is True
    assert "boom" in result["stderr"]


def test_args_are_passed_literally_without_shell() -> None:
    runner = CommandRunner()

    result = runner.run(
        PYTHON,
        ["-c", "import sys; print(sys.argv[1])", "a; echo hacked && whoami"],
    )

    assert result["ok"] is True
    assert result["stdout"].strip() == "a; echo hacked && whoami"
    assert "hacked" in result["stdout"]


def test_long_output_is_truncated_with_marker() -> None:
    runner = CommandRunner(max_output=1000)

    result = runner.run(PYTHON, ["-c", "print('x' * 20000)"])

    assert result["stdout_truncated"] is True
    assert len(result["stdout"]) < 1200
    assert "已截断" in result["stdout"]


def test_timeout_terminates_process() -> None:
    runner = CommandRunner()

    result = runner.run(PYTHON, ["-c", "import time; time.sleep(5)"], timeout=0.5)

    assert result["ok"] is False
    assert result["timeout"] is True
    assert "超时" in result["error"]


def test_missing_program_is_reported() -> None:
    runner = CommandRunner()

    result = runner.run("definitely-not-a-real-program-xyz")

    assert result["ok"] is False
    assert result["exit_code"] is None
    assert "找不到程序" in result["error"]


def test_command_with_spaces_is_rejected() -> None:
    runner = CommandRunner()

    with pytest.raises(ToolError, match="args 列表"):
        runner.run("git status")


def test_args_must_be_a_list() -> None:
    runner = CommandRunner()

    with pytest.raises(ToolError, match="args 必须是字符串数组"):
        runner.run(PYTHON, "--version")  # type: ignore[arg-type]


def test_args_items_must_be_scalars() -> None:
    runner = CommandRunner()

    with pytest.raises(ToolError, match="每一项都必须是字符串"):
        runner.run(PYTHON, [{"a": 1}])  # type: ignore[list-item]


def test_gb18030_output_is_decoded() -> None:
    def fake_runner(argv, timeout, cwd):
        return subprocess.CompletedProcess(
            argv, 0, stdout="中文输出".encode("gb18030"), stderr=b""
        )

    result = CommandRunner(runner=fake_runner).run("cmd")

    assert result["stdout"] == "中文输出"


def test_timeout_keeps_partial_output() -> None:
    def fake_runner(argv, timeout, cwd):
        raise subprocess.TimeoutExpired(argv, timeout, output=b"partial", stderr=b"oops")

    result = CommandRunner(runner=fake_runner).run("cmd", timeout=1)

    assert result["ok"] is False
    assert result["timeout"] is True
    assert result["stdout"] == "partial"
    assert result["stderr"] == "oops"


def test_registered_between_fetch_and_list_tools(workspace: Path) -> None:
    names = build_registry(workspace).names()

    assert names.index("fetchWeb") < names.index("RunCli") < names.index("list_tools")


def test_registry_reports_cli_errors_as_failed_outcome(workspace: Path) -> None:
    registry = build_registry(workspace)

    missing = registry.execute("RunCli", json.dumps({"command": ""}))
    assert missing.ok is False
    assert "command" in json.loads(missing.output)["error"]

    bad_args = registry.execute(
        "RunCli", json.dumps({"command": "git", "args": "--version"})
    )
    assert bad_args.ok is False
    assert "args 必须是字符串数组" in json.loads(bad_args.output)["error"]