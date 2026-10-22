"""分层约束测试：core 不能反向依赖任何界面技术。"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"

FORBIDDEN_IMPORT = re.compile(r"^\s*(?:from|import)\s+(textual|rich|tui)\b", re.MULTILINE)
UI_IMPORT = re.compile(r"^\s*(?:from|import)\s+(textual|rich)\b", re.MULTILINE)


def core_files() -> list[Path]:
    return sorted(CORE.rglob("*.py"))


def test_core_does_not_import_ui_libraries() -> None:
    offenders = [
        str(path.relative_to(ROOT))
        for path in core_files()
        if FORBIDDEN_IMPORT.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_core_has_no_process_level_io() -> None:
    offenders = []
    for path in core_files():
        text = path.read_text(encoding="utf-8")
        for needle in ("print(", "input(", "sys.exit"):
            if needle in text:
                offenders.append("%s: %s" % (path.relative_to(ROOT), needle))
    assert offenders == []


def test_core_imports_without_textual_installed() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import core, core.tools, core.llm, core.factory"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr


def test_tui_is_the_only_place_importing_textual() -> None:
    """界面技术的 import 只允许出现在 tui 包内。"""
    offenders = []
    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT)
        if relative.parts[0] in ("tests", "tui"):
            continue
        if UI_IMPORT.search(path.read_text(encoding="utf-8")):
            offenders.append(str(relative))
    assert offenders == []