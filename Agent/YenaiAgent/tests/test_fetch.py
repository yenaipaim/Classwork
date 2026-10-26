"""fetchWeb 工具：curl 下载与 trafilatura 提取的单元测试（不访问网络）。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from core.errors import ToolError
from core.factory import build_registry
from core.tools.web import WebFetcher, build_fetch_tool, extract_markdown

HTML = """<html><body>
<nav><a href="/x">首页</a> <a href="/y">新闻</a></nav>
<article>
<h1>标题A</h1>
<p>这是第一段正文，内容足够长一些以便提取器认为它是一篇真正的文章。</p>
<p>第二段：说明 trafilatura 的作用，保留段落结构。</p>
<ul><li>项目一</li><li>项目二</li></ul>
<table><tr><th>名称</th><th>数量</th></tr><tr><td>格1</td><td>格2</td></tr></table>
<p>链接：<a href="https://example.com/page">示例链接</a></p>
</article>
<footer>版权所有 2026</footer>
</body></html>"""

MARKDOWN = "# 标题A\n\n正文段落。\n\n- 项目一\n- 项目二"


def make_runner(
    *,
    returncode: int = 0,
    stdout: bytes = HTML.encode("utf-8"),
    stderr: bytes = b"",
) -> tuple[list, object]:
    """构造假 curl：记录调用参数，返回固定结果。"""
    calls: list = []

    def runner(args, timeout):
        calls.append((list(args), timeout))
        return subprocess.CompletedProcess(
            args, returncode, stdout=stdout, stderr=stderr
        )

    runner.calls = calls  # type: ignore[attr-defined]
    return calls, runner


def test_fetch_returns_url_and_markdown() -> None:
    calls, runner = make_runner()
    fetcher = WebFetcher(runner=runner, extractor=lambda html: MARKDOWN)

    output = fetcher.fetch("https://example.com/a")

    assert output.startswith("网页：https://example.com/a")
    assert MARKDOWN in output

    args, _timeout = calls[0]
    assert isinstance(args, list)  # 参数列表，不走 shell
    assert args[0] == "curl"
    assert "-L" in args and "-f" in args and "-sS" in args
    assert args[-1] == "https://example.com/a"


def test_curl_failure_reports_hint_and_stderr() -> None:
    _calls, runner = make_runner(
        returncode=22, stdout=b"", stderr=b"curl: (22) The requested URL returned error: 502"
    )
    fetcher = WebFetcher(runner=runner, extractor=lambda html: MARKDOWN)

    with pytest.raises(ToolError) as excinfo:
        fetcher.fetch("https://example.com/a")

    message = str(excinfo.value)
    assert "网页访问失败" in message
    assert "退出码 22" in message
    assert "502" in message


def test_missing_curl_is_reported() -> None:
    def runner(args, timeout):
        raise FileNotFoundError("curl")

    fetcher = WebFetcher(runner=runner, extractor=lambda html: MARKDOWN)

    with pytest.raises(ToolError, match="找不到 curl"):
        fetcher.fetch("https://example.com/a")


def test_curl_timeout_is_reported() -> None:
    def runner(args, timeout):
        raise subprocess.TimeoutExpired(args, timeout)

    fetcher = WebFetcher(runner=runner, extractor=lambda html: MARKDOWN)

    with pytest.raises(ToolError, match="网页访问超时"):
        fetcher.fetch("https://example.com/a")


def test_empty_response_is_rejected() -> None:
    _calls, runner = make_runner(stdout=b"   ")
    fetcher = WebFetcher(runner=runner, extractor=lambda html: MARKDOWN)

    with pytest.raises(ToolError, match="内容为空"):
        fetcher.fetch("https://example.com/a")


@pytest.mark.parametrize("url", ["", "   ", "file:///C:/Windows/win.ini", "ftp://example.com/a", "https://", "https://a b.com"])
def test_invalid_urls_are_rejected(url: str) -> None:
    fetcher = WebFetcher(runner=lambda a, t: None, extractor=lambda html: MARKDOWN)

    with pytest.raises(ToolError):
        fetcher.fetch(url)


def test_extraction_failure_is_reported() -> None:
    _calls, runner = make_runner()
    fetcher = WebFetcher(runner=runner, extractor=lambda html: None)

    with pytest.raises(ToolError, match="无法从该网页提取正文"):
        fetcher.fetch("https://example.com/a")


def test_extractor_crash_is_reported() -> None:
    _calls, runner = make_runner()

    def extractor(html: str):
        raise ValueError("bad html")

    fetcher = WebFetcher(runner=runner, extractor=extractor)

    with pytest.raises(ToolError, match="网页正文解析失败"):
        fetcher.fetch("https://example.com/a")


def test_long_markdown_is_truncated() -> None:
    _calls, runner = make_runner()
    fetcher = WebFetcher(
        runner=runner, extractor=lambda html: "x" * 30000, max_chars=20000
    )

    output = fetcher.fetch("https://example.com/a")

    assert output.endswith("…（正文过长，已截断）")
    assert len(output) < 20200


def test_extract_markdown_keeps_structure_and_drops_chrome() -> None:
    markdown = extract_markdown(HTML)

    assert markdown is not None
    assert "# 标题A" in markdown
    assert "第一段正文" in markdown
    assert "- 项目一" in markdown
    assert "| 名称 | 数量 |" in markdown
    assert "[示例链接](https://example.com/page)" in markdown
    assert "首页" not in markdown
    assert "版权所有" not in markdown


def test_fetch_tool_registered_between_search_and_list_tools(workspace: Path) -> None:
    registry = build_registry(workspace)
    names = registry.names()

    assert names.index("searchWeb") < names.index("fetchWeb") < names.index("list_tools")


def test_fetch_tool_reports_errors_as_failed_outcome(workspace: Path) -> None:
    registry = build_registry(workspace)

    missing_url = registry.execute("fetchWeb", "{}")
    assert missing_url.ok is False
    assert "工具参数错误" in json.loads(missing_url.output)["error"]

    bad_scheme = registry.execute("fetchWeb", json.dumps({"url": "file:///etc/passwd"}))
    assert bad_scheme.ok is False
    assert "仅支持 http" in json.loads(bad_scheme.output)["error"]