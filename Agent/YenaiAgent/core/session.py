"""一轮问答的编排：上下文裁剪、流式调用、工具循环、提交历史。

会话层只产出事件，不打印、不读输入，也不关心界面是什么样子。

第十一次课新增上下文压缩：``compact()`` 负责「归档原始上下文 → 调模型写摘要 →
用摘要替换历史」，``context_usage()`` 负责随时报告占用，达到阈值后
``compact_required`` 置位并拒绝新的普通提问，直到压缩成功。
"""

from __future__ import annotations

import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

from .agentsmd import read_project_prompt
from .archive import ContextArchive
from .budget import ContextUsage, estimate_message
from .budget import measure as measure_usage
from .compaction import build_compaction_messages, compose_summary, summary_history
from .config import AppConfig
from .context import build_messages, recent_messages
from .errors import AgentError, ConfigError, ErrorCode, LlmRequestError
from .events import (
    AgentEvent,
    CompactionArchived,
    CompactionCompleted,
    CompactionFailed,
    CompactionStarted,
    ContextWarning,
    TextDelta,
    ToolCallFinished,
    ToolCallRecord,
    ToolCallStarted,
    TurnCancelled,
    TurnCompleted,
    TurnFailed,
    TurnStarted,
)
from .llm.backend import LlmBackend
from .llm.collector import TurnCollector
from .llm.types import LlmRequest
from .mcp import McpHub
from .sessions import SessionStore
from .skills import SkillLibrary
from .tools.spec import ToolRegistry
from .transcript import Transcript


class CancelToken:
    """线程安全的中断标志，由界面层置位。"""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def reset(self) -> None:
        self._event.clear()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


class _Cancelled(Exception):
    """内部信号：中断发生在流式循环里，用异常跳出去。"""


class AgentSession:
    """持有内存上下文与存档，按需执行一次问答。"""

    def __init__(
        self,
        backend: LlmBackend,
        registry: ToolRegistry,
        config: AppConfig,
        transcript: Transcript | None = None,
        registry_factory: Callable[[Path | str], ToolRegistry] | None = None,
        skills: SkillLibrary | None = None,
        mcp: McpHub | None = None,
        archive: ContextArchive | None = None,
        sessions: SessionStore | None = None,
        project_root: Path | str | None = None,
    ) -> None:
        self._backend = backend
        self._registry = registry
        self._config = config
        self._transcript = transcript
        # 由装配点注入：换工作区时按新目录重建工具注册表
        self._registry_factory = registry_factory
        # 技能清单：名字与描述注入 System Prompt，全文只在 loadSkill 被调用时进入上下文
        self._skills = skills
        # MCP 会话：退出时由界面层调用 close() 释放子进程 / HTTP 连接
        self._mcp = mcp
        # 上下文归档目录：没有它就无法压缩（要求「先落盘再替换」）
        self._archive = archive
        # 会话事件日志：/new /resume /save 都靠它落地
        self._sessions = sessions
        # 项目根：AGENTS.md 从这里读，读到后整个会话复用同一份文本
        self._project_root = Path(project_root) if project_root is not None else None
        self._project_prompt = ""
        # 已挂上注册表的 MCP 工具名：异步加载完成后再同步时先摘后挂
        self._mcp_tool_names: list[str] = []
        self._history: list[dict[str, Any]] = []
        # 完整原始上下文：含 System Prompt 之外的全部消息、工具调用与工具结果
        self._raw: list[dict[str, Any]] = []
        # 接口返回的 prompt token 数（拿不到为 None，改用本地估算）
        self._last_usage: int | None = None
        # 上一次请求之后才生成的那条回答：真实用量不含它，显示时补上，
        # 否则占用条永远落后一轮，看起来像「越聊越少」
        self._usage_extra = 0
        # 占用到阈值后置位：暂停接受普通提问，直到压缩成功
        self._compact_required = False
        # 防止压缩过程被重复触发
        self._compacting = False

    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    @property
    def raw_context(self) -> list[dict[str, Any]]:
        """完整原始上下文（含工具调用与结果），只读副本。"""
        return [dict(item) for item in self._raw]

    @property
    def skills(self) -> SkillLibrary | None:
        return self._skills

    @property
    def mcp(self) -> McpHub | None:
        return self._mcp

    @property
    def archive(self) -> ContextArchive | None:
        return self._archive

    @property
    def sessions(self) -> SessionStore | None:
        return self._sessions

    @property
    def session_id(self) -> str | None:
        return None if self._sessions is None else self._sessions.session_id

    @property
    def project_root(self) -> Path | None:
        return self._project_root

    @property
    def project_prompt(self) -> str:
        """本会话注入的项目约定（AGENTS.md）；没有文件时为空串。"""
        return self._project_prompt

    @property
    def compact_required(self) -> bool:
        """是否已到阈值、正等待用户执行 /compact。"""
        return self._compact_required

    @property
    def transcript_path(self):
        return self._transcript.path if self._transcript is not None else None

    def reset(self) -> None:
        """清空上下文，并让后续存档写到新文件。"""
        self._history.clear()
        self._raw.clear()
        self._last_usage = None
        self._usage_extra = 0
        self._compact_required = False
        if self._transcript is not None:
            self._transcript.reset()
        # 清空后重新读一次 AGENTS.md，并另起一份会话日志
        self._project_prompt = ""
        if self._sessions is not None and self._sessions.enabled:
            self._sessions.start()

    def close(self) -> None:
        """结束 MCP 会话、回收子进程；退出前把会话日志刷盘。"""
        self.save_session()
        if self._mcp is not None:
            self._mcp.close()

    def switch_model(self, config: AppConfig) -> None:
        """切换模型等设置：保留当前上下文，从下一轮开始生效。"""
        self._config = config
        # 换了模型，上一轮的用量与窗口大小都不再适用
        self._last_usage = None
        self._usage_extra = 0

    def switch_workspace(self, workspace_root: Path | str) -> Path:
        """切换工作区：文件工具沙箱与 RunCli 工作目录随之改变，上下文保留。

        支持 ``%VAR%`` / ``~`` / 相对路径（按当前进程目录解析）。
        目录不存在或会话未注入注册表工厂时抛 :class:`ConfigError`。
        """
        root = Path(os.path.expandvars(str(workspace_root))).expanduser().resolve()
        if not root.exists():
            raise ConfigError(
                ErrorCode.CONFIG_INVALID, "工作区目录不存在：%s" % workspace_root
            )
        if not root.is_dir():
            raise ConfigError(ErrorCode.CONFIG_INVALID, "工作区不是目录：%s" % root)
        if self._registry_factory is None:
            raise ConfigError(
                ErrorCode.CONFIG_INVALID, "当前会话未启用工作区切换"
            )
        self._registry = self._registry_factory(root)
        return root

    # ------------------------------------------------------------ 会话管理

    def load_project_prompt(self) -> str:
        """读取并缓存 AGENTS.md：一个会话只读一次，之后每轮复用同一段文本。

        原文会写进会话事件日志（role=system, kind=agents_md），恢复会话时
        直接取日志里的那份，不再依赖磁盘上的文件是否还在。
        """
        if self._project_prompt or self._project_root is None:
            return self._project_prompt
        text = read_project_prompt(
            self._project_root,
            self._config.agents_md,
            self._config.agents_md_max_chars,
        )
        self._project_prompt = text
        if not text:
            return ""
        self._ensure_session()
        if self._sessions is not None:
            self._sessions.append_message("system", text, kind="agents_md")
        # 归档与压缩也应当看得见这段约定
        self._raw.insert(0, {"role": "system", "content": text})
        return text

    def _ensure_session(self) -> None:
        if self._sessions is not None and self._sessions.session_id is None:
            if self._sessions.enabled:
                self._sessions.start()

    def save_session(self) -> Path | None:
        """把会话事件日志刷到磁盘（/save）；没有日志时返回 None。"""
        if self._sessions is None or self._sessions.session_id is None:
            return None
        return self._sessions.save()

    def new_session(self) -> str | None:
        """结束当前会话并开启新日志（/new）；返回新编号，未启用日志时为 None。"""
        if self._sessions is None:
            self.reset()
            return None
        if self._sessions.session_id is not None:
            self._sessions.save()
        self._history.clear()
        self._raw.clear()
        self._last_usage = None
        self._usage_extra = 0
        self._compact_required = False
        self._project_prompt = ""
        if self._transcript is not None:
            self._transcript.reset()
        if not self._sessions.enabled:
            return None
        return self._sessions.start()

    def restore(self, session_id: str) -> int:
        """把历史会话读回内存（/resume），返回恢复的消息条数。"""
        if self._sessions is None:
            raise ConfigError(ErrorCode.SESSION_FAILED, "当前会话未启用会话日志")
        messages = self._sessions.messages(session_id)
        text = self._sessions.agents_md(session_id)
        self._sessions.attach(session_id)
        self._history = [dict(item) for item in messages]
        self._raw = [dict(item) for item in messages]
        if text:
            self._raw.insert(0, {"role": "system", "content": text})
        self._project_prompt = text
        self._last_usage = None
        self._usage_extra = 0
        self._compact_required = False
        return len(messages)

    def sync_mcp_tools(self) -> int:
        """MCP 异步加载完成后把工具挂进注册表，返回当前 MCP 工具数。

        先摘掉上一批自己挂的工具再重挂，避免重复注册报错；内置工具与用户
        自己注册的工具不受影响。
        """
        if self._mcp is None:
            return 0
        for name in self._mcp_tool_names:
            self._registry.remove(name)
        self._mcp_tool_names = []
        before = set(self._registry.names())
        self._mcp.register_into(self._registry)
        self._mcp_tool_names = [
            name for name in self._registry.names() if name not in before
        ]
        return len(self._mcp_tool_names)

    # ------------------------------------------------------------ 上下文占用

    def context_usage(self) -> ContextUsage:
        """当前上下文占用，口径与实际请求完全一致。

        统计对象就是 :func:`recent_messages` 的产物——System Prompt + 最近
        ``history_turns`` 轮历史——再加工具定义。工具调用与工具结果只在当轮
        请求里存在、下一轮不再发送，算进来只会让占用条虚高，所以不计入。

        优先用接口返回的真实用量（再补上这条请求之后才生成的那条回答，
        否则数字总落后一轮）；接口不给、或刚换模型 / 压缩过，就本地估算。
        """
        messages = recent_messages(
            self._history, self._config, self._extra_system()
        )
        api_tokens = None
        if self._last_usage is not None:
            api_tokens = self._last_usage + self._usage_extra
        return measure_usage(
            self._config,
            messages,
            self._registry.schemas(),
            api_tokens=api_tokens,
        )

    # ------------------------------------------------------------ 上下文压缩

    def compact(self) -> Iterator[AgentEvent]:
        """执行一次上下文压缩，逐事件产出进度。

        压缩期间只做两件事：归档原始上下文、让模型写摘要；不执行任何工具。
        任何一步失败都保留原上下文，用户可以重新执行 /compact。
        """
        if self._compacting:
            yield CompactionFailed(
                AgentError(ErrorCode.COMPACT_FAILED, "上一次压缩还在进行中")
            )
            return
        self._compacting = True
        try:
            yield from self._compact()
        finally:
            self._compacting = False

    def _compact(self) -> Iterator[AgentEvent]:
        usage = self.context_usage()
        yield CompactionStarted(
            message_count=len(self._raw), usage_tokens=usage.used
        )

        if not self._raw:
            yield CompactionFailed(
                AgentError(ErrorCode.COMPACT_FAILED, "当前没有可压缩的上下文")
            )
            return
        if self._archive is None:
            yield CompactionFailed(
                AgentError(
                    ErrorCode.COMPACT_FAILED, "当前会话没有配置上下文归档目录"
                )
            )
            return

        # 1) 归档：原始记录必须成功落盘，才允许动摘要与替换
        try:
            record = self._archive.save(self._raw, model=self._config.model_name)
        except AgentError as exc:
            yield CompactionFailed(exc)
            return
        yield CompactionArchived(
            archive_id=record.id,
            path=str(record.path),
            message_count=record.message_count,
            bytes=record.bytes,
        )

        # 2) 只调 LLM 生成摘要：tools 传空，压缩期间不可能触发 Function Calling
        parts: list[str] = []
        try:
            request = LlmRequest(
                model=self._config.model_name,
                messages=build_compaction_messages(
                    self._raw, target_tokens=self._config.compact_target_tokens
                ),
                tools=(),
                max_tokens=self._config.compact_max_tokens,
                timeout=self._config.compact_timeout,
            )
            for chunk in self._backend.stream(request):
                if chunk.content:
                    parts.append(chunk.content)
        except KeyboardInterrupt:
            yield CompactionFailed(
                AgentError(ErrorCode.COMPACT_FAILED, "压缩被中断，原上下文未改变")
            )
            return
        except LlmRequestError as exc:
            yield CompactionFailed(exc)
            return
        except Exception as exc:  # 兜底，界面层不该看到裸异常
            yield CompactionFailed(AgentError(ErrorCode.COMPACT_FAILED, str(exc)))
            return

        summary = "".join(parts).strip()
        if not summary:
            yield CompactionFailed(
                AgentError(ErrorCode.COMPACT_FAILED, "模型没有返回摘要，请重试")
            )
            return

        # 3) 用摘要替换历史：System Prompt 与工具定义不动，只换对话部分
        text = compose_summary(summary, record.id, record.created_at)
        self._history = summary_history(text)
        self._raw = []
        self._last_usage = None
        self._usage_extra = 0
        self._compact_required = False
        if self._sessions is not None:
            self._sessions.append_compact(record.id, text)
        after = self.context_usage()
        yield CompactionCompleted(
            archive_id=record.id,
            created_at=record.created_at,
            summary=text,
            usage_tokens=after.used,
            window=after.window,
        )

    # ------------------------------------------------------------ 一轮问答

    def ask(
        self,
        question: str,
        cancel: CancelToken | None = None,
    ) -> Iterator[AgentEvent]:
        """执行一轮问答，逐事件产出。

        只有完整成功才写入上下文与存档；失败或中断都不留下半截记录。
        """
        if self._compact_required:
            usage = self.context_usage()
            yield TurnFailed(
                AgentError(
                    ErrorCode.CONTEXT_LIMIT,
                    "上下文已占用 %d/%d tokens（%.0f%%），请先执行 /compact 压缩后再继续"
                    % (usage.used, usage.window, usage.percent),
                ),
                "",
            )
            return

        # 首次提问时注入 AGENTS.md 并开一份会话日志；之后每轮复用缓存
        self.load_project_prompt()
        self._ensure_session()
        yield TurnStarted(question)

        messages = build_messages(
            self._history, question, self._config, self._extra_system()
        )
        parts: list[str] = []
        records: list[ToolCallRecord] = []
        # 本轮产生的工具调用消息，按原顺序并入原始上下文
        turn_tail: list[dict[str, Any]] = []
        rounds = 0
        # 同一工具 + 同一组参数的连续调用次数，用来发现原地打转
        repeats: dict[tuple[str, str], int] = {}

        while True:
            if cancel is not None and cancel.cancelled:
                yield TurnCancelled("".join(parts))
                return

            collector = TurnCollector()
            try:
                request = LlmRequest(
                    model=self._config.model_name,
                    messages=messages,
                    tools=self._registry.schemas(),
                    max_tokens=self._config.max_tokens,
                    timeout=self._config.request_timeout,
                )
                for chunk in self._backend.stream(request):
                    collector.add_chunk(chunk)
                    if chunk.content:
                        parts.append(chunk.content)
                        yield TextDelta(chunk.content)
                    if cancel is not None and cancel.cancelled:
                        raise _Cancelled()
            except _Cancelled:
                yield TurnCancelled("".join(parts))
                return
            except LlmRequestError as exc:
                yield TurnFailed(exc, "".join(parts))
                return
            except KeyboardInterrupt:
                yield TurnCancelled("".join(parts))
                return
            except AgentError as exc:
                yield TurnFailed(exc, "".join(parts))
                return
            except Exception as exc:  # 兜底，避免界面层拿到裸异常
                yield TurnFailed(
                    AgentError(ErrorCode.UNKNOWN, str(exc)), "".join(parts)
                )
                return

            if collector.usage_tokens:
                # 接口给了真实用量就记下来，下一轮判断阈值时直接用。
                # 这份用量已经覆盖本次请求发出去的全部消息，旧增量作废。
                self._last_usage = collector.usage_tokens
                self._usage_extra = 0

            if not collector.text.strip() and not collector.has_tool_calls:
                # 流结束了却什么都没有：多半是连接被掐断或模型空回复。
                # 静默结束会让界面停在“思考中”，所以明确报错让用户重试。
                yield TurnFailed(
                    AgentError(
                        ErrorCode.UNKNOWN,
                        "模型没有返回任何内容（连接可能中断或模型异常），请重试。",
                    ),
                    "".join(parts),
                )
                return

            if not collector.has_tool_calls:
                break

            if rounds >= self._config.max_tool_rounds:
                # 不再报错中止：保留已经拿到的回答，让用户可以继续追问。
                text = "".join(parts) + _round_limit_note(self._config.max_tool_rounds)
                self._commit(question, text, records, turn_tail)
                yield TurnCompleted(text, tuple(records))
                yield from self._usage_events()
                return
            rounds += 1

            calls = collector.tool_calls()
            assistant_message = {
                "role": "assistant",
                "content": collector.text or None,
                "tool_calls": [
                    {
                        "id": call.call_id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": call.arguments,
                        },
                    }
                    for call in calls
                ],
            }
            messages.append(assistant_message)
            turn_tail.append(assistant_message)

            for call in calls:
                if cancel is not None and cancel.cancelled:
                    yield TurnCancelled("".join(parts))
                    return

                signature = (call.name, call.arguments)
                repeats[signature] = repeats.get(signature, 0) + 1
                if repeats[signature] > self._config.max_repeated_tool_calls:
                    # 模型在用同样的参数反复调同一个工具，再跑下去只是空转
                    text = "".join(parts) + _repeat_note(call.name)
                    self._commit(question, text, records, turn_tail)
                    yield TurnCompleted(text, tuple(records))
                    yield from self._usage_events()
                    return

                yield ToolCallStarted(call.name, call.arguments, call.call_id)
                started_at = datetime.now().strftime("%H:%M:%S")
                outcome = self._registry.execute(call.name, call.arguments)
                records.append(
                    ToolCallRecord(
                        name=call.name,
                        arguments=call.arguments,
                        output=outcome.output,
                        ok=outcome.ok,
                        started_at=started_at,
                    )
                )
                tool_message = {
                    "role": "tool",
                    "tool_call_id": call.call_id,
                    "content": outcome.output,
                }
                messages.append(tool_message)
                turn_tail.append(tool_message)
                yield ToolCallFinished(
                    call.name, call.arguments, outcome.output, outcome.ok
                )

        text = "".join(parts)
        if collector.finish_reason == "length":
            # 模型被单次输出上限截断：明确告诉用户，而不是让回答莫名其妙停在半句
            text += _truncated_note(self._config.max_tokens)
        self._commit(question, text, records, turn_tail)
        yield TurnCompleted(text, tuple(records))
        yield from self._usage_events()

    def _usage_events(self) -> Iterator[AgentEvent]:
        """一轮结束后检查占用：到阈值就发警告，并暂停后续普通提问。"""
        usage = self.context_usage()
        threshold = float(self._config.warn_ratio)
        if usage.ratio < threshold:
            return
        self._compact_required = True
        yield ContextWarning(
            used=usage.used,
            window=usage.window,
            ratio=usage.ratio,
            window_is_default=usage.window_is_default,
            threshold=threshold,
        )

    def _extra_system(self) -> str:
        """System Prompt 末尾追加的稳定内容：项目约定 + 技能清单。

        两者都与会话当前问题无关、逐轮逐字相同，才能吃到模型侧的提示词缓存。
        """
        blocks = [
            block
            for block in (self.load_project_prompt(), self._skills_prompt())
            if block
        ]
        return "\n\n".join(blocks)

    def _skills_prompt(self) -> str:
        """注入 System Prompt 的技能清单；没有 Skill 时为空串。"""
        if self._skills is None:
            return ""
        return self._skills.prompt_block()

    def _commit(
        self,
        question: str,
        text: str,
        records: list[ToolCallRecord],
        extras: list[dict[str, Any]] | None = None,
    ) -> None:
        """把一轮问答写入上下文与存档（失败和中断不走这里）。"""
        self._history.append({"role": "user", "content": question})
        self._history.append({"role": "assistant", "content": text})
        self._raw.append({"role": "user", "content": question})
        if extras:
            self._raw.extend(extras)
        self._raw.append({"role": "assistant", "content": text})
        if self._transcript is not None:
            self._transcript.save_turn(question, text, records)
        # 会话事件日志：/resume 靠它还原，工具调用也留档
        self._ensure_session()
        if self._sessions is not None:
            self._sessions.append_message("user", question)
            for record in records:
                self._sessions.append_tool(
                    record.name,
                    record.arguments,
                    record.output,
                    record.ok,
                    record.started_at,
                )
            self._sessions.append_message("assistant", text)
        # 真实用量是「上一次请求」的数字，刚生成的回答还没算进去，先记着
        self._usage_extra = estimate_message(
            {"role": "assistant", "content": text}
        )


def _round_limit_note(limit: int) -> str:
    return (
        "\n\n（本轮已连续调用工具 %d 轮，达到上限；上面的结果已保留，"
        "可以继续追问，或让我换个方式处理。）" % limit
    )


def _repeat_note(name: str) -> str:
    return (
        "\n\n（工具「%s」被反复以相同参数调用，已停止以免空转；"
        "可以换个说法，或告诉我需要什么信息。）" % name
    )


def _truncated_note(max_tokens: int) -> str:
    return (
        "\n\n（本次回答达到单次输出上限 %d tokens，后面被截断了；"
        "回复“继续”即可接着写，或在 config.ini 里调大 max_tokens。）" % max_tokens
    )
