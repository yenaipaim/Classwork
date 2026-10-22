"""存档格式测试。"""

from __future__ import annotations

from pathlib import Path

from core.events import ToolCallRecord
from core.transcript import Transcript


def test_lazy_creation_and_legacy_format(tmp_path: Path) -> None:
    transcript = Transcript(tmp_path, "test-model")
    assert transcript.path is None

    transcript.save_turn(
        "几点了",
        "现在十点",
        [ToolCallRecord("get_date", "{}", "2026-01-01 10:00:00 星期四（UTC+0800）", True, "10:00:00")],
    )

    path = transcript.path
    assert path is not None and path.is_file()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# 模型：test-model\n# 开始：")
    assert "\n[工具] get_date  10:00:00\n参数：{}\n结果：2026-01-01 10:00:00 星期四（UTC+0800）\n" in text
    assert text.endswith("\n[回复]\n现在十点\n")
    assert "用户\n几点了\n" in text


def test_second_turn_appends_to_same_file(tmp_path: Path) -> None:
    transcript = Transcript(tmp_path, "m")
    transcript.save_turn("q1", "a1")
    first = transcript.path
    transcript.save_turn("q2", "a2")

    assert transcript.path == first
    text = first.read_text(encoding="utf-8")
    assert text.count("# 模型：") == 1
    assert text.count("[回复]") == 2
    assert "a1" in text and "a2" in text


def test_reset_switches_to_a_new_file(tmp_path: Path) -> None:
    transcript = Transcript(tmp_path, "m")
    transcript.save_turn("q1", "a1")
    first = transcript.path
    first_text = first.read_text(encoding="utf-8")

    transcript.reset()
    assert transcript.path is None
    transcript.save_turn("q2", "a2")

    second = transcript.path
    assert second is not None and second != first
    assert "q2" in second.read_text(encoding="utf-8")
    assert first.read_text(encoding="utf-8") == first_text


def test_write_failure_is_swallowed(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")

    transcript = Transcript(blocker / "nested", "m")
    transcript.save_turn("q", "a")

    assert transcript.path is None