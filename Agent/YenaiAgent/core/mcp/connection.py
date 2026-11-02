"""把 MCP SDK 的异步客户端包成同步、线程安全的连接。

每个 Server 独占一个后台线程和一条事件循环：MCP 的 stdio 客户端会启动子进程，
用 anyio 绑定当前事件循环，不能与 TUI 的线程混用一条 loop。线程里完成
initialize + list_tools 后 `start()` 立即返回；工具调用通过
`run_coroutine_threadsafe` 投递回这条 loop，调用方仍按同步函数使用。

一次连接失败只影响这一家 Server：错误保存在 `error` 里，:class:`McpHub`
会跳过它，其余工具照常注册。
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import threading
from concurrent.futures import TimeoutError as FuturesTimeoutError
from contextlib import AsyncExitStack
from typing import Any, Mapping

import anyio
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

from ..tools.spec import ToolOutcome
from .config import TRANSPORT_SSE, TRANSPORT_STDIO, McpServerConfig

try:  # mcp 2.x：URL 与 http_client 分离，headers 要自己建客户端
    from mcp.client.streamable_http import create_mcp_http_client
except ImportError:  # pragma: no cover - mcp 1.x
    create_mcp_http_client = None  # type: ignore[assignment]

try:  # mcp 1.x 的名字，2.x 已移除
    from mcp.client.streamable_http import streamablehttp_client as _legacy_http_client
except ImportError:  # pragma: no cover - mcp 2.x
    _legacy_http_client = None  # type: ignore[assignment]

#: 等连接结果的额外宽限，避免和 SDK 内部的超时卡在同一毫秒
_READY_GRACE = 0.5
#: 工具调用在服务端超时之外再留的余量
_CALL_GRACE = 5.0


class McpConnection:
    """一家 MCP Server 的连接与会话。"""

    def __init__(self, config: McpServerConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._session: ClientSession | None = None
        self._tools: tuple[Any, ...] = ()
        self._error: str | None = None
        self._stopped = False
        self._stop_event: anyio.Event | None = None
        self._errlog = None

    # ---------------------------------------------------------------- 状态

    @property
    def config(self) -> McpServerConfig:
        return self._config

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def tools(self) -> tuple[Any, ...]:
        """list_tools 返回的 MCP Tool 列表（连接成功前为空）。"""
        return self._tools

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def connected(self) -> bool:
        return (
            self._session is not None
            and self._error is None
            and not self._stopped
        )

    # ---------------------------------------------------------------- 生命周期

    def launch(self) -> None:
        """启动后台线程，不等待连接完成。"""
        with self._lock:
            if self._thread is not None:
                return
            if not self._config.enabled:
                self._error = "在 .mcp.json 中已禁用"
                return
            self._thread = threading.Thread(
                target=self._run,
                name="mcp-%s" % self._config.name,
                daemon=True,
            )
            self._thread.start()

    def start(self) -> bool:
        """启动并等待 initialize + list_tools 完成。"""
        self.launch()
        if self._thread is None:
            return False
        return self.wait_ready()

    def wait_ready(self, timeout: float | None = None) -> bool:
        """等待连接就绪；超时返回 False，不抛异常。"""
        if self._ready.is_set():
            return self.connected
        if self._thread is None:
            # launch() 因禁用而没起线程，没必要再等
            return self.connected
        limit = self._config.connect_timeout if timeout is None else timeout
        if not self._ready.wait(max(0.0, limit) + _READY_GRACE):
            with self._lock:
                if self._error is None:
                    self._error = "连接超时（%.0f 秒）：%s" % (
                        limit,
                        self._config.target or self._config.name,
                    )
            return False
        return self.connected

    def stop(self, grace: float = 3.0) -> None:
        """通知后台线程收尾，并等待它退出（最多 grace 秒）。"""
        self._stopped = True
        loop = self._loop
        event = self._stop_event
        if loop is not None and event is not None:
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:  # loop 已经关闭
                pass
        thread = self._thread
        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(grace)

    # ---------------------------------------------------------------- 调用

    def call_tool(
        self, tool_name: str, arguments: Mapping[str, Any] | None = None
    ) -> ToolOutcome:
        """同步调用 MCP 工具；所有失败都转成 ok=False 的结果。"""
        loop = self._loop
        session = self._session
        if not self.connected or loop is None or session is None:
            return _failure(self._unavailable_reason())
        payload = dict(arguments or {})
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._call(session, tool_name, payload), loop
            )
        except RuntimeError as exc:
            return _failure("MCP Server %s 已停止：%s" % (self.name, exc))
        try:
            return future.result(timeout=self._config.call_timeout + _CALL_GRACE)
        except (FuturesTimeoutError, TimeoutError):
            future.cancel()
            return _failure(
                "调用 MCP 工具 %s 超时（%.0f 秒）；确认 Server 是否仍在运行。"
                % (tool_name, self._config.call_timeout)
            )
        except Exception as exc:
            return _failure("调用 MCP 工具 %s 失败：%s" % (tool_name, _describe(exc)))

    async def _call(
        self,
        session: ClientSession,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolOutcome:
        result = await session.call_tool(
            tool_name,
            arguments or None,
            read_timeout_seconds=self._config.call_timeout,
        )
        return _to_outcome(result, self._config.max_output)

    # ---------------------------------------------------------------- 后台线程

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._serve())
        except BaseException as exc:  # 兜底：事件循环本身出错时也要留下原因
            if not self._stopped:
                self._fail("MCP 连接异常终止：%s" % _describe(exc))
        finally:
            self._session = None
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
            self._loop = None
            self._close_errlog()
            self._ready.set()

    async def _serve(self) -> None:
        stop_event = anyio.Event()
        self._stop_event = stop_event
        try:
            async with AsyncExitStack() as stack:
                read, write = await self._connect(stack)
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                listing = await session.list_tools()
                self._tools = tuple(listing.tools)
                self._session = session
                self._ready.set()
                await stop_event.wait()
        except BaseException as exc:
            if not self._stopped:
                self._fail(self._failure_message(exc))
        finally:
            self._session = None
            self._ready.set()

    async def _connect(self, stack: AsyncExitStack):
        config = self._config
        if config.transport == TRANSPORT_STDIO:
            self._errlog = tempfile.TemporaryFile(
                mode="w+", encoding="utf-8", errors="replace"
            )
            params = StdioServerParameters(
                command=config.command,
                args=list(config.args),
                env=dict(config.env) or None,
                cwd=config.cwd or None,
            )
            read, write = await stack.enter_async_context(
                stdio_client(params, errlog=self._errlog)
            )
            return read, write

        headers = dict(config.headers) or None
        if config.transport == TRANSPORT_SSE:
            return await stack.enter_async_context(
                sse_client(config.url, headers=headers, timeout=config.connect_timeout)
            )

        if _legacy_http_client is not None:
            streams = await stack.enter_async_context(
                _legacy_http_client(config.url, headers=headers)
            )
            return streams[0], streams[1]

        if create_mcp_http_client is None:  # pragma: no cover - 不该发生
            raise RuntimeError("当前 MCP SDK 缺少 Streamable HTTP 客户端")
        http_client = create_mcp_http_client(headers=headers)
        await stack.enter_async_context(http_client)
        streams = await stack.enter_async_context(
            streamable_http_client(config.url, http_client=http_client)
        )
        return streams[0], streams[1]

    # ---------------------------------------------------------------- 错误

    def _fail(self, message: str) -> None:
        with self._lock:
            if self._error is None:
                self._error = message

    def _failure_message(self, exc: BaseException) -> str:
        text = _describe(exc)
        if self._config.transport == TRANSPORT_STDIO:
            tail = self._stderr_tail()
            if tail:
                text = "%s（Server 输出：%s）" % (text, tail)
        return "连接 MCP Server %s 失败：%s" % (self.name, text)

    def _stderr_tail(self, limit: int = 800) -> str:
        stream = self._errlog
        if stream is None:
            return ""
        try:
            stream.flush()
            position = stream.tell()
            stream.seek(max(0, position - limit * 2))
            text = stream.read().strip()
        except (OSError, ValueError):
            return ""
        return text[-limit:]

    def _close_errlog(self) -> None:
        stream = self._errlog
        self._errlog = None
        if stream is not None:
            try:
                stream.close()
            except OSError:  # pragma: no cover
                pass

    def _unavailable_reason(self) -> str:
        if not self._config.enabled:
            return "MCP Server %s 在配置中已禁用。" % self.name
        if self._error:
            return "MCP Server %s 不可用：%s" % (self.name, self._error)
        return "MCP Server %s 尚未连接完成，请稍后再试。" % self.name


def input_schema(tool: Any) -> dict[str, Any]:
    """兼容 2.x 的 input_schema 与 1.x 的 inputSchema。"""
    schema = getattr(tool, "input_schema", None)
    if schema is None:
        schema = getattr(tool, "inputSchema", None)
    if isinstance(schema, Mapping):
        return dict(schema)
    return {"type": "object", "properties": {}}


def _to_outcome(result: Any, limit: int) -> ToolOutcome:
    is_error = bool(
        getattr(result, "is_error", False) or getattr(result, "isError", False)
    )
    parts = [_content_text(item) for item in getattr(result, "content", ()) or ()]
    text = "\n".join(part for part in parts if part)

    structured = getattr(result, "structured_content", None)
    if structured is None:
        structured = getattr(result, "structuredContent", None)
    if structured is not None:
        try:
            encoded = json.dumps(structured, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            encoded = str(structured)
        text = (text + "\n" if text else "") + "结构化结果：" + encoded

    if not text:
        text = "MCP 工具执行完成，但没有返回内容。"
    if len(text) > limit:
        text = text[:limit] + "\n…（结果超过 %d 字符，已截断）" % limit
    return ToolOutcome(text, not is_error)


def _content_text(item: Any) -> str:
    kind = getattr(item, "type", "")
    if kind == "text":
        return str(getattr(item, "text", "") or "")
    if kind == "image":
        return "[图片内容：%s]" % (getattr(item, "mime_type", None) or "未知类型")
    if kind == "audio":
        return "[音频内容：%s]" % (getattr(item, "mime_type", None) or "未知类型")
    if kind == "resource_link":
        return "[资源链接：%s]" % (getattr(item, "uri", "") or "未知地址")
    if kind == "resource":
        resource = getattr(item, "resource", None)
        if resource is None:
            return "[嵌入资源]"
        text = getattr(resource, "text", None)
        if text is not None:
            return str(text)
        blob = getattr(resource, "blob", None) or ""
        mime = getattr(resource, "mime_type", None) or "未知类型"
        return "[二进制资源：%s，%d 字节]" % (mime, len(blob))
    dump = getattr(item, "model_dump", None)
    if callable(dump):
        try:
            return json.dumps(dump(), ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            pass
    return str(item)


def _describe(exc: BaseException) -> str:
    """拆掉 anyio 的 ExceptionGroup，只留下最里面那条真实错误。"""
    current: BaseException = exc
    for _ in range(6):
        inner = getattr(current, "exceptions", None)
        if isinstance(inner, (list, tuple)) and inner:
            current = inner[0]
            continue
        break
    text = str(current).strip()
    return text or current.__class__.__name__


def _failure(message: str) -> ToolOutcome:
    return ToolOutcome(
        json.dumps({"ok": False, "error": message}, ensure_ascii=False), False
    )
