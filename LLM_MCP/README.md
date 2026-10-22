# AnythingLLM MCP Bridge

将 AnythingLLM 的 `mods` 工作区封装成一个 MCP 工具，供支持 Streamable HTTP
的 MCP 客户端调用。

## 功能

工具名：`query_mods`

| 参数 | 类型 | 说明 |
|------|------|------|
| `question` | string | 向 `mods` 工作区提出的问题 |

工具会把问题发送到 AnythingLLM 的流式对话接口，累积 `textResponseChunk`
和 `textResponse` 内容，然后返回完整文本。

## 前置条件

- AnythingLLM 运行在 <http://localhost:3001>
- 已创建 `mods` 工作区并完成文档嵌入
- Python 3.10+

## 安装与启动

```powershell
pip install mcp httpx
python server.py
```

依赖 `mcp` 2.x（`from mcp.server import MCPServer`）与 Python 3.10+。
服务使用 MCP Streamable HTTP 传输。默认 MCP 地址由 `mcp.run("streamable-http")`
决定，通常为 <http://127.0.0.1:8000/mcp>，请以启动日志为准。

## 配置

连接参数位于 `server.py` 顶部：

```python
ANYTHINGLLM_BASE = "http://localhost:3001/api/v1"
ANYTHINGLLM_KEY = "..."
WORKSPACE_SLUG = "mods"
```

运行前请将 API Key 替换为自己的 AnythingLLM 密钥。不要提交真实密钥。

> 仓库内的 `server.py` 自带一个课程演示用的 Key（已随代码提交），仅用于本地实验；
> 请勿在真实环境复用，也建议改用环境变量读取。

## 直接请求 AnythingLLM

服务调用以下接口：

```text
POST /api/v1/workspace/mods/stream-chat
```

请求模式为 `query`，超时时间为 120 秒。

## 安全说明

- 当前实现把 API Key 写在源码中，只适合本地课程演示。
- AnythingLLM 和本服务都不应直接暴露到公网。
- 如果要长期使用，应改为从环境变量或本地配置文件读取密钥。

