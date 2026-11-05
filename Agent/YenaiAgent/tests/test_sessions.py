"""会话日志测试：事件追加、历史还原、列表、导出与非法编号。"""

from __future__ import annotations

import json

import pytest

from core.errors import AgentError, ErrorCode
from core.sessions import SessionInfo, SessionStore
from core.compaction import SUMMARY_ACK


def read_lines(path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_start_writes_header_and_returns_valid_id(tmp_path) -> None:
    """开新会话立刻落一个 header，编号能直接用来找文件。"""
    store = SessionStore(tmp_path, "test-model")

    session_id = store.start()

    assert session_id == store.session_id
    assert store.path is not None and store.path.is_file()
    header = read_lines(store.path)[0]
    assert header["type"] == "session"
    assert header["id"] == session_id
    assert header["model"] == "test-model"
    assert header["created_at"] == store.created_at


def test_second_start_does_not_overwrite_existing_log(tmp_path) -> None:
    """同一秒内连续新建不会互相覆盖。"""
    store = SessionStore(tmp_path, "test-model")
    first = store.start()
    first_path = store.path
    second = store.start()

    assert second != first
    assert first_path is not None and first_path.is_file()
    assert store.path is not None and store.path.is_file()
    assert len(list(tmp_path.glob("*.jsonl"))) == 2


def test_messages_keeps_dialogue_and_skips_tools(tmp_path) -> None:
    """还原历史只取 user/assistant，工具事件留在日志里但不进对话。"""
    store = SessionStore(tmp_path, "test-model")
    store.start()
    store.append_message("user", "算一下 2048")
    store.append_tool("isLeapyear", '{"year": 2048}', '{"leap": true}', True)
    store.append_message("assistant", "2048 是闰年")

    assert store.messages(store.session_id) == [
        {"role": "user", "content": "算一下 2048"},
        {"role": "assistant", "content": "2048 是闰年"},
    ]
    # 工具事件确实写进了日志
    assert any(item.get("type") == "tool" for item in store.load(store.session_id))


def test_messages_restart_from_last_compact(tmp_path) -> None:
    """压缩点之前的对话丢弃，摘要作为新的开头。"""
    store = SessionStore(tmp_path, "test-model")
    store.start()
    store.append_message("user", "旧问题")
    store.append_message("assistant", "旧回答")
    store.append_compact("20260101-000000", "## 摘要\n\n旧结论")
    store.append_message("user", "新问题")

    messages = store.messages(store.session_id)

    assert messages[0]["role"] == "user"
    assert "旧结论" in messages[0]["content"]
    assert messages[1] == {"role": "assistant", "content": SUMMARY_ACK}
    assert messages[2] == {"role": "user", "content": "新问题"}
    assert all(item["content"] != "旧问题" for item in messages)


def test_list_sorts_newest_first_and_titles_from_first_prompt(tmp_path) -> None:
    """列表按时间倒序，标题取第一条用户消息。"""
    store = SessionStore(tmp_path, "test-model")
    older = store.start()
    store.append_message("user", "第一个会话的问题")
    import time

    time.sleep(0.01)
    newer = store.start()
    store.append_message("user", "第二个会话的问题")

    items = store.list()

    assert [item.id for item in items] == [newer, older]
    assert items[0].title == "第二个会话的问题"
    assert items[0].message_count == 1
    assert items[0].updated_at >= items[0].created_at
    assert store.latest() is not None and store.latest().id == newer


def test_list_skips_broken_lines(tmp_path) -> None:
    """崩溃写坏的半行不会让整个会话消失。"""
    store = SessionStore(tmp_path, "test-model")
    session_id = store.start()
    store.append_message("user", "能读到")
    path = store.path_for(session_id)
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"type": "message", "role": "user", "content": "half')

    items = store.list()

    assert len(items) == 1
    assert items[0].message_count == 1
    assert store.messages(session_id) == [{"role": "user", "content": "能读到"}]


def test_agents_md_roundtrip(tmp_path) -> None:
    """项目约定原文写进日志，恢复会话时还能取回来。"""
    store = SessionStore(tmp_path, "test-model")
    session_id = store.start()
    store.append_message("system", "# 项目约定\n用中文回答", kind="agents_md")

    assert store.agents_md(session_id) == "# 项目约定\n用中文回答"
    # 它不会被当成对话消息
    assert store.messages(session_id) == []


def test_attach_marks_existing_session_current(tmp_path) -> None:
    """恢复会话后，后续消息继续写进同一个文件。"""
    store = SessionStore(tmp_path, "test-model")
    old_id = store.start()
    store.append_message("user", "旧会话")

    other = SessionStore(tmp_path, "test-model")
    other.attach(old_id)
    other.append_message("assistant", "继续写")

    assert other.session_id == old_id
    assert other.message_count == 2
    assert [item["content"] for item in other.messages(old_id)] == ["旧会话", "继续写"]


def test_path_for_rejects_traversal(tmp_path) -> None:
    """编号来自用户输入，必须挡住路径分隔符。"""
    store = SessionStore(tmp_path, "test-model")

    for bad in ("../etc/passwd", "a/b", "", "x y", ".."):
        with pytest.raises(AgentError) as excinfo:
            store.path_for(bad)
        assert excinfo.value.code == ErrorCode.SESSION_FAILED


def test_export_markdown_writes_dialogue(tmp_path) -> None:
    """导出成 Markdown，问答各占一段。"""
    store = SessionStore(tmp_path, "test-model")
    session_id = store.start()
    store.append_message("user", "问题")
    store.append_message("assistant", "回答")

    path = store.export_markdown(session_id, tmp_path / "export")

    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "# 会话 %s" % session_id in text
    assert "## 你\n\n问题" in text
    assert "## AI\n\n回答" in text


def test_disabled_store_is_a_noop(tmp_path) -> None:
    """关掉会话日志时所有写操作都不落盘。"""
    store = SessionStore(tmp_path, "test-model", enabled=False)

    assert store.start() == ""
    assert store.save() is None
    store.append_message("user", "没人要")
    assert store.list() == []
    assert not list(tmp_path.glob("*.jsonl"))
