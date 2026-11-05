"""上下文归档：把原始消息按 JSONL 写入 `.agents/context/`。

一行一条消息，保留角色、内容、工具调用参数、工具返回结果与顺序，方便日后
用 `recallContext` 做本地全文检索。文件名就是归档编号：
`20261022-153000.jsonl`。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from .errors import AgentError, ErrorCode

ARCHIVE_SUFFIX = ".jsonl"
ID_FORMAT = "%Y%m%d-%H%M%S"

#: 检索结果的控制上限：片段太多会把上下文再次撑满
RECALL_MAX_SNIPPETS = 6
RECALL_MAX_CHARS = 3_600
#: 命中位置前后保留的字符数
SNIPPET_RADIUS = 120


@dataclass(frozen=True, slots=True)
class ArchiveRecord:
    """一次归档的结果。"""

    id: str
    path: Path
    message_count: int
    bytes: int
    created_at: str


@dataclass(frozen=True, slots=True)
class RecallHit:
    """一条命中：来自哪个归档、第几行、什么角色、相关度与片段。"""

    archive: str
    line: int
    role: str
    score: int
    snippet: str


@dataclass(frozen=True, slots=True)
class RecallResult:
    query: str
    archives_searched: int
    matched: int
    hits: tuple[RecallHit, ...]
    truncated: bool
    mode: str  # "phrase"（整句命中）或 "keyword"（拆词命中）


class ContextArchive:
    """归档目录的读写门面；目录在第一次写入时才创建。"""

    def __init__(
        self,
        directory: Path | str,
        *,
        max_snippets: int = RECALL_MAX_SNIPPETS,
        max_chars: int = RECALL_MAX_CHARS,
    ) -> None:
        self._directory = Path(directory)
        # 单次检索的预算：由 config.ini 的 [context] 段决定，避免结果再次占满上下文
        self._max_snippets = max(1, int(max_snippets))
        self._max_chars = max(200, int(max_chars))

    @property
    def directory(self) -> Path:
        return self._directory

    # ---------------------------------------------------------------- 写入

    def save(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        model: str = "",
    ) -> ArchiveRecord:
        """把消息按原顺序写成一个新归档；写失败抛 :class:`AgentError`。

        先写临时文件再原子改名，避免留下写了一半的归档——上层要求
        「原始记录成功保存后才继续压缩」。
        """
        if not messages:
            raise AgentError(ErrorCode.ARCHIVE_FAILED, "没有可归档的消息")
        created = datetime.now()
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AgentError(
                ErrorCode.ARCHIVE_FAILED, "无法创建归档目录：%s" % exc
            ) from exc

        path = self._unique_path(created)
        temp = path.with_name(path.name + ".tmp")
        try:
            with temp.open("w", encoding="utf-8", newline="\n") as handle:
                for index, message in enumerate(messages, 1):
                    handle.write(
                        json.dumps(
                            _archive_entry(message, index, model),
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        except OSError as exc:
            try:
                temp.unlink()
            except OSError:
                pass
            raise AgentError(
                ErrorCode.ARCHIVE_FAILED, "写入归档失败：%s" % exc
            ) from exc
        return ArchiveRecord(
            id=path.stem,
            path=path,
            message_count=len(messages),
            bytes=path.stat().st_size,
            created_at=created.strftime("%Y-%m-%d %H:%M:%S"),
        )

    def _unique_path(self, moment: datetime) -> Path:
        base = moment.strftime(ID_FORMAT)
        index = 1
        while True:
            name = base if index == 1 else "%s-%d" % (base, index)
            path = self._directory / (name + ARCHIVE_SUFFIX)
            if not path.exists():
                return path
            index += 1

    # ---------------------------------------------------------------- 读取

    def list_archives(self) -> list[Path]:
        """全部归档文件，新的在前（先按写入时间，同一秒再按文件名）。"""
        if not self._directory.is_dir():
            return []
        paths = list(self._directory.glob("*" + ARCHIVE_SUFFIX))

        def order(path: Path) -> tuple[float, str]:
            try:
                return (path.stat().st_mtime, path.name)
            except OSError:
                return (0.0, path.name)

        return sorted(paths, key=order, reverse=True)

    def ids(self) -> list[str]:
        return [path.stem for path in self.list_archives()]

    def path_for(self, archive_id: str) -> Path | None:
        """把编号映射成文件路径；只接受纯编号，挡住 `../` 之类的路径穿越。"""
        name = (archive_id or "").strip()
        if not name:
            return None
        if name.lower().endswith(ARCHIVE_SUFFIX):
            name = name[: -len(ARCHIVE_SUFFIX)]
        if not name or "/" in name or "\\" in name or name in (".", ".."):
            return None
        return self._directory / (name + ARCHIVE_SUFFIX)

    def load(self, archive_id: str) -> list[dict[str, Any]]:
        """读回一个归档的全部消息。"""
        path = self.path_for(archive_id)
        if path is None or not path.is_file():
            raise AgentError(ErrorCode.ARCHIVE_FAILED, "找不到归档：%s" % archive_id)
        return [message for _, message in self._iter_messages(path)]

    def search(
        self,
        text: str,
        *,
        archive_id: str | None = None,
        max_snippets: int | None = None,
        max_chars: int | None = None,
    ) -> RecallResult:
        """本地全文检索：整句命不中时按逗号/空白拆词，再按相关度排序截断。"""
        if max_snippets is None:
            max_snippets = self._max_snippets
        if max_chars is None:
            max_chars = self._max_chars
        query = " ".join((text or "").split())
        if not query:
            raise ValueError("检索关键词不能为空")
        files = self._files_of(archive_id)
        needle = query.lower()
        tokens = [
            token for token in re.split(r"[\s,，、;；|]+", needle) if len(token) >= 2
        ]

        hits: list[RecallHit] = []
        matched = 0
        mode = "phrase"
        for path in files:
            for line_no, message in self._iter_messages(path):
                haystack = _searchable(message)
                lowered = haystack.lower()
                score = lowered.count(needle)
                hit_mode = "phrase"
                if score == 0 and tokens:
                    hit_mode = "keyword"
                    score = sum(len(token) for token in tokens if token in lowered)
                if score <= 0:
                    continue
                matched += 1
                if hit_mode == "keyword":
                    mode = "keyword"
                hits.append(
                    RecallHit(
                        archive=path.stem,
                        line=line_no,
                        role=str(message.get("role") or ""),
                        score=score,
                        snippet=_snippet(
                            haystack,
                            needle if hit_mode == "phrase" else "",
                            tokens,
                        ),
                    )
                )

        hits.sort(key=lambda hit: hit.score, reverse=True)
        kept: list[RecallHit] = []
        used = 0
        for hit in hits:
            if len(kept) >= max_snippets or used + len(hit.snippet) > max_chars:
                break
            kept.append(hit)
            used += len(hit.snippet)
        return RecallResult(
            query=query,
            archives_searched=len(files),
            matched=matched,
            hits=tuple(kept),
            truncated=len(kept) < len(hits),
            mode=mode,
        )

    def _files_of(self, archive_id: str | None) -> list[Path]:
        if archive_id:
            path = self.path_for(archive_id)
            if path is None or not path.is_file():
                raise ValueError("找不到归档：%s" % archive_id)
            return [path]
        return self.list_archives()

    def _iter_messages(self, path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        message = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(message, dict):
                        yield line_no, message
        except OSError:
            return


def _archive_entry(
    message: Mapping[str, Any], index: int, model: str
) -> dict[str, Any]:
    """只保留有检索价值的字段，并补上顺序编号。"""
    entry: dict[str, Any] = {"index": index, "role": message.get("role") or ""}
    content = message.get("content")
    if content is not None:
        entry["content"] = content
    if message.get("tool_calls"):
        entry["tool_calls"] = message["tool_calls"]
    if message.get("tool_call_id"):
        entry["tool_call_id"] = message["tool_call_id"]
    if message.get("name"):
        entry["name"] = message["name"]
    if model and index == 1:
        entry["model"] = model
    return entry


def _searchable(message: Mapping[str, Any]) -> str:
    """把一条消息摊平成可检索文本（正文 + 工具名 + 参数 + 结果 id）。"""
    parts: list[str] = []
    content = message.get("content")
    if isinstance(content, str) and content:
        parts.append(content)
    elif content:
        try:
            parts.append(json.dumps(content, ensure_ascii=False))
        except (TypeError, ValueError):
            parts.append(str(content))
    calls = message.get("tool_calls") or ()
    for call in calls:
        function = call.get("function") if isinstance(call, Mapping) else None
        if not isinstance(function, Mapping):
            continue
        parts.append(str(function.get("name") or ""))
        parts.append(str(function.get("arguments") or ""))
    if message.get("tool_call_id"):
        parts.append(str(message["tool_call_id"]))
    return "\n".join(part for part in parts if part)


def _snippet(
    text: str,
    phrase: str,
    tokens: Sequence[str],
    radius: int = SNIPPET_RADIUS,
) -> str:
    lowered = text.lower()
    position = lowered.find(phrase) if phrase else -1
    if position < 0:
        for token in tokens:
            position = lowered.find(token)
            if position >= 0:
                break
    if position < 0:
        position = 0
    start = max(position - radius, 0)
    end = min(position + radius, len(text))
    snippet = " ".join(text[start:end].split())
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet
