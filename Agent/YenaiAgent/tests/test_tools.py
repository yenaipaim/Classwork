"""工具层测试：注册表、内置工具、文件沙箱。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.errors import ToolError
from core.factory import build_registry
from core.tools.builtins import get_date, is_leap_year
from core.tools.files import FileToolbox

# ---------------------------------------------------------------- 内置工具


def test_get_date_contains_weekday_and_offset() -> None:
    text = get_date()
    assert "星期" in text
    assert "UTC" in text
    assert len(text) >= len("2026-01-01 00:00:00 星期一（UTC+0800）")


@pytest.mark.parametrize(
    ("year", "expected"),
    [(2024, "2024 年是闰年"), (2023, "2023 年不是闰年"), (1900, "1900 年不是闰年"), (2000, "2000 年是闰年")],
)
def test_is_leap_year(year: int, expected: str) -> None:
    assert is_leap_year(year) == expected


def test_is_leap_year_accepts_numeric_string() -> None:
    assert is_leap_year("2024") == "2024 年是闰年"


def test_is_leap_year_rejects_non_integer() -> None:
    with pytest.raises(ToolError):
        is_leap_year("abc")


# ---------------------------------------------------------------- 注册表


def test_registry_has_thirteen_tools_in_legacy_order(workspace: Path) -> None:
    registry = build_registry(workspace)
    assert registry.names() == [
        "get_date",
        "isLeapyear",
        "get_current_working_directory",
        "list_directory_contents",
        "get_file_type",
        "read_text_file",
        "create_file",
        "edit_text_file",
        "create_directory",
        "delete_directory",
        "delete_file",
        "rename_path",
        "list_tools",
    ]
    assert len(registry.schemas()) == 13
    assert registry.schemas()[0]["type"] == "function"


def test_list_tools_reports_all_tools(workspace: Path) -> None:
    registry = build_registry(workspace)
    outcome = registry.execute("list_tools", "{}")
    assert outcome.ok is True
    payload = json.loads(outcome.output)
    assert payload["count"] == 13
    assert {item["name"] for item in payload["tools"]} == set(registry.names())


def test_unknown_tool_and_bad_arguments(workspace: Path) -> None:
    registry = build_registry(workspace)

    unknown = registry.execute("nope", "{}")
    assert unknown.ok is False
    assert "未知工具" in unknown.output

    broken = registry.execute("isLeapyear", "{not json")
    assert broken.ok is False
    assert "JSON" in broken.output

    wrong_type = registry.execute("isLeapyear", '{"year": "abc"}')
    assert wrong_type.ok is False


def test_handler_exception_becomes_failure(workspace: Path) -> None:
    from core.tools.spec import ToolRegistry, ToolSpec

    def boom() -> str:
        raise RuntimeError("炸了")

    registry = ToolRegistry()
    registry.register(
        ToolSpec("boom", "总是失败", {"type": "object", "properties": {}}, boom)
    )
    outcome = registry.execute("boom", "{}")
    assert outcome.ok is False
    assert "炸了" in outcome.output


# ---------------------------------------------------------------- 文件沙箱


@pytest.fixture
def toolbox(workspace: Path) -> FileToolbox:
    return FileToolbox(workspace)


def test_file_tool_count(toolbox: FileToolbox) -> None:
    assert len(toolbox.specs()) == 10
    assert {spec.name for spec in toolbox.specs()} == {
        "get_current_working_directory",
        "list_directory_contents",
        "get_file_type",
        "read_text_file",
        "create_file",
        "edit_text_file",
        "create_directory",
        "delete_directory",
        "delete_file",
        "rename_path",
    }


def test_write_read_edit_roundtrip(toolbox: FileToolbox, workspace: Path) -> None:
    assert toolbox.create_file(".", "note.txt")["message"] == "文件已创建"
    toolbox.edit_text_file("note.txt", "第一行\n第二行")
    assert (workspace / "note.txt").read_text(encoding="utf-8") == "第一行\n第二行"

    payload = toolbox.read_text_file("note.txt")
    assert payload["content"] == "第一行\n第二行"
    assert payload["encoding"] == "utf-8"

    listing = toolbox.list_directory_contents(".")
    assert [entry["name"] for entry in listing["entries"]] == ["note.txt"]
    assert listing["entries"][0]["type"] == "file"


def test_gb18030_text_is_detected(toolbox: FileToolbox, workspace: Path) -> None:
    (workspace / "gb.txt").write_bytes("中文内容".encode("gb18030"))
    payload = toolbox.read_text_file("gb.txt")
    assert payload["content"] == "中文内容"
    assert payload["encoding"] in ("gb18030", "cp936", "gbk")


def test_binary_file_is_rejected(toolbox: FileToolbox, workspace: Path) -> None:
    (workspace / "data.txt").write_bytes(b"abc\x00def")
    with pytest.raises(ToolError) as excinfo:
        toolbox.read_text_file("data.txt")
    assert "二进制" in str(excinfo.value)


def test_path_traversal_is_blocked(toolbox: FileToolbox, workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(ToolError):
        toolbox.read_text_file("../outside.txt")
    with pytest.raises(ToolError):
        toolbox.read_text_file(str(outside))
    with pytest.raises(ToolError):
        toolbox.create_file(".", "../escape.txt")
    assert not (tmp_path / "escape.txt").exists()


def test_delete_and_rename_rules(toolbox: FileToolbox, workspace: Path) -> None:
    toolbox.create_directory("sub")
    toolbox.create_file("sub", "a.txt")
    toolbox.create_file("sub", "b.txt")

    with pytest.raises(ToolError):
        toolbox.rename_path("sub/a.txt", "b.txt")

    renamed = toolbox.rename_path("sub/a.txt", "c.txt")
    assert Path(renamed["new_path"]) == Path("sub/c.txt")
    assert (workspace / "sub" / "c.txt").is_file()

    assert toolbox.delete_file("sub/c.txt")["message"] == "文件已删除"
    assert toolbox.delete_directory("sub")["message"] == "目录已删除"

    with pytest.raises(ToolError):
        toolbox.delete_directory(".")
    with pytest.raises(ToolError):
        toolbox.rename_path(".", "new-root")


def test_get_file_type_reports_directory_and_text(toolbox: FileToolbox, workspace: Path) -> None:
    (workspace / "a.md").write_text("# hi", encoding="utf-8")
    assert toolbox.get_file_type(".")["type"] == "directory"
    payload = toolbox.get_file_type("a.md")
    assert payload["type"] == "file"
    assert payload["is_text"] is True
    assert payload["suffix"] == ".md"


def test_missing_paths_report_errors(toolbox: FileToolbox) -> None:
    with pytest.raises(ToolError):
        toolbox.read_text_file("absent.txt")
    with pytest.raises(ToolError):
        toolbox.list_directory_contents("absent")