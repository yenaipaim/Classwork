<div align="center">

**课程实践项目集 · 宠物医院 MCP 系统 / LLM 对接 / 文档上传 / 命令行对话工具 / 本地文件工具 / Textual 终端智能体 / 上下文压缩 / 会话管理**

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
├── Agent/Practice02/       ← 第五次课：本地文件操作工具扩展
└── Agent/YenaiAgent/       ← 第六~十二次课：core/TUI 分层 + Agent Skills + MCP + 上下文压缩 + 会话/配置
```

| 目录 | 课程 | 简介 | 启动方式 |
|:----:|:----:|------|----------|
| [Pet/](Pet/README.md) | 第 1 次 | Go 宠物医院 + 28 个 MCP 工具 + AI 对话网页 | 双击 `Pet/启动.bat` |
| [LLM_MCP/](LLM_MCP/README.md) | 第 2 次 | 将 AnythingLLM 知识库封装为 MCP 工具 | `python server.py` |
| [LLM_UPLOAD_MCP/](LLM_UPLOAD_MCP/README.md) | 第 3 次 | 文档上传 & 嵌入 AnythingLLM 的网页 | 浏览器直接打开 `index.html` |
| [Agent/Practice01/](Agent/Practice01/README.md) | 第 4 次 | 多轮对话 CLI（流式输出 · 终端转圈动画） | `python main.py` |
| [Agent/Practice02/](Agent/Practice02/README.md) | 第 5 次 | 多轮对话 CLI + 13 个工具（含 10 个本地文件操作） | `python Agent\Practice02\main.py` |
| [Agent/YenaiAgent/](Agent/YenaiAgent/README.md) | 第 6-12 次 | core + tui 分层：Textual 界面、19 个本地工具 + MCP 动态工具与边栏、可切换工作区、Agent Skills、上下文占用条与 `/compact` 压缩、`/` 命令补全、会话事件日志与 `/resume`、全量 `config.ini`、`AGENTS.md` 一次注入 | `python Agent\YenaiAgent\main.py` |

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

> `config.json` 含明文 API Key，**已退出版本库跟踪**（`.gitignore` 忽略），仓库不再分发该文件；
> 文件缺失时服务用内置默认值正常启动，在网页「设置」页填写后会在本地生成。

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
- ⚠️ 演示用的 AnythingLLM Key 写死在 `server.py` 源码里，仅供本地课程实验，不要复用；长期使用应改读环境变量

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
请输入>>> （在这里输入问题）

生成中 \          ← 首个 token 到达前转圈，随后被回复原地覆盖
（AI 回复，流式逐段出现）
请输入>>> （下一轮问题）

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
>
> 该目录保留为课程原始版本；分层重写版见 [Agent/YenaiAgent](Agent/YenaiAgent/README.md)。

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

## Agent/YenaiAgent — 分层重构 TUI 版（第六~十二次课）

> 把 Practice02 重构为 **core + tui** 两层：对话、工具、会话、存档全部收进 `core/`，
> 终端界面换成 **Textual**，后续 Web / Desktop 可直接复用同一套 core。
> 第十次课接入 **MCP 客户端**：启动时读技能目录里的 `.mcp.json`（缺失自动生成模板），
> 把外部 MCP Server 的工具注册成普通函数工具。第十一次课补上 **上下文压缩**：
> TUI 常驻占用条、70% 阈值警告并暂停输入、`/compact` 归档 + 摘要替换、`recallContext` 回查原始记录。
> 第十二次课补上 **会话与配置**：会话事件日志 + `/new` `/resume` `/sessions` `/save` `/export`、
> 全部参数搬进 `config.ini`（首次运行生成完整模板）、MCP 边栏异步加载、`AGENTS.md` 一次注入全程复用。
> 工具 19 个：日期 / 闰年、10 个文件工具、联网搜索 `searchWeb`、网页抓取 `fetchWeb`、
> 本地命令行 `RunCli`、技能加载 `loadSkill`、技能创建 `createSkill`、上下文回查 `recallContext`，外加工具清单。

```powershell
python Agent\YenaiAgent\main.py
```

首次运行若无 `config.ini`，会先在同一目录生成一份**完整模板**（各段都带注释与示例值，
接口 / 密钥 / 模型填 mock 值），弹框提示「改成真实值后重新启动」并退出；改完再运行即进入
TUI。所有可调参数都在这个文件里，代码只提供默认值。常用的几段：

```ini
[llm]
max_tool_rounds = 40      # 单轮工具调用轮数上限（默认 40，触顶保留结果不报错）
max_tokens = 4096         # 单次回复输出上限（被截断时回答末尾会提示）

[search]                  # searchWeb 联网搜索（百度千帆），缺省则搜索返回“未配置”提示
baidu_qianfan_api_key = your-key

[skills]                  # 技能根目录（可多个），缺省用 <启动目录>/.agents/skills
roots = D:\my-skills; F:\yenaipaim\Plugin\.agents\skills
```

`fetchWeb` 抓网页不需要配置，依赖系统自带的 `curl`（Windows 10+ 自带）；技能目录也可以
用 `--skills-dir` 或环境变量 `YENAI_SKILLS_DIRS` 临时指定。

### 分层约定

| 层 | 目录 | 职责 |
|----|------|------|
| core | `core/` | 配置、事件、上下文裁剪、LLM 后端、工具注册表、文件沙箱、会话、存档 |
| tui | `tui/` | Textual App、消息卡片、配置页、中文文案、样式 |
| 入口 | `main.py` | 只调用 `tui.__main__.main()`，可传 `--config` / `--history-dir` / `--workspace` |

依赖方向是单向的：`tui → core`；`core` 不导入 `textual` / `rich` / `tui`，也不使用
`print` / `input` / `sys.exit`，因此可以脱离终端被其他前端调用。

### 界面与操作

- 消息卡片：用户橙色左边条、助手蓝色左边条，正文与角色标签分行
- 工具调用卡片：`工具名(参数)`、✓/✗ 状态、耗时 ms、「参数」「结果」分节
- 状态栏：就绪 / 思考中（带等待秒数与工具调用次数）/ 工具运行 / 正在中断
- 输入框：多行编辑，`Enter` 发送，`Ctrl+J` 换行（增强键盘终端也可用 `Shift+Enter`）
- 命令补全：输入 `/` 弹出带说明的命令候选，继续输入按前缀过滤；↑↓ 选择、Tab 补全
  （带参数命令补出空格，如 `/model `）、Enter 直接执行、Esc 收起
- 上下文占用条：输入框上方常驻「已用 k / 窗口 k（百分比）」，窗口未知时按 128k 并标「默认」，
  达 70% 变黄提示 `/compact`
- 快捷键：`Ctrl+Q` 退出，`Ctrl+C` 中断当前回复（空闲时退出），`Ctrl+L` 清屏
- 命令：`/help` `/new` `/resume` `/sessions` `/save` `/export` `/clear` `/reset` `/compact`
  `/status` `/tools` `/config` `/model` `/workspace` `/skills` `/mcp` `/quit` `/exit`
- MCP 边栏：右侧常驻面板，后台线程连 Server，连上后显示每个 Server 的状态与工具清单
- 工作区：默认为项目目录，`--workspace` 启动指定或 `/workspace` 运行时切换；
  决定文件工具沙箱与 `RunCli` 的工作目录，切换时保留上下文
- 稳定性：状态栏每秒显示等待秒数与工具调用次数；模型空响应、请求失败会明确报错，
  不会静默卡住；`Ctrl+C` 中断（正在执行的工具最长再等约 30 秒）

### Agent Skills 技能加载（第八次课）

按 Agent Skills 规范（`SKILL.md` + YAML frontmatter）实现动态技能加载，自实现解析器，
不引入第三方依赖：

- 启动时以**程序启动目录**扫描技能根目录下的技能子目录，每个子目录的顶层
  `SKILL.md` 声明 `name` 与 `description`；初始化只读这两个字段，正文不进上下文。
- 技能根目录默认是 `<程序启动目录>/.agents/skills/`，可通过 `config.ini` 的
  `[skills] roots`（`;` 分隔、支持多个根）、`--skills-dir` 或环境变量
  `YENAI_SKILLS_DIRS` 指向别处；多根按顺序扫描，同名技能先扫到的生效。
- 技能清单（`- name: description` 列表）注入 System Prompt；模型需要细节时调用
  `loadSkill(name, filename?)`：只给 `name` 返回 `SKILL.md` 全文，给 `filename` 则读取
  技能附带的其他文件（支持相对技能目录 / 相对项目根 / 绝对路径，同名文件列出候选让模型选）。
- 读取严格限制在该技能目录内，越界路径直接拒绝；缺 `SKILL.md`、缺字段或重名的目录
  自动跳过（`session.skills.skipped` 可查）。
- `.agents/` 已加入 `.gitignore`；想版本化自己的技能，删掉该行即可。
- `/skills` 命令可随时查看已加载技能、扫描目录与跳过原因。

完整约定见 [Agent/YenaiAgent/README.md](Agent/YenaiAgent/README.md) 的「技能（Agent Skills）」一节。

### Skill 创建工具 createSkill（第九次课）

前八次课只能「读取已有的技能」，这一课把技能从「手写文件」变成「对话里让 Agent 自己建」：

- 新增 Function Calling 工具 `createSkill(name, skillContext)`。`name` 是技能名，
  `skillContext` 是要写进 `SKILL.md` 的完整内容（frontmatter + 正文）。
- 工具在第一个技能根目录（默认 `.agents/skills/`）下建出 `name` 对应的子目录与
  `SKILL.md`，当轮即登记进技能清单，同一会话马上能用 `loadSkill` 读到，无需重启。
- 技能名统一规范成 Agent Skills 推荐的 kebab-case（小写字母、数字、单个连字符）：
  模型给 `PDF Tools` 会落成 `pdf-tools`；纯中文名无法规范时直接返回错误与可用名单。
- 生成的文件符合 Agent Skills 规范：YAML frontmatter 固定带 `name` 与 `description`，
  `name` 以目录名为准；`description` 缺省时从正文第一条可读文字推导；值里有 `: `、
  以 `-`/`>` 开头等容易破坏 YAML 的情况自动改用折叠块标量；模型自带的其他
  frontmatter 键（如 `license`、`metadata`）原样保留。
- 目标技能已存在（不管是已登记的，还是目录在但缺 `SKILL.md`）一律返回
  `ok=false` 与「已存在」提示，附带现有文件清单，不覆盖任何字节；跨技能根重名同样拒绝。
- `references/`、`scripts/` 等附属文件不由 `createSkill` 生成，仍由模型继续调用
  `create_file`、`edit_text_file` 等文件工具补齐。

### MCP 客户端（第十次课）

- 配置与技能同源：第一个技能根下的 `.mcp.json`（默认 `<启动目录>/.agents/skills/.mcp.json`），
  支持 `stdio`、`streamable_http`（Streamable HTTP）与 `sse` 三种传输；文件不存在时自动
  写入内置模板（PeiHospitalMCP + 两条 disabled 示例），已有配置永不覆盖；
  `YENAI_MCP_CONFIG` 可指定别的文件，设为 `off` 则整体关闭。
- 连上后调用 `list_tools()`，把工具名、描述、参数 Schema 转成 `ToolSpec` 注册进同一个注册表
  （排在本地工具之后），模型看到的就是普通 Function Calling；调用时按内部映射找回 Server 与
  原名，文本、结构化结果、错误原样返回。
- 工具名与本地工具或其它 Server 撞名时自动加 `<Server>__<工具>` 前缀；OpenAI 兼容接口只允许
  ASCII 函数名，纯中文的工具名注册成 `tool_1`、`tool_2`…，中文原名写进描述，模型按描述挑选。
- 单个 Server 配置写错或连不上只影响它自己：启动摘要与 `/mcp` 显示原因，本地工具和其他
  Server 照常可用；stdio Server 随会话退出关闭。
- 模板默认带 `PeiHospitalMCP`（`Pet` 的宠物医院 MCP，`http://127.0.0.1:9000/mcp`，
  28 个工具），另附 stdio 与带鉴权头 HTTP 两条 disabled 示例；生成在技能目录里，
  属于本机文件、不入库。
- 排错先看 `url` 和外壳：`url` 要写全协议头与路径（`http://127.0.0.1:9000/mcp`），
  少协议头会进「配置问题」列表，少了 `/mcp` 会连到根路径失败；最外层漏掉
  `"mcpServers"` 会被当成空配置（0 个 Server、0 条问题），这种情况 `/mcp` 里什么都看不到。

完整格式与字段说明见 [Agent/YenaiAgent/README.md](Agent/YenaiAgent/README.md) 的
「MCP（Model Context Protocol）」一节。

### 上下文压缩与历史检索（第十一次课）

上下文窗口是有限资源。这一课不加向量库、不接 Embedding，只用「归档 + 摘要 + 全文检索」
三件事让 Agent 能在有限窗口里连续做长时间任务：

- **用量监控**：统计口径与实际请求一致——System Prompt + 最近 `history_turns` 轮历史 +
  工具定义；工具调用与结果只在当轮请求里存在、下一轮不再发送，因此不计入。优先用接口
  返回的 usage（再补上这条请求之后才生成的回答，数字不落后一轮），拿不到就本地估算：
  中文 1.6 字 ≈ 1 token、其余 3.5 字符 ≈ 1 token，估算值前面带 `~` 与真实值区分。
  占用条实时显示「已用 / 窗口（百分比）」，窗口未知按 128k 并标注「默认」；
  达到 70% 变黄提示，并暂停接受新的普通提问，直到压缩成功。
- **手动压缩** `/compact`：先把原始上下文完整写入 `.agents/context/20261022-153000.jsonl`
  （角色、内容、工具调用参数、工具结果、消息顺序全保留，编号按时间戳且同秒不撞号），
  归档成功后才调用 LLM 生成约 5,000 tokens 的 Markdown 摘要；摘要替换历史消息并追加一条
  「已归档为 编号 X，需要细节请用 recallContext」的说明，System Prompt 与工具定义原样保留。
  压缩期间不执行任何其它工具，失败则原上下文一条不动，可直接重试。
- **压缩 Prompt**：固定六段结构——用户目标与约束、已完成的工作、当前状态、关键技术信息
  （路径 / 函数 / 配置 / 命令原样保留）、关键决策与原因、下一步任务；要求区分「已验证」与
  「推测」，不把计划写成已完成。
- **`recallContext(id?, text)`**：`text` 必填，`id` 可选；给了编号只查那份归档，否则扫
  `.agents/context/` 下全部文件。纯 Python 全文关键词匹配，返回命中片段、归档编号与位置；
  结果最多 6 条、总长不超过 3,600 字符，避免检索结果再次撑爆上下文。
- 压缩、归档、检索三者互相配合：摘要负责「挡住」细节，检索负责「按需取回」细节。

实现分别在 `core/budget.py`（估算与阈值）、`core/archive.py`（归档与检索）、
`core/compaction.py`（Prompt 与摘要拼装）、`core/recall.py`（工具定义），TUI 侧在
`tui/app.py` 里接占用条、`/compact` 后台任务与输入限制。细节与设计取舍见
[Agent/YenaiAgent/README.md](Agent/YenaiAgent/README.md) 的「上下文压缩与历史检索（第十一次课）」一节。

### 会话、配置与 AGENTS.md（第十二次课）

前十一课的会话只活在内存里，退出即散；这一课把「会话」做成可保存、可恢复、可导出的一等
对象，同时把散落在代码里的数字搬进配置文件。

- **会话事件日志**：每次问答追加到 `.agents/sessions/<编号>.jsonl`（编号 `YYYYMMDD-HHMMSS`，
  同秒补 `-2`）。文件首行是 header（版本 / 编号 / 创建时间 / 模型 / 工作区 / System Prompt），
  之后是 `user` / `assistant` / `tool` 事件；工具事件保留名称、参数、结果与耗时。写入用
  「追加 + 原子替换」，读取时跳过坏行，进程被杀留下的半截 JSON 不会毁掉整个会话。
- **会话命令**：`/new` 先保存当前会话再换新编号；`/save` 立即落盘；`/sessions` 按新→旧列出
  编号、时间、轮数与标题（首条用户消息，压缩过的取摘要首行）；`/resume` 打开列表面板
  （↑↓ 选择、Enter 恢复、Esc 取消，当前会话带 `▶`），恢复时从事件重建上下文并沿用原编号
  继续追加；`/export [目录]` 导出 Markdown；`/status` 汇总编号、模型、上下文、MCP 与 AGENTS.md。
- **配置化**：`core/config.py:AppConfig` 是唯一的默认值来源，`config.ini` 分 `[llm]` `[context]`
  `[session]` `[tools]` `[search]` `[mcp]` `[skills]` 七段覆盖；缺项与空值走默认，类型错误
  直接报 `CONFIG_INVALID` 并指到 `[段] 键名`。`/config` 只改 `[llm]` 三项，其余段原样保留。
- **首次运行模板**：缺少 `config.ini` 时 `render_config_template()` 生成全量注释模板（mock 值），
  弹框提示修改后重启，随后退出，不会带着假配置进聊天界面。
- **MCP 边栏**：`McpHub.start_async()` 在后台线程连接，TUI 先渲染「正在加载 MCP 服务…」，
  连完后经主线程刷新成每个 Server 一行（状态 + 工具数 + 工具名，超出折叠）。连接慢或失败
  都不挡首屏，工具注册仍走 `hub.register_into(registry)`。
- **AGENTS.md 一次注入**：工作区有 `AGENTS.md` 时，会话建好后读取一次，包成带分隔标记的
  项目约定块作为一条 system 消息参与请求，同时原文写入事件日志（`kind="agents_md"`）；
  之后每轮 System Prompt 逐字不变（提示词缓存可命中），文件删掉后用 `/resume` 也能从日志
  恢复。超过 `agents_md_max_chars`（默认 20000）截断并注明。

实现分别在 `core/sessions.py`（事件日志与恢复）、`core/agentsmd.py`（读取与包装）、
`core/config.py`（字段化配置与模板）、`tui/screens/`（首次运行提示、会话列表）、
`tui/widgets/sidebar.py`（MCP 边栏）；细节见
[Agent/YenaiAgent/README.md](Agent/YenaiAgent/README.md) 的「第十二次课：会话、配置与 MCP 边栏」。

### 测试

```powershell
cd Agent\YenaiAgent
python -m pytest tests -q
```

覆盖配置读写、上下文裁剪、工具注册表、文件沙箱越界与工作区切换、会话事件流、
存档格式、Skill 发现与加载（含多根扫描与 `[skills]` 配置）、`createSkill` 的名称规范化
与 `SKILL.md` 生成（含已存在不覆盖）、MCP 配置解析与技能目录模板生成、工具命名、真实 stdio MCP Server 的
list / call 往返，上下文压缩全链路（token 估算与默认 128k 标记、归档编号与字段顺序、
`path_for` 路径穿越拦截、`recallContext` 命中与截断、摘要替换后历史只剩摘要 + 归档说明、
压缩失败保留原上下文、70% 阈值触发警告并暂停输入、占用口径与 `~` 估算标记、占用条文案），
`/` 命令补全（展开、过滤、Tab 补全、Enter 执行、Esc 收起、只读不弹），会话事件日志
（header / 同秒不撞号 / 只取对话消息 / 压缩点重开 / 列表排序 / 坏行跳过 / 路径穿越拦截 /
Markdown 导出），AGENTS.md 一次注入与恢复，`/new` `/save` `/resume` `/sessions` `/export`
`/status` `/tools` 的 TUI 行为与 MCP 边栏占位，分层约束（core 不得依赖 UI）以及 TUI 无头测试，
当前 243 个用例。

跑测试先装：`pip install pytest pytest-asyncio`（或 `pip install -r Agent\YenaiAgent\requirements.txt` 一次装齐）。

---

## 通用要求

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | MCP 服务 / Web 后端 |
| Go | 1.22+ | 仅重新编译 Go 后端时需要（已有编译好的 exe） |
| Node.js | 不需要 | 前端为原生 JS，无构建步骤 |

Python 依赖：

```powershell
pip install mcp httpx uvicorn openai textual trafilatura
```

> `openai` 供 `Agent/Practice01`、`Agent/Practice02` 与 `Agent/YenaiAgent` 使用；
> `textual` / `trafilatura` 仅 `Agent/YenaiAgent` 需要（后者用于 `fetchWeb`）；
> `mcp` / `httpx` / `uvicorn` 供 `Pet` 与 `LLM_MCP` 使用。

### 不上传的本地文件

以下都是运行数据或敏感配置，已在根 `.gitignore` 排除（不会进入仓库）：

| 模式 | 内容 |
|------|------|
| `config.ini` | 各 Agent 的接口地址 / API 密钥 |
| `config.json` | `Pet/web` 的 AI 接口密钥（明文 Key） |
| `chat_history/` | 每次运行的对话存档 |
| `.agents/` | YenaiAgent 的 Agent Skills 本地技能目录（默认 `.agents/skills/`） |
| `.agents/context/` | `/compact` 生成的原始上下文归档（`*.jsonl`，含完整对话，同样不应上传） |
| `data/` | 临时图片与模板 |
| `.mcp.json` | 本机 MCP Server 配置（放在技能目录里，首次启动自动生成模板） |
| `.env`、`*.pem`、`*.key` | 环境变量与密钥文件 |
| `*.log`、`*.tmp`、`*.bak` | 日志与临时备份 |
| `.DS_Store`、`Thumbs.db`、`.idea/`、`.vscode/` | 系统与编辑器杂项 |
| `__pycache__/`、`*.py[cod]`、`.pytest_cache/`、`.venv/` | 缓存与虚拟环境 |

> MCP 配置：不再随仓库提交模板文件——首次运行会在技能目录里自动生成 `.mcp.json`
> （PeiHospitalMCP + 两条 disabled 示例），按本机改完重启即可；该目录已被忽略，不会上传。
> 也可用环境变量 `YENAI_MCP_CONFIG` 指向另一份文件。

已跟踪的文件改 `.gitignore` 不会自动移除，需要用 `git rm --cached <文件>` 解除跟踪。
（`Pet/web/config.json` 已按此处理，本地文件保留。）

---

## License

MIT
