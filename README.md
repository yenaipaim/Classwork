<div align="center">

**课程实践项目集 · 宠物医院 MCP 系统 / LLM 对接 / 文档上传 / 命令行对话工具 / 本地文件操作工具**

</div>

---

## 项目结构

```
Anything/
├── README.md               ← 本文件
├── Pet/                    ← 第一次课：宠物医院完整系统
├── LLM_MCP/                ← 第二次课：AnythingLLM MCP 桥接
├── LLM_UPLOAD_MCP/         ← 第三次课：AnythingLLM 文档上传页
├── Agent/Practice01/       ← 第四次课：多轮对话命令行工具
└── Agent/Practice02/       ← 第五次课：本地文件操作工具扩展
```

| 目录 | 课程 | 简介 | 启动方式 |
|:----:|:----:|------|----------|
| [Pet/](Pet/README.md) | 第 1 次 | Go 宠物医院 + 28 个 MCP 工具 + AI 对话网页 | 双击 `Pet/启动.bat` |
| [LLM_MCP/](LLM_MCP/README.md) | 第 2 次 | 将 AnythingLLM 知识库封装为 MCP 工具 | `python server.py` |
| [LLM_UPLOAD_MCP/](LLM_UPLOAD_MCP/README.md) | 第 3 次 | 文档上传 & 嵌入 AnythingLLM 的网页 | 浏览器直接打开 `index.html` |
| [Agent/Practice01/](Agent/Practice01/README.md) | 第 4 次 | 多轮对话 CLI（流式输出 · 终端转圈动画） | `python main.py` |
| [Agent/Practice02/](Agent/Practice02/README.md) | 进阶 | 多轮对话 CLI + 13 个工具（含 10 个本地文件操作） | `python Agent\Practice02\main.py` |

---

## Pet — 宠物医院 AI 系统（第 1 次课）

> 一个完整的本地宠物医院管理系统：**Go REST API + Python MCP 服务 + AI 对话网页**，
> 通过自然语言即可查询、修改宠物医院数据。

### 架构

```
┌──────────────────────────────────────────────────────┐
│                浏览器网页 (port 3000)                  │
│     设置页（AI 配置 / MCP 开关）+ 对话页（AI 聊天）      │
└──────────────────┬───────────────────────────────────┘
                   │ HTTP
┌──────────────────▼───────────────────────────────────┐
│              Web 后端 (Python, port 3000)             │
│     静态托管 · AI 流式代理 · MCP 会话管理 · 配置持久化   │
└──────┬───────────────────────────────┬───────────────┘
       │ AI SSE 流                     │ MCP JSON-RPC
┌──────▼──────────┐          ┌─────────▼───────────────┐
│  自定义 AI 接口   │          │  MCP 服务 (port 9000)    │
│ (OpenAI 兼容)    │          │  28 个中文命名工具        │
└─────────────────┘          └─────────┬───────────────┘
                                       │ REST
                             ┌─────────▼───────────────┐
                             │  Go 宠物医院 (port 8080)  │
                             │  29 个 REST API 接口      │
                             │  单文件数据库 data/pet.db  │
                             └─────────────────────────┘
```

### 一键启动

```powershell
# 双击即可
Pet\启动.bat
```

或手动分步启动：

```powershell
# 1. Go 后端 (端口 8080)
cd Pet\windows
.\pethospital.exe

# 2. MCP 服务 (端口 9000)
python Pet\mcp_launcher.py

# 3. Web 服务 (端口 3000)
python Pet\web\server.py
```

启动后打开 **<http://127.0.0.1:3000>**。

### 使用流程

1. **设置页** → 填写 AI 接口（Base URL / API Key / 模型）
2. **设置页** → 点击「刷新 MCP 连接」，勾选要启用的工具（默认全关）
3. **对话页** → 直接输入自然语言，如「查询所有金毛犬」「给旺财添加一条病历」

### 28 个 MCP 工具

| 类别 | 工具名 |
|------|--------|
| 档案 | 查询宠物列表 · 获取宠物详情 · 新增宠物 · 全量更新宠物 · 局部更新宠物 · 删除宠物 |
| 查询 | 全文搜索 · 按主人查询 · 按医生查询 · 按种类查询 · 按疾病查询 · 按状态查询 · 消费排行榜 · 按花费区间查询 |
| 病历 | 查看病历 · 添加病历 |
| 收费 | 查看收费明细 · 添加收费 · 费用汇总 |
| 统计 | 经营统计 · 元数据字典 |
| 管理 | 批量新增 · 批量删除 · 导出数据 · 压实数据库 · 生成模拟数据 · 接口清单 · 健康检查 |

### 配置说明

| 文件 | 说明 |
|------|------|
| `Pet/web/config.json` | AI 接口（`baseUrl` / `apiKey` / `model`）与已启用的 MCP 工具列表 |

环境变量（可选）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WEB_PORT` | `3000` | Web 服务端口 |
| `MCP_PORT` | `9000` | MCP 服务端口 |
| `MCP_URL` | `http://127.0.0.1:9000` | Web 后端访问 MCP 的地址 |
| `PET_HOSPITAL_BASE_URL` | `http://127.0.0.1:8080` | MCP 访问 Go 后端的地址 |

### 目录详情

```
Pet/
├── 启动.bat                # 一键启动入口
├── start.py                # 启动编排（Go + MCP + Web）
├── mcp_launcher.py         # MCP 独立启动入口
├── windows/
│   ├── pethospital.exe     # Go 宠物医院（已内嵌网页）
│   └── data/pet.db         # 单文件数据库（约 1000 条测试数据）
├── pet_hospital_mcp/
│   ├── src/pet_hospital_mcp/
│   │   ├── server.py       # MCP 服务（28 个工具注册）
│   │   ├── rest_client.py  # 通用 HTTP 客户端（GET/POST/PUT/PATCH/DELETE）
│   │   └── tools/          # 工具实现（按功能分 7 个模块）
│   └── tests/              # pytest 测试
└── web/
    ├── server.py           # Web 后端（静态托管 + AI/MCP 代理）
    └── frontend/index.html # 单页前端（设置页 + 对话页）
```

### 技术栈

- **后端**：Go 标准库（零第三方依赖）· Python 3.10+ · `mcp` SDK · `uvicorn`
- **前端**：原生 HTML / CSS / JavaScript（单文件，无构建步骤）
- **协议**：MCP Streamable HTTP · OpenAI 兼容 Chat Completions SSE

---

## LLM_MCP — AnythingLLM MCP 桥接（第 2 次课）

将 **AnythingLLM** 知识库封装为一个 MCP 工具，供 AI 客户端调用。

```powershell
python LLM_MCP\server.py
```

- **工具**：`query_mods(question)` — 向 AnythingLLM 的 `mods` 工作区提问，返回基于文档的 AI 回答
- **依赖**：本地运行的 AnythingLLM（默认 `http://localhost:3001`）
- **传输**：Streamable HTTP

---

## LLM_UPLOAD_MCP — 文档上传页（第 3 次课）

一个纯前端页面，将本地文档上传到 AnythingLLM 并完成向量嵌入。

```
浏览器直接打开 LLM_UPLOAD_MCP/index.html
```

- 支持多文件批量上传
- 自动获取工作区 → 上传文档 → 触发嵌入（embedding）
- 实时显示每一步状态

---

## Agent/Practice01 — 多轮对话 CLI（第 4 次课）

> 单文件命令行对话工具：**纯终端界面 + 流式输出 + 多轮上下文**，
> 兼容任意 OpenAI 格式接口。无 emoji，无第三方界面库。

```powershell
python Agent\Practice01\main.py
```

### 特性

| 能力 | 说明 |
|------|------|
| 多轮上下文 | 保留在内存中，退出即清空；只发送最近 **10 轮**（`HISTORY_TURNS` 可调） |
| 流式输出 | `stream=True` 逐段打印，首字到达即开始显示 |
| 等待动画 | 每次请求（含工具调用后的续问）在首个 token 到达前原地转圈（`\` `丨` `/` `-` 四帧），超过 3 秒附加已等待秒数，到达后自动擦除，不残留空行；秒数只是显示进度，不影响请求本身 |
| 配置向导 | 首次运行若无 `config.ini`，交互式询问 BaseURL / APIKey / ModelName 并写入 |
| 退出方式 | 输入 `/exit`，或 Ctrl+C / Ctrl+D |
| 错误处理 | 失败统一提示 `额度已经耗尽或者配置信息错误`；失败或中断的轮次**不写入上下文** |
| 工具调用 | 模型可调用 `get_date` 与 `isLeapyear`；单轮内最多连续 5 次（`MAX_TOOL_ROUNDS`），执行结果同时打印并写入历史 |
| 历史记录 | 每次运行在 `chat_history/` 下生成一个带时间戳的 `.txt`，逐轮追加成功的问答与工具调用 |

### 可用工具

| 工具 | 参数 | 说明 |
|------|------|------|
| `get_date` | 无 | 读取本机当前时间（执行系统 `date` 命令，无 `date` 时退回 Python 实现） |
| `isLeapyear` | `year`（整数） | 判断年份是否为闰年，Python 规则计算：能被 4 整除，整百年需能被 400 整除 |

### 交互示例

```
等待用户输入：

（在这里输入问题）

生成中 \          ← 首个 token 到达前转圈，随后被回复原地覆盖
（AI 回复，流式逐段出现）
等待用户输入：

```

### 配置说明

| 文件 | 说明 |
|------|------|
| `Agent/Practice01/config.ini` | `[llm]` 段下的 `base_url` / `api_key` / `model_name`，首次运行自动生成 |
| `Agent/Practice01/chat_history/*.txt` | 每次运行的对话存档，文件名形如 `20261019_092847.txt` |

> `config.ini` 内含 API Key、`chat_history/` 含对话内容，均已在**根目录 `.gitignore`** 中排除，不会提交到仓库。

### 历史记录

每次启动会新建一个文件（`chat_history/年月日_时分秒.txt`），只追加**成功完成**的问答（含本轮内的工具调用）；失败、中断、半截断流的轮次不写入。格式：

```text
# 模型：mimo-v2.6-flash
# 开始：2026-10-19 09:28:47

[09:28:47] 用户
现在几点

[工具] get_date  09:28:48
参数：{}
结果：2026-10-19 09:28:48 星期日（UTC+0800）

[回复]
现在是 9 点 28 分。
```

该文件仅作本地存档，**不会在启动时回读**——上下文仍只保留当次运行的内存内容。

### 可调参数（`main.py` 顶部常量）

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `SYSTEM_PROMPT` | `回答简洁，减少副词，不用 emoji。` | 系统提示词 |
| `MAX_TOKENS` | `512` | 单次回答上限 |
| `HISTORY_TURNS` | `10` | 保留的上下文轮数 |
| `REQUEST_TIMEOUT` | `60.0` | 单次请求超时（秒） |
| `EXIT_COMMAND` | `/exit` | 退出指令 |
| `SPINNER_INTERVAL` | `0.12` | 转圈动画帧间隔（秒） |
| `HISTORY_DIR` | `chat_history` | 历史记录目录（与 `main.py` 同目录） |

### 依赖

```powershell
pip install openai
```

---

## Agent/Practice02 — 本地文件操作 CLI(第五次课)

> 在 `Agent/Practice01` 的多轮对话、流式输出和工具调用基础上，
> 增加一组受项目目录约束的本地文件操作工具。

```powershell
python Agent\Practice02\main.py
```

首次运行时，如果同目录下没有 `config.ini`，程序会交互式询问
BaseURL、APIKey 和 ModelName 并保存配置。输入 `/exit` 退出。

### 文件结构

```text
Agent/Practice02/
├── main.py            # CLI 入口、对话循环、工具注册与执行分发
├── file_tools.py      # 10 个本地文件工具、路径校验与文本格式处理
├── config.ini         # 本地模型配置（含 API Key，不提交）
└── chat_history/      # 每次运行的问答与工具调用存档（不提交）
```

`main.py` 在导入本地模块前关闭了字节码缓存写入，因此正常运行不会生成
`__pycache__`。退出后，当前对话历史仍会按运行时间写入 `chat_history/`。

### 与 Practice01 的区别

| 能力 | Practice01 | Practice02 |
|------|------------|------------|
| 对话与流式输出 | 支持 | 支持 |
| 日期与闰年工具 | 2 个 | 2 个 |
| 本地文件工具 | 无 | 10 个 |
| 工具清单 | 无 | `list_tools` |
| 工具总数 | 2 个 | 13 个 |
| 路径范围 | 不涉及文件操作 | 限定在 `Agent/Practice02` |

### 工具清单

| 工具 | 参数 | 说明 |
|------|------|------|
| `get_date` | 无 | 获取本机日期、时间、星期和 UTC 偏移 |
| `isLeapyear` | `year`（整数） | 判断指定年份是否为闰年 |
| `get_current_working_directory` | 无 | 返回当前进程工作目录和项目根目录 |
| `list_directory_contents` | `directory` | 列出指定目录的直接子文件和子目录，不递归 |
| `get_file_type` | `path` | 返回扩展名、MIME 类型、是否纯文本及文件大小 |
| `read_text_file` | `path` | 读取纯文本文件，支持 UTF-8、UTF-16、GB18030 等编码 |
| `create_file` | `directory`、`filename` | 在已有目录下创建空文件，不覆盖同名文件 |
| `edit_text_file` | `path`、`content` | 用完整的新内容替换纯文本文件 |
| `create_directory` | `directory` | 创建目录，缺少的父目录会一并创建 |
| `delete_directory` | `directory` | 递归删除目录及其中全部内容 |
| `delete_file` | `path` | 删除指定文件 |
| `rename_path` | `path`、`new_name` | 在同一目录内重命名文件或目录 |
| `list_tools` | 无 | 列出当前注册的全部工具名称和描述 |

### 路径与文件安全

- 文件路径可以是相对路径或绝对路径，但最终必须位于 `Agent/Practice02` 内。
- 路径越界、通过符号链接指向项目外时会被拒绝。
- `delete_directory` 支持删除非空目录，但不能删除项目根目录。
- `rename_path` 只能在同一目录内改名，不能覆盖已有文件或目录。
- 读取和编辑仅支持纯文本格式；二进制内容会被拒绝。
- 单个文本文件读取上限为 **2 MB**。
- `edit_text_file` 会完整替换文件内容，不会自动合并或追加。
- `list_directory_contents` 只列出当前层级的直接内容，不递归遍历。

### 配置与历史记录

| 文件 | 说明 |
|------|------|
| `Agent/Practice02/config.ini` | `[llm]` 段下的 `base_url` / `api_key` / `model_name` |
| `Agent/Practice02/chat_history/*.txt` | 每次运行生成的问答和工具调用存档 |

配置、历史记录和 `__pycache__` 均属于本地运行产物，不应提交到仓库。

---

## 通用要求

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | MCP 服务 / Web 后端 |
| Go | 1.22+ | 仅重新编译 Go 后端时需要（已有编译好的 exe） |
| Node.js | 不需要 | 前端为原生 JS，无构建步骤 |

Python 依赖：

```powershell
pip install mcp httpx uvicorn openai
```

> `openai` 供 `Agent/Practice01` 与 `Agent/Practice02` 使用；
> `mcp` / `httpx` / `uvicorn` 供 `Pet` 与 `LLM_MCP` 使用。

---

## License

MIT
