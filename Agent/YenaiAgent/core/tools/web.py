"""网页抓取工具：本地 curl 下载 HTML + trafilatura 提取 Markdown 正文。

curl 用参数列表调用（不使用 shell），只接受 http/https 地址；超时、退出码、
HTML 解析失败、正文为空等情况都转成中文 :class:`ToolError`，由注册表统一
包装成 ``ok=False`` 的工具结果。
"""

from __future__ import annotations

import re
import subprocess
from typing import Any, Callable
from urllib.parse import urlsplit

import trafilatura

from ..constants import FETCH_MAX_CHARS, FETCH_TIMEOUT, FETCH_USER_AGENT
from ..errors import ToolError
from .spec import ToolSpec

# (args, timeout) -> 带 returncode/stdout/stderr 的结果；测试里可替换成假实现
Runner = Callable[[list[str], float], Any]
# (html) -> markdown 或 None；测试里可替换
Extractor = Callable[[str], str | None]

# curl 退出码里值得单独提示的几种
_ERROR_HINTS = {
    6: "无法解析域名",
    7: "无法连接服务器",
    22: "服务器返回了错误状态（如 404/403）",
    28: "请求超时",
    35: "TLS/SSL 握手失败",
    60: "HTTPS 证书校验失败",
}


class WebFetcher:
    """抓取网页并提取正文。"""

    def __init__(
        self,
        *,
        curl: str = "curl",
        timeout: float = FETCH_TIMEOUT,
        max_chars: int = FETCH_MAX_CHARS,
        runner: Runner | None = None,
        extractor: Extractor | None = None,
    ) -> None:
        self._curl = curl
        self._timeout = float(timeout)
        self._max_chars = int(max_chars)
        self._runner = runner or _run_curl
        self._extractor = extractor or extract_markdown

    def fetch(self, url: str) -> str:
        """下载并提取一个网页，返回「网页地址 + Markdown 正文」。"""
        target = _validate_url(url)
        html = self._download(target)
        markdown = self._extract(html)
        return self._compose(target, markdown)

    def _download(self, url: str) -> str:
        args = [
            self._curl,
            "-sS",  # 静默，但错误信息仍写 stderr
            "-L",  # 跟随重定向
            "-f",  # HTTP >= 400 视为失败，避免把错误页当正文
            "--compressed",
            "-A",
            FETCH_USER_AGENT,
            "--max-time",
            _seconds(self._timeout),
            url,
        ]
        try:
            completed = self._runner(args, self._timeout + 5.0)
        except FileNotFoundError as exc:
            raise ToolError(
                "找不到 curl：请确认系统已安装 curl（Windows 10 及以上自带）"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ToolError(
                "网页访问超时（超过 %g 秒）：%s" % (self._timeout, url)
            ) from exc
        except OSError as exc:
            raise ToolError("调用 curl 失败：%s" % exc) from exc

        code = int(getattr(completed, "returncode", 0) or 0)
        if code != 0:
            hint = _ERROR_HINTS.get(code, "curl 执行失败")
            raise ToolError(
                "网页访问失败（%s，退出码 %d）：%s"
                % (hint, code, _describe_stderr(completed))
            )

        html = _decode(getattr(completed, "stdout", b"") or b"")
        if not html.strip():
            raise ToolError("网页返回内容为空：%s" % url)
        return html

    def _extract(self, html: str) -> str:
        try:
            markdown = self._extractor(html)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError("网页正文解析失败：%s" % exc) from exc

        if not markdown or not markdown.strip():
            raise ToolError(
                "无法从该网页提取正文：可能是图片、视频、需要登录或由脚本渲染的页面"
            )
        return markdown.strip()

    def _compose(self, url: str, markdown: str) -> str:
        body = markdown
        if len(body) > self._max_chars:
            body = body[: self._max_chars].rstrip() + "\n\n…（正文过长，已截断）"
        return "网页：%s\n\n%s" % (url, body)


def build_fetch_tool(fetcher: WebFetcher) -> ToolSpec:
    """把抓取器包成一个函数调用工具。"""

    def handler(url: str) -> str:
        return fetcher.fetch(url)

    return ToolSpec(
        name="fetchWeb",
        description=(
            "读取网页正文：下载指定网页，提取标题、段落、列表、表格与链接，"
            "转成 Markdown 返回。适合在搜索拿到链接后查看全文。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "完整的 http 或 https 网页地址",
                }
            },
            "required": ["url"],
        },
        handler=handler,
    )


def extract_markdown(html: str) -> str | None:
    """用 trafilatura 把 HTML 转成 Markdown（保留标题、列表、表格、链接）。

    开启 ``favor_precision``，优先丢掉导航栏、广告、页脚这类正文以外的内容；
    标题里残留的 ``[¶](#锚点)`` 是网页自己的永久链接标记，对模型没有意义，
    顺手去掉。
    """
    try:
        markdown = trafilatura.extract(
            html,
            output_format="markdown",
            include_links=True,
            include_tables=True,
            include_formatting=True,
            include_comments=False,
            deduplicate=True,
            favor_precision=True,
        )
    except Exception as exc:  # lxml / 解析器内部异常
        raise ToolError("网页 HTML 解析失败：%s" % exc) from exc
    if not markdown:
        return None
    return _ANCHOR_LINK.sub("", markdown)


_ANCHOR_LINK = re.compile(r"\[\s*¶\s*\]\([^)]*\)")


def _run_curl(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _validate_url(url: str) -> str:
    text = url.strip() if isinstance(url, str) else ""
    if not text:
        raise ToolError("参数错误：url 不能为空")
    if " " in text:
        raise ToolError("参数错误：url 中不能包含空格")
    parsed = urlsplit(text)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ToolError("参数错误：仅支持 http 或 https 网页地址")
    if not parsed.netloc:
        raise ToolError("参数错误：url 缺少主机名")
    return text


def _decode(raw: bytes) -> str:
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", "replace")
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _describe_stderr(completed: Any) -> str:
    raw = getattr(completed, "stderr", b"") or b""
    text = " ".join(_decode(raw).split())
    if text.startswith("curl: "):
        text = text[len("curl: ") :]
    return text[:300] or "无错误输出"


def _seconds(value: float) -> str:
    return ("%g" % value) if value != int(value) else str(int(value))