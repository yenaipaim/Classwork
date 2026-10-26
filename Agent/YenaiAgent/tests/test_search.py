"""网络搜索工具测试：全部使用假 transport，不发真实请求。"""

from __future__ import annotations

import io
import json
import urllib.error
from typing import Any

import pytest

from core.errors import ToolError
from core.tools.search import SearchClient, build_search_tool
from core.tools.spec import ToolRegistry


def _references(count: int = 2) -> list[dict[str, Any]]:
    return [
        {
            "id": index,
            "title": "标题%d" % index,
            "url": "https://example.test/%d" % index,
            "content": "摘要内容%d" % index,
            "date": "2026-10-2%d" % index,
        }
        for index in range(1, count + 1)
    ]


def _transport(payload: dict[str, Any] | None = None, *, status: int = 200, text: str | None = None):
    calls: list[dict[str, Any]] = []

    def send(url: str, headers: dict[str, str], body: bytes, timeout: float) -> tuple[int, str]:
        calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": json.loads(body.decode("utf-8")),
                "timeout": timeout,
            }
        )
        if text is not None:
            return status, text
        return status, json.dumps(payload or {"references": _references()}, ensure_ascii=False)

    send.calls = calls  # type: ignore[attr-defined]
    return send


def test_search_formats_results_and_sends_query() -> None:
    send = _transport()
    client = SearchClient("key", transport=send)

    results = client.search("今天有什么新闻", 2)

    assert [item.title for item in results] == ["标题1", "标题2"]
    assert send.calls[0]["url"].endswith("/v2/ai_search/chat/completions")
    assert send.calls[0]["headers"]["Authorization"] == "Bearer key"
    assert send.calls[0]["payload"]["messages"][0]["content"] == "今天有什么新闻"
    assert send.calls[0]["payload"]["stream"] is False

    text = client.format("今天有什么新闻", results)
    assert "今天有什么新闻" in text
    assert "标题1" in text
    assert "https://example.test/1" in text
    assert "摘要：摘要内容1" in text
    assert "日期：2026-10-21" in text


def test_search_truncates_long_snippet() -> None:
    payload = {"references": [{"title": "长文", "url": "https://example.test/long", "content": "字" * 1000}]}
    client = SearchClient("key", transport=_transport(payload))

    results = client.search("长文")

    assert results[0].snippet.endswith("…")
    assert len(results[0].snippet) <= 401


def test_search_clamps_count_and_ignores_bad_values() -> None:
    payload = {"references": _references(30)}
    client = SearchClient("key", transport=_transport(payload))

    assert len(client.search("q", 3)) == 3
    assert len(client.search("q", 99)) == 10
    assert len(client.search("q", 0)) == 1
    assert len(client.search("q", "bad")) == 5


def test_search_requires_api_key() -> None:
    client = SearchClient("")

    with pytest.raises(ToolError) as excinfo:
        client.search("q")
    assert "baidu_qianfan_api_key" in str(excinfo.value)


def test_search_rejects_blank_query() -> None:
    client = SearchClient("key", transport=_transport())

    with pytest.raises(ToolError):
        client.search("   ")


def test_search_reports_http_error_with_body() -> None:
    body = json.dumps({"error_code": 110, "error_msg": "invalid api key"}, ensure_ascii=False)
    client = SearchClient("key", transport=_transport(status=401, text=body))

    with pytest.raises(ToolError) as excinfo:
        client.search("q")

    message = str(excinfo.value)
    assert "HTTP 401" in message
    assert "invalid api key" in message


def test_search_handles_http_error_raised_by_transport() -> None:
    def send(url, headers, body, timeout):
        raise urllib.error.HTTPError(
            url,
            500,
            "Server Error",
            {},
            io.BytesIO(b'{"error_msg":"boom"}'),
        )

    client = SearchClient("key", transport=send)

    with pytest.raises(ToolError) as excinfo:
        client.search("q")
    assert "HTTP 500" in str(excinfo.value)
    assert "boom" in str(excinfo.value)


def test_search_reports_network_failure() -> None:
    def send(url, headers, body, timeout):
        raise urllib.error.URLError("connection refused")

    client = SearchClient("key", transport=send)

    with pytest.raises(ToolError) as excinfo:
        client.search("q")
    assert "无法连接搜索服务" in str(excinfo.value)
    assert "connection refused" in str(excinfo.value)


def test_search_reports_invalid_json() -> None:
    client = SearchClient("key", transport=_transport(text="<html>gateway</html>"))

    with pytest.raises(ToolError) as excinfo:
        client.search("q")
    assert "无法解析" in str(excinfo.value)


def test_search_reports_business_error_in_200() -> None:
    payload = {"error_code": 500001, "error_msg": "quota exceeded"}
    client = SearchClient("key", transport=_transport(payload))

    with pytest.raises(ToolError) as excinfo:
        client.search("q")
    assert "500001" in str(excinfo.value)
    assert "quota exceeded" in str(excinfo.value)


def test_search_empty_results_message() -> None:
    client = SearchClient("key", transport=_transport({"references": []}))

    results = client.search("不存在的关键词")

    assert results == []
    assert "没有找到" in client.format("不存在的关键词", results)


def test_registry_executes_search_web() -> None:
    registry = ToolRegistry().register(
        build_search_tool(SearchClient("key", transport=_transport()))
    )

    outcome = registry.execute("searchWeb", json.dumps({"query": "今天日期"}))

    assert outcome.ok is True
    assert "标题1" in outcome.output
    assert "https://example.test/1" in outcome.output


def test_registry_reports_unconfigured_search() -> None:
    registry = ToolRegistry().register(
        build_search_tool(SearchClient("", transport=_transport()))
    )

    outcome = registry.execute("searchWeb", json.dumps({"query": "q"}))

    assert outcome.ok is False
    payload = json.loads(outcome.output)
    assert "baidu_qianfan_api_key" in payload["error"]