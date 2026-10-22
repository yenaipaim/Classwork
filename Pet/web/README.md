# Pet Web 服务

宠物医院系统的浏览器入口。服务同时负责静态页面托管、AI 接口代理和 MCP 工具代理。

## 启动

```powershell
pip install -r requirements.txt
python server.py
```

默认地址为 <http://127.0.0.1:3000>。

通常不需要单独启动本服务，根目录的 `start.py` 会负责启动 Go API、MCP 和 Web。

## 目录

```text
web/
├── server.py           # HTTP 服务与 AI/MCP 代理
├── config.json         # 本地运行配置
├── requirements.txt    # Python 依赖
└── frontend/index.html # 单页前端
```

前端为单文件 `frontend/index.html`（原生 HTML/CSS/JS，无构建步骤），通过上表的
HTTP 接口与后端交互，包含「设置」与「对话」两个页面。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WEB_PORT` | `3000` | Web 服务监听端口 |
| `MCP_URL` | `http://127.0.0.1:9000` | MCP 服务地址 |

## HTTP 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/config` | 读取 AI 与 MCP 配置 |
| `POST` | `/api/config` | 保存 AI 与 MCP 配置 |
| `GET` | `/api/mcp/tools` | 获取页面展示的工具名称列表 |
| `POST` | `/api/mcp/discover` | 从 MCP 服务发现工具及参数定义 |
| `POST` | `/api/mcp/call` | 调用指定 MCP 工具 |
| `POST` | `/api/ai/stream` | 代理 OpenAI 兼容的流式对话请求 |

## 配置与安全

- `config.json` 保存 AI Base URL、API Key、模型和已启用工具。
- API Key 以明文保存在本地文件中，不应提交或分享。
- 服务没有鉴权，只适合在本机或可信内网使用。

## 相关文档

- 系统总览：[../README.md](../README.md)
- Go API 接口：[../windows/README.md](../windows/README.md)
- MCP 服务：[../pet_hospital_mcp/README.md](../pet_hospital_mcp/README.md)

