"""网络搜索工具：调用百度千帆「智能搜索生成」接口。

这一层只做一件事：把关键词变成一组带标题、链接、日期和摘要的网页结果，
再用一段模型容易读的文本交回去。配置缺失、网络失败、接口报错都转成
清晰的中文提示，由注册表包装成 ``ok=False`` 的工具结果。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..constants import SEARCH_ENDPOINT, SEARCH_MAX_TOP_K, SEARCH_TOP_K, SEARCH_TIMEOUT
from ..errors import ToolError
from .spec import ToolSpec

# (url, headers, body, timeout) -> (status, text)；测试里可替换成假实现
Transport = Callable[[str, Mapping[str, str], bytes, float], tuple[int, str]]

# 单条摘要最多保留的字符数，避免一条结果就吃掉大半上下文
SNIPPET_LIMIT = 400


@dataclass(frozen=True, slots=True)
class SearchResult:
    """一条网页结果。"""

    title: str
    url: str
    snippet: str = ""
    date: str = ""


class SearchClient:
    """百度千帆搜索的薄封装。"""

    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = SEARCH_ENDPOINT,
        timeout: float = SEARCH_TIMEOUT,
        transport: Transport | None = None,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._endpoint = endpoint or SEARCH_ENDPOINT
        self._timeout = timeout
        self._transport = transport or _post_json

    def search(self, query: str, count: int | None = None) -> list[SearchResult]:
        """执行一次搜索；任何失败都抛 :class:`ToolError`。"""
        text = query.strip() if isinstance(query, str) else ""
        if not text:
            raise ToolError("参数错误：query 不能为空")
        if not self._api_key:
            raise ToolError(
                "未配置搜索服务：请在 config.ini 的 [search] 段填写 "
                "baidu_qianfan_api_key 后重启程序"
            )

        limit = _clamp_count(count)
        payload = {
            "messages": [{"role": "user", "content": text}],
            "stream": False,
        }
        status, body = self._call(payload)
        data = _parse_body(body)
        _raise_business_error(data)

        references = data.get("references") or []
        if not isinstance(references, list):
            raise ToolError("搜索 API 返回格式异常：references 不是数组")

        results = [
            _to_result(item) for item in references if isinstance(item, Mapping)
        ]
        results = [item for item in results if item.title and item.url]
        return results[:limit]

    def format(self, query: str, results: list[SearchResult]) -> str:
        """把结果整理成给模型看的文本。"""
        text = query.strip() if isinstance(query, str) else query
        if not results:
            return "没有找到与“%s”相关的网页结果。" % text
        lines = ["搜索“%s”返回 %d 条结果：" % (text, len(results))]
        for index, item in enumerate(results, 1):
            lines.append("")
            lines.append("%d. %s" % (index, item.title))
            lines.append("   链接：%s" % item.url)
            if item.date:
                lines.append("   日期：%s" % item.date)
            if item.snippet:
                lines.append("   摘要：%s" % item.snippet)
        return "\n".join(lines)

    def _call(self, payload: Mapping[str, Any]) -> tuple[int, str]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": "Bearer " + self._api_key,
            "Content-Type": "application/json",
        }
        try:
            status, text = self._transport(self._endpoint, headers, body, self._timeout)
        except urllib.error.HTTPError as exc:
            status, text = exc.code, _read_error_body(exc)
        except urllib.error.URLError as exc:
            raise ToolError("搜索请求失败：无法连接搜索服务（%s）" % exc.reason) from exc
        except TimeoutError as exc:
            raise ToolError("搜索请求超时：%s" % exc) from exc

        if status != 200:
            raise ToolError(
                "搜索 API 返回 HTTP %d：%s" % (status, _describe_error(text))
            )
        return status, text


def build_search_tool(client: SearchClient) -> ToolSpec:
    """把搜索客户端包成一个函数调用工具。"""

    def handler(query: str, count: int | None = None) -> str:
        results = client.search(query, count)
        return client.format(query, results)

    return ToolSpec(
        name="searchWeb",
        description=(
            "联网搜索：检索互联网上的实时信息，返回网页标题、链接、日期与内容摘要。"
            "适合查询新闻、行情、时效数据，或训练数据里没有的最新事实。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词或完整问题"},
                "count": {
                    "type": "integer",
                    "description": "返回结果条数，默认 5，最多 10",
                    "minimum": 1,
                    "maximum": SEARCH_MAX_TOP_K,
                },
            },
            "required": ["query"],
        },
        handler=handler,
    )


def _post_json(
    url: str, headers: Mapping[str, str], body: bytes, timeout: float
) -> tuple[int, str]:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", "replace")


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read()
    except Exception:  # 读不到错误体时只保留状态码
        return ""
    return raw.decode("utf-8", "replace") if raw else ""


def _parse_body(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text or "")
    except json.JSONDecodeError as exc:
        snippet = (text or "").strip().replace("\n", " ")[:120]
        raise ToolError("搜索 API 返回了无法解析的内容（%s）：%s" % (exc, snippet)) from exc
    if not isinstance(data, dict):
        raise ToolError("搜索 API 返回格式异常：顶层不是对象")
    return data


def _raise_business_error(data: Mapping[str, Any]) -> None:
    for key in ("error_code", "err_code", "code"):
        code = data.get(key)
        if code in (None, 0, "0", ""):
            continue
        message = (
            data.get("error_msg")
            or data.get("err_msg")
            or data.get("message")
            or "未知错误"
        )
        raise ToolError("搜索 API 返回错误（%s）：%s" % (code, message))

    error = data.get("error")
    if isinstance(error, Mapping):
        message = error.get("message") or error.get("code") or "未知错误"
        raise ToolError("搜索 API 返回错误：%s" % message)


def _describe_error(text: str) -> str:
    try:
        data = json.loads(text or "")
    except json.JSONDecodeError:
        data = None
    if isinstance(data, Mapping):
        message = (
            data.get("error_msg")
            or data.get("err_msg")
            or data.get("message")
            or data.get("error")
        )
        code = data.get("error_code") or data.get("err_code") or data.get("code")
        if message:
            return "%s（%s）" % (message, code) if code not in (None, "") else str(message)
    body = (text or "").strip().replace("\n", " ")
    return body[:200] or "无错误详情"


def _to_result(item: Mapping[str, Any]) -> SearchResult:
    title = str(item.get("title") or item.get("web_anchor") or "").strip()
    url = str(item.get("url") or "").strip()
    snippet = _clean_snippet(item.get("content") or item.get("snippet"))
    date = str(item.get("date") or "").strip()
    return SearchResult(title=title, url=url, snippet=snippet, date=date)


def _clean_snippet(value: Any) -> str:
    if not value:
        return ""
    text = " ".join(str(value).split())
    if len(text) > SNIPPET_LIMIT:
        text = text[:SNIPPET_LIMIT].rstrip() + "…"
    return text


def _clamp_count(count: Any) -> int:
    try:
        value = int(count)
    except (TypeError, ValueError):
        return SEARCH_TOP_K
    return max(1, min(SEARCH_MAX_TOP_K, value))