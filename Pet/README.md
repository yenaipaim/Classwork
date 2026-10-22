# Pet Hospital AI System

本地宠物医院演示系统，由 Go REST API、Python MCP 服务和浏览器 AI 对话界面组成。
三个服务可在同一个终端中一键启动。

## 快速启动

双击 `启动.bat`，或在当前目录执行：

```powershell
python start.py
```

首次运行前安装 Python 依赖：

```powershell
pip install -r web\requirements.txt
pip install -e pet_hospital_mcp
```

启动完成后浏览器会打开 <http://127.0.0.1:3000>。

## 服务

| 服务 | 地址 | 入口 | 说明 |
|------|------|------|------|
| Web / AI 对话 | <http://127.0.0.1:3000> | `web/server.py` | 静态页面、AI 代理、MCP 工具代理 |
| MCP | <http://127.0.0.1:9000/mcp> | `mcp_launcher.py` | 向 AI 暴露 28 个中文工具 |
| Go REST API | <http://127.0.0.1:8080> | `windows/pethospital.exe` | 宠物档案、病历、收费和统计数据 |

数据保存在单文件数据库 `windows/data/pet.db` 中。

## 使用流程

1. 打开 Web 页面中的“设置”。
2. 填写 OpenAI 兼容的 Base URL、API Key 和模型名称。
3. 刷新 MCP 连接，并勾选允许 AI 调用的工具。
4. 回到“对话”页面，用自然语言查询或修改宠物数据。

## 目录结构

```text
Pet/
├── 启动.bat
├── start.py
├── mcp_launcher.py
├── windows/
│   ├── pethospital.exe
│   ├── data/pet.db
│   ├── LICENSE
│   ├── README.md
│   └── README-Windows.md
├── pet_hospital_mcp/
│   ├── src/pet_hospital_mcp/
│   └── README.md
└── web/
    ├── server.py
    ├── config.json
    ├── requirements.txt
    ├── frontend/index.html
    └── README.md
```

更详细的 Go API 说明见 [windows/README.md](windows/README.md)，
MCP 服务说明见 [pet_hospital_mcp/README.md](pet_hospital_mcp/README.md)，
Web 服务说明见 [web/README.md](web/README.md)。

> 本仓库只附带已编译的 **Windows 可执行文件**与数据库；Go 源码、`Makefile`、
> `build.sh`、发行 ZIP 都不在本仓库。`windows/README.md` 中「从源码编译 / 构建发布」
> 两节只作上游 Go 项目参考。

## 配置

Web 设置保存在 `web/config.json`，其中包括 AI 接口信息和启用的 MCP 工具列表。
该文件可能包含 API Key，不应提交到公共仓库。

启动脚本支持以下环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WEB_PORT` | `3000` | Web 服务端口 |
| `MCP_PORT` | `9000` | MCP 服务端口 |
| `MCP_URL` | `http://127.0.0.1:9000` | Web 服务访问 MCP 的地址 |
| `PET_HOSPITAL_BASE_URL` | `http://127.0.0.1:8080` | MCP 访问 Go API 的地址 |

## 测试

```powershell
cd pet_hospital_mcp
pytest -q
```

## 本地运行说明

- 服务只监听本机地址，适合课程演示和本地开发。
- 系统没有登录和鉴权，不应直接暴露到公网。
- `start.py` 退出时会尝试终止它启动的三个子进程。

