"""会话事件日志：把每一次对话按事件追加到 .agents/sessions/<编号>.jsonl。

为什么要“事件流”而不是“状态快照”：

* 追加写不会因为中途崩溃破坏已有记录，最后一行损坏也只是丢一条；
* 重放一遍就能还原聊天历史，不需要数据库；
* 工具调用、压缩事件都能留痕，汇总时按 type 过滤即可。

一条日志大概是：

    {"type": "session", "id": "20261105-101500", "created_at": "...", "model": "..."}
    {"type": "message", "role": "user", "content": "帮我看看这个报错", "ts": "..."}
    {"type": "tool", "name": "RunCli", "arguments": "{}", "output": "...", "ok": true}
    {"type": "message", "role": "assistant", "content": "...", "ts": "..."}
    {"type": "compact", "archive": "20261105-110000", "summary": "..."}

界面层只关心“有哪些会话 / 某个会话说了什么”，
所以这里只提供 list()、messages() 和导出 Markdown 这三件事。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .compaction import summary_history
from .constants import SESSION_LIST_LIMIT, SESSION_LOG_VERSION
from .errors import AgentError, ErrorCode

#: 会话编号：日期-时间，允许撞号后缀 -2、-3
_ID_PATTERN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z_-]{0,63}$")
#: 列表里显示的标题长度
_TITLE_CHARS = 60


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """一个历史会话的摘要，供 /resume 面板展示。"""

    id: str
    path: Path
    created_at: str
    updated_at: str
    title: str
    message_count: int
    bytes: int


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SessionStore:
    """会话日志的读写门面；一个实例对应“当前正在写的那个会话”。"""

    def __init__(
        self,
        directory: Path | str,
        model_name: str = "",
        *,
        enabled: bool = True,
    ) -> None:
        self._directory = Path(directory)
        self._model = model_name
        self._enabled = enabled
        self._id = ""
        self._path: Path | None = None
        self._created_at = ""
        self._message_count = 0

    # ---------------------------------------------------------------- 属性

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def directory(self) -> Path:
        return self._directory

    @property
    def session_id(self) -> str | None:
        """当前会话编号；还没开始写日志时是 None（不是空串）。"""
        return self._id or None

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def created_at(self) -> str:
        return self._created_at

    @property
    def message_count(self) -> int:
        return self._message_count

    # ---------------------------------------------------------------- 写入

    def start(self, *, title: str = "") -> str:
        """开一个新会话（旧文件原样留在磁盘上），返回编号。"""
        if not self._enabled:
            return ""
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AgentError(
                ErrorCode.SESSION_FAILED, "无法创建会话目录：%s" % exc
            ) from exc
        self._id = self._new_id()
        self._path = self._directory / ("%s.jsonl" % self._id)
        self._created_at = _now()
        self._message_count = 0
        self._write(
            {
                "type": "session",
                "id": self._id,
                "created_at": self._created_at,
                "model": self._model,
                "title": title,
                "version": SESSION_LOG_VERSION,
            }
        )
        return self._id

    def append(self, event: dict[str, Any]) -> None:
        """追加一条事件；type 必须由调用方给全。"""
        if not self._enabled:
            return
        if self._path is None:
            self.start()
        record = dict(event)
        record.setdefault("ts", _now())
        self._write(record)
        if record.get("type") == "message":
            self._message_count += 1

    def append_message(self, role: str, content: str, **extra: Any) -> None:
        self.append({"type": "message", "role": role, "content": content, **extra})

    def append_tool(
        self,
        name: str,
        arguments: str,
        output: str,
        ok: bool,
        started_at: str = "",
    ) -> None:
        self.append(
            {
                "type": "tool",
                "name": name,
                "arguments": arguments,
                "output": output,
                "ok": ok,
                "started_at": started_at,
            }
        )

    def append_compact(self, archive_id: str, summary: str) -> None:
        """压缩事件：重建历史时从这里之后开始，摘要作为新的开头。"""
        self.append({"type": "compact", "archive": archive_id, "summary": summary})

    def save(self) -> Path | None:
        """把当前会话刷到磁盘（fsync），返回文件路径。"""
        if not self._enabled:
            return None
        if self._path is None:
            self.start()
        assert self._path is not None
        try:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise AgentError(
                ErrorCode.SESSION_FAILED, "无法保存会话：%s" % exc
            ) from exc
        return self._path

    # ---------------------------------------------------------------- 读取

    def path_for(self, session_id: str) -> Path:
        """会话编号 → 文件路径；拒绝带路径分隔符的编号。"""
        if not _ID_PATTERN.match(str(session_id or "")):
            raise AgentError(ErrorCode.SESSION_FAILED, "会话编号不合法：%s" % session_id)
        return self._directory / ("%s.jsonl" % session_id)

    def attach(self, session_id: str) -> Path:
        """把“当前会话”指向已有日志，后续消息继续写进它（即恢复会话）。"""
        path = self.path_for(session_id)
        if not path.is_file():
            raise AgentError(ErrorCode.SESSION_FAILED, "会话不存在：%s" % session_id)
        try:
            events = _read_events(path)
        except OSError as exc:
            raise AgentError(
                ErrorCode.SESSION_FAILED, "无法读取会话：%s" % exc
            ) from exc
        header = _header(events)
        self._id = session_id
        self._path = path
        self._created_at = str(header.get("created_at") or "")
        self._message_count = sum(1 for item in events if item.get("type") == "message")
        self._enabled = True
        return path

    def load(self, session_id: str) -> list[dict[str, Any]]:
        """读取一个会话的全部事件（损坏行会被跳过）。"""
        path = self.path_for(session_id)
        if not path.is_file():
            raise AgentError(ErrorCode.SESSION_FAILED, "会话不存在：%s" % session_id)
        try:
            return _read_events(path)
        except OSError as exc:
            raise AgentError(
                ErrorCode.SESSION_FAILED, "无法读取会话：%s" % exc
            ) from exc

    def messages(self, session_id: str) -> list[dict[str, Any]]:
        """还原聊天历史：压缩点之后的对话，加上压缩摘要本身。"""
        events = self.load(session_id)
        start = 0
        summary = ""
        for index, item in enumerate(events):
            if item.get("type") == "compact":
                start = index + 1
                summary = str(item.get("summary") or "")
        restored: list[dict[str, Any]] = []
        if summary:
            restored.extend(summary_history(summary))
        for item in events[start:]:
            if item.get("type") != "message":
                continue
            role = str(item.get("role") or "")
            if role not in ("user", "assistant"):
                continue
            restored.append({"role": role, "content": str(item.get("content") or "")})
        return restored

    def agents_md(self, session_id: str) -> str:
        """取回会话首次加载时注入的项目约定（AGENTS.md）原文。"""
        try:
            events = self.load(session_id)
        except AgentError:
            return ""
        text = ""
        for item in events:
            if item.get("type") == "message" and item.get("kind") == "agents_md":
                text = str(item.get("content") or "")
        return text

    def list(self, limit: int = SESSION_LIST_LIMIT) -> list[SessionInfo]:
        """按时间倒序列出历史会话；损坏或空文件直接跳过。"""
        if not self._directory.is_dir():
            return []
        infos: list[SessionInfo] = []
        for path in self._directory.glob("*.jsonl"):
            info = _describe(path)
            if info is not None:
                infos.append(info)
        infos.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        return infos[: max(1, limit)]

    def latest(self) -> SessionInfo | None:
        infos = self.list(limit=1)
        return infos[0] if infos else None

    def export_markdown(self, session_id: str, directory: Path | str) -> Path:
        """把会话导出成一份 Markdown，方便贴给别人或存档。"""
        messages = self.messages(session_id)
        lines = ["# 会话 %s" % session_id, ""]
        for item in messages:
            who = "你" if item["role"] == "user" else "AI"
            lines.append("## %s" % who)
            lines.append("")
            lines.append(str(item["content"]))
            lines.append("")
        target = Path(directory)
        try:
            target.mkdir(parents=True, exist_ok=True)
            path = target / ("%s.md" % session_id)
            path.write_text("\n".join(lines), encoding="utf-8")
        except OSError as exc:
            raise AgentError(
                ErrorCode.SESSION_FAILED, "无法导出会话：%s" % exc
            ) from exc
        return path

    # ---------------------------------------------------------------- 内部

    def _new_id(self) -> str:
        base = datetime.now().strftime("%Y%m%d-%H%M%S")
        candidate = base
        counter = 2
        while (self._directory / ("%s.jsonl" % candidate)).exists():
            candidate = "%s-%d" % (base, counter)
            counter += 1
        return candidate

    def _write(self, record: dict[str, Any]) -> None:
        assert self._path is not None
        try:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            raise AgentError(
                ErrorCode.SESSION_FAILED, "无法写入会话：%s" % exc
            ) from exc


def _read_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                # 崩溃时最后一行可能只写了一半：跳过它，其余记录照常可用
                continue
            if isinstance(item, dict):
                events.append(item)
    return events


def _header(events: list[dict[str, Any]]) -> dict[str, Any]:
    for item in events:
        if item.get("type") == "session":
            return item
    return {}


def _title(events: list[dict[str, Any]]) -> str:
    for item in events:
        if item.get("type") == "message" and item.get("role") == "user":
            text = " ".join(str(item.get("content") or "").split())
            return text[:_TITLE_CHARS]
    return "(空会话)"


def _describe(path: Path) -> SessionInfo | None:
    try:
        events = _read_events(path)
        size = path.stat().st_size
    except OSError:
        return None
    header = _header(events)
    created = str(header.get("created_at") or "")
    updated_at = created
    count = 0
    for item in events:
        if not item.get("type"):
            continue
        stamp = str(item.get("ts") or "")
        if stamp:
            updated_at = stamp
        if item.get("type") == "message":
            count += 1
    return SessionInfo(
        id=path.stem,
        path=path,
        created_at=created,
        updated_at=updated_at,
        title=_title(events),
        message_count=count,
        bytes=size,
    )
