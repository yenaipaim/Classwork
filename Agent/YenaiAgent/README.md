# YenaiAgent

把 `Agent/Practice02` 的单文件 Agent 改造成 **core + TUI 分层** 的项目：
业务逻辑全部集中在 `core/`，终端界面用 [Textual](https://textual.textualize.io/)，以后加
Web / Desktop 界面时只需再写一个薄薄的适配层。

## 目录结构

```
YenaiAgent/
├── core/                 # 核心层：不依赖任何界面技术
│   ├── config.py         # AppConfig / ConfigStore（config.ini 读写）
│   ├── constants.py      # 系统提示词、上下文轮数、工具轮数上限等默认值
│   ├── context.py        # 消息裁剪：system + 最近 N 轮 + 当前问题
│   ├── errors.py         # ErrorCode / AgentError / ConfigError / LlmRequestError / ToolError
│   ├── events.py         # 一轮问答对外暴露的事件（frozen dataclass）
│   ├── factory.py        # 唯一装配点：create_session(...)
│   ├── paths.py          # 包根、默认配置、默认存档目录、默认沙箱根
│   ├── skills.py         # Agent Skills：SKILL.md 扫描、清单注入、loadSkill / createSkill
│   ├── session.py        # AgentSession / CancelToken：流式、工具循环、存档提交
│   ├── transcript.py     # chat_history/*.txt 存档（格式与旧版一致）
│   ├── llm/              # 后端协议、请求/流式块类型、工具调用收集器
│   ├── mcp/              # MCP 客户端：.mcp.json 解析、连接（stdio / HTTP / SSE）、工具注册
│   └── tools/            # ToolSpec / ToolRegistry / 内置工具 / 文件工具（沙箱根注入）
├── tui/                  # 终端界面层：只做输入、展示与命令
│   ├── app.py            # YenaiApp：线程模型、流式刷新、斜杠命令
│   ├── i18n.py           # 全部中文文案与错误码 -> 文案映射
│   ├── screens/          # 配置弹窗（全中文）
│   ├── widgets/          # 消息卡片、可折叠的工具调用卡片、多行输入框
│   ├── styles.tcss       # 界面样式（角色色条、工具卡片配色）
│   └── __main__.py       # python -m tui
├── tests/                # 无网络测试：FakeBackend + Textual run_test
├── main.py               # python main.py
├── pyproject.toml        # 打包、入口点、pytest 配置
├── requirements.txt      # 依赖清单（运行 + 测试，装这一份即可）
├── architecture.mmd      # 分层与依赖方向图
└── .agents/skills/       # 本机技能目录；MCP 配置 .mcp.json 也在其中（首次启动生成模板）
```

`config.ini`、`chat_history/`、本地技能目录 `.agents/` 与各类缓存由**仓库根目录**的
`.gitignore` 统一忽略，不会提交到仓库。MCP 配置 `.mcp.json` 就放在技能目录里（本机文件，
同样不入库）：首次启动时自动生成模板，之后按本机情况增删 Server 即可。不要把私有
endpoint 或密钥写进会提交的文件（HTTP 鉴权用 `${环境变量}` 引用）。

## 分层契约

- `tui -> core` 单向依赖；`core` 不 import `textual` / `rich` / `tui`，也不
  `print` / `input` / `sys.exit`。
- 错误统一用 `ErrorCode` 表达，中文文案只放在 `tui/i18n.py`；用户看得到的提示
  全部是中文。
- 唯一的装配点是 `core/factory.py:create_session(config, *, workspace_root, history_dir,
  backend=None, project_root=None, skills=None)`；
  界面层只拿 `AgentSession` 和 `AgentEvent`，不直接碰 OpenAI SDK。
- `core/tools/files.py` 的沙箱根由构造参数注入（旧版是模块级 `PROJECT_ROOT`），
  换界面或换工作目录时行为可预测。

## 快速开始

需要 Python 3.10+。

```bash
pip install -r requirements.txt
python main.py            # 或者：python -m tui
python main.py --workspace F:\your\project    # 启动时指定工作区（默认本项目目录）
python main.py --skills-dir D:\my-skills       # 额外技能根目录（可重复）
```

首次启动没有 `config.ini` 时，会弹出中文配置页，填写：

- 接口地址（BaseURL）
- API 密钥（APIKey，输入时隐藏）
- 模型名称（ModelName）

保存后写入 `YenaiAgent/config.ini`（已被仓库根 `.gitignore` 忽略，不会提交）。

也可以手动创建：

```ini
[llm]
base_url = https://api.example.com/v1
api_key = your-key
model_name = your-model

# 可选：单轮内最多允许的连续工具调用轮数（默认 40）
max_tool_rounds = 40

# 可选：单次回复的输出上限，单位 token（默认 4096；含工具参数，调小会让长文件写入被截断）
max_tokens = 4096

# 可选：联网搜索工具 searchWeb 使用百度千帆「智能搜索生成」接口
[search]
baidu_qianfan_api_key = your-baidu-key
```

不填 `[search]` 也能正常对话，只是模型调用 `searchWeb` 时会收到
「未配置搜索服务」的提示。搜索默认返回 5 条结果，单条摘要截断到 400 字。
网页抓取工具 `fetchWeb` 不需要额外配置，依赖系统自带的 `curl`。

## 使用

- 输入框支持多行：`Enter` 发送，`Ctrl+J` 换行（输入框会随行数变高，超过 8 行后
  内部滚动）。支持增强键盘协议（kitty / WezTerm / Ghostty 等）的终端里
  `Shift+Enter` / `Ctrl+Enter` 也可以换行，也可以直接粘贴多行文本。
  Windows 控制台会丢掉 `Ctrl` 修饰，`Ctrl+Enter` 会退化成 `Enter`（也就是发送），
  所以 Windows 上换行请用 `Ctrl+J` 或直接粘贴。
- 每条消息是一张带左侧色条的卡片：你的消息为橙色条，
  `AI` 回复为蓝色条，正文流式输出、逐块显示。
- 工具调用显示为绿色（成功）或红色（失败）卡片：标题行是 `工具名(参数) · 耗时 ms`，
  下面是「参数」「结果」两节；点击卡片可折叠/展开（`▼` 展开、`▶` 折叠）。
- `Ctrl+C`：正在回答时中断；空闲时退出。
- `Ctrl+Q`：退出。
- `Ctrl+L`：清屏（不影响上下文）。
- 命令：
  - `/help` 查看帮助
  - `/clear` 清屏（保留上下文）
  - `/reset` 清空上下文并换新存档
  - `/model` 查看当前模型；`/model 名称` 切换模型（保留上下文，同时写回 config.ini）
  - `/workspace` 查看当前工作区；`/workspace 目录` 切换工作区（保留上下文）
  - `/skills` 查看已加载的 Agent Skills 技能、扫描目录与跳过原因
  - `/config` 重新打开配置页（保存后换新会话）
  - `/exit` 退出

### 工作区

工作区是文件工具的沙箱范围，也决定 `RunCli` 命令的工作目录：

- 默认是 YenaiAgent 项目目录本身；启动时可用 `--workspace 路径` 指定，
  运行中随时用 `/workspace 目录路径` 切换。
- 支持 `~`、`%环境变量%` 与相对路径（按当前进程目录解析）；目录必须已存在。
- 切换只影响工具范围，**上下文与存档保留**：对话不用重来。
- 切到外部目录后，`list_directory_contents` / `read_text_file` 等才能访问该目录
  （不切换就只能访问默认工作区，绝对路径也会被沙箱挡下）。

### 长时间任务、卡顿与中断

- 状态栏每秒刷新：等待模型时显示「思考中… N 秒（已调用工具 M 次）」，
  工具执行时显示「调用工具：名称 · 已 N 秒（第 M 次）」。数字在走就说明没死。
- 单轮最多 40 轮工具调用（`[llm] max_tool_rounds` 可调）。到达上限不会丢结果：
  已经拿到的回答会保留在对话和上下文里，并附一句提示，直接继续追问即可。
- 模型如果用**完全相同的参数反复调同一个工具**超过 3 次，会自动停下并提示，
  避免在一件事上空转。
- 模型返回空内容（连接被掐断、额度或接口异常）时会明确报错，不会静默停在“思考中”。
- 超时：模型请求 60 秒；搜索 / 抓网页 / 命令行默认 30 秒（命令行可由模型指定到 120 秒）。
- `Ctrl+C` 立即进入“中断”状态，但正在执行的工具要等它返回（最长约 30 秒）才真正停下。
- 遇到卡住：先 `Ctrl+C` 中断再重发；仍不对可用 `/reset` 换新上下文，或 `/model` 换模型试试。

界面大致是这样（左侧竖条是卡片色条）：

```
▌你
▌ 2048 是闰年吗？

▌AI
▌ 是闰年。

▌▼ ✓ isLeapyear(year=2048) · 0 ms
▌  参数
▌  {
▌    "year": 2048
▌  }
▌  结果
▌  2048 年是闰年
```

切换模型不需要重建会话：后端按请求携带 `model`，因此当前上下文会保留，从下一轮
请求开始用新模型；存档继续写当前对话文件。

存档写入 `chat_history/YYYYMMDD_HHMMSS.txt`，格式与旧版一致：
`# 模型/开始` 头、`[HH:MM:SS] 用户`、`[工具] 名称 时间`、`[回复]`。

## 工具

共 18 个（装配了技能库时；不带技能库则为 16 个），前 13 个的顺序与旧版一致；接入 MCP
Server 时，每个 Server 的工具会在 `list_tools` 之前**动态追加**，不占下面的固定编号：

1. `get_date`：当前本地日期、时间、星期（纯 Python，不依赖 `date` 命令）
2. `isLeapyear`：闰年判断
3. `get_current_working_directory`
4. `list_directory_contents`
5. `get_file_type`
6. `read_text_file`
7. `create_file`
8. `edit_text_file`
9. `create_directory`
10. `delete_directory`
11. `delete_file`
12. `rename_path`
13. `searchWeb`：联网搜索（百度千帆「智能搜索生成」接口，返回标题、链接、日期、摘要）
14. `fetchWeb`：读取网页正文（本地 `curl` 下载 + `trafilatura` 转 Markdown）
15. `RunCli`：执行本机命令行程序，返回退出码、stdout、stderr。Windows 下会把子进程的
    `TMP`/`TEMP` 指到工作区内的 `.cli-tmp`（部分 CLI 写系统临时目录会被拒绝）
16. `loadSkill`：加载 Agent Skills 技能的 `SKILL.md` 或技能目录内的其他文件（见「技能」）
17. `createSkill`：按自然语言要求新建 Agent Skills 技能，生成规范的 `SKILL.md`（见「技能」）
18. `list_tools`：列出所有工具

MCP 工具默认沿用 Server 里的工具名；与本地工具或别的 Server 重名时自动加前缀
（`工具名` → `服务名__工具名`），仍冲突再补 `_2`、`_3`。

搜索工具的实现约定：

- 只接受 `query`（必填）和 `count`（1–10，默认 5），结果整理成编号列表交回模型。
- API Key 从 `config.ini` 的 `[search] baidu_qianfan_api_key` 读取，不在代码里硬编码；
  配置页保存 `[llm]` 时会原样保留 `[search]` 段。
- 缺配置、网络不通、HTTP 非 200、接口业务错误、返回体无法解析，都会变成
  `ok=False` 的工具结果，附带中文原因，由模型转述给用户。

网页抓取工具的实现约定：

- `curl` 用参数列表调用（`subprocess.run([...])`，不使用 `shell=True`），只接受
  `http` / `https` 地址，拒绝 `file://` 等本地路径；默认超时 30 秒。
- `curl` 加 `-f`，HTTP 4xx/5xx 直接按失败处理，避免把错误页当正文。
- 正文用 `trafilatura` 的 Markdown 输出（保留标题、段落、列表、表格、链接），开启
  `favor_precision` 去掉导航栏、广告、页脚；超过 2 万字截断并注明。
- 找不到 `curl`、访问超时、退出码非 0、HTML 解析失败、正文为空都转成带中文原因的
  `ok=False` 结果。
- Windows 10 及以上自带 `curl`；`trafilatura` 已写入 `requirements.txt`。

命令行工具的实现约定：

- 参数为 `command`（程序名或完整路径）与 `args`（字符串数组），内部拼成
  `[command, *args]` 交给 `subprocess.run(..., shell=False)`，逐个参数传递，
  不经过 Shell 解析——`args` 里的 `;`、`&&`、管道等只会作为普通字符串交给程序。
- 工作目录为当前工作区（默认项目根目录）；返回 JSON：`exit_code`、`stdout`、`stderr`，以及
  两路各自的 `*_truncated` 标记；退出码非 0 时 `ok` 为 `false`，模型可据此重试。
- 默认超时 30 秒（可由模型指定 1–120 秒），超时会终止进程并在 `error` 中说明；
  stdout/stderr 各自超过 8000 字符时保留头尾、中间标注「已截断 N 字符」。
- 找不到程序、参数格式错误、无法启动进程都会返回 `ok=false` 的结构化结果。

> ⚠️ `RunCli` 以运行本程序的用户权限执行任意命令，本阶段故意没有命令白名单、
> 黑名单或审批确认，仅适合受控教学实验环境；不要在生产或多人共用的机器上启用。

文件工具限制在沙箱根目录内：相对路径以沙箱根为基准，绝对路径也必须在根内；
只处理纯文本（UTF-8 / UTF-16 / GB18030，最大 2 MB）；删除根目录、重命名覆盖已有文件都会被拒绝。
沙箱根默认为项目目录，`--workspace` / `/workspace` 可切换到其他目录（见「工作区」）。

## 技能（Agent Skills）

启动时按 **程序启动目录**（不是工作区）扫描技能根目录下的技能子目录，扫描只进行一次；
运行中 `/workspace` 切换工作区不会改变技能清单；随时可用 `/skills` 查看扫描目录、
已加载技能与跳过原因。

技能根目录默认是 `<程序启动目录>/.agents/skills/`，也可以指向别处（支持多个根，
按顺序扫描，同名技能先扫到的生效）：

```ini
# config.ini
[skills]
roots = D:\my-skills; F:\yenaipaim\Plugin\.agents\skills
```

- 多个根用 `;` 或 `,` 分隔，支持 `~` 与 `%环境变量%`；相对路径按程序启动目录解析，
  换机器、换目录都不用改代码。
- 也可用 `--skills-dir 路径`（可重复）或环境变量 `YENAI_SKILLS_DIRS="a;b"`
  临时指定；优先级：命令行 > 环境变量 > `config.ini`。
- `config.ini` 不进版本库：技能根目录属于「本机环境」配置，保存模型设置时该段原样保留。
- 某次扫描目录不存在时不会报错，会在 `/skills` 里提示「技能根目录不存在」。

- 每个技能是一个子目录，内含顶层 `SKILL.md`；frontmatter 里声明 `name` 与
  `description`（其余字段忽略），示例：

  ```markdown
  ---
  name: deploy-helper
  description: 部署本项目的辅助流程与注意事项
  ---

  # 部署流程（正文只在模型调用 loadSkill 时才进入上下文）
  ```

- 初始化只读取 `name` 与 `description` 两个字段，正文不会加载；技能清单以
  `- name: description` 的形式注入 System Prompt，并附一句「用 `loadSkill` 加载」的说明。
- `loadSkill` 工具的参数：
  - `name`（必填）：技能名，精确匹配优先，找不到时按大小写不敏感回退；只给 `name`
    时返回该技能 `SKILL.md` 的全文。
  - `filename`（可选）：技能附带的其他文件。支持相对技能目录、相对项目根、绝对路径；
    先精确匹配，找不到再在技能目录内递归按文件名查找——唯一命中就直接读取，
    多个同名文件会返回候选路径列表让模型选。
- 安全边界：`loadSkill` 的所有读取都限制在该技能目录内，越界路径（`../` 或目录外的
  绝对路径）会直接拒绝；文件按 UTF-8（含 BOM）读取，回退 GB18030，超过 2 MB 截断。
- 缺 `SKILL.md`、frontmatter 不完整或 `name`/`description` 缺失的目录会被跳过；
  重名时先扫到的生效。跳过原因可通过 `session.skills.skipped` 查看（调试用）。

### 用 createSkill 新建技能（第九次课）

除了手写文件，也可以直接对 Agent 说「帮我建一个 xxx 技能，内容是……」，
模型会调用 `createSkill(name, skillContext)` 自己落盘：

| 参数 | 说明 |
| --- | --- |
| `name` | 技能名，会规范成 kebab-case：`PDF Tools` → `pdf-tools`，`A_b` → `a-b`；规范不出小写英文名（如纯中文）时返回错误与现有技能清单 |
| `skillContext` | 写入 `SKILL.md` 的完整内容，可以带 frontmatter（含 `name` / `description`）与正文；不带 frontmatter 时自动补一份 |

- 目录建在**第一个技能根**（默认 `.agents/skills/`；根不存在会自动创建），文件名固定 `SKILL.md`。
- `name` 以目录名为准重写；`description` 缺省时取正文第一条可读文字（去掉 `#`、
  `- `、`1. ` 等前缀，最多 200 字）；含 `: ` 等会破坏 YAML 的值自动用 `>-` 折叠块。
- 模型自带的其他 frontmatter 键（`license`、`metadata` 等）原样保留，嵌套块不丢。
- 建完立刻 `_register` 进技能库：同一会话的下一轮 System Prompt 就带它，`loadSkill` 也能读，
  **不需要重启**。
- 目标技能已存在时不覆盖：返回 `ok=false`、中文「已存在」提示与现有文件清单
  （已登记的同名技能、以及「目录在但缺 `SKILL.md`」的半成品目录都算）；
  跨技能根重名同样拒绝。名称非法或正文为空时不会留下任何目录。
- `references/`、`scripts/` 等附属文件不由此工具生成，仍由模型调用文件工具补齐。

## MCP（Model Context Protocol）

配置文件与技能同源：**第一个技能根下的 `.mcp.json`**（默认 `<启动目录>/.agents/skills/.mcp.json`）。
启动时读取它，连上后把每个 Server 的 `list_tools()` 结果注册进同一个工具注册表——
模型看到的就是普通 Function Calling，调用时由客户端转发到对应 Server，文本、结构化
结果和错误原样交回。

「有就直接用，没有就自己建」：首次运行（或换了技能根）时文件不存在，程序会把内置模板
写进去并提示路径，改完重启即可；已有文件永远不被覆盖。技能根由 `config.ini` 的
`[skills] roots` 或 `--skills-dir` 决定（多个时取第一个），和 `/skills` 看到的是同一处。

唯一的外部覆盖是环境变量 `YENAI_MCP_CONFIG`：指向别的配置文件（相对路径按项目根解析），
设为 `off` 则本次运行整体关闭 MCP（测试就是用它隔离的）。

格式与 Claude Desktop / Cursor 的 `mcpServers` 兼容：

```json
{
  "mcpServers": {
    "PeiHospitalMCP": {
      "type": "streamable_http",
      "url": "http://127.0.0.1:9000/mcp",
      "connect_timeout": 5,
      "timeout": 30
    },
    "Bazi-MCP": {
      "type": "streamable_http",
      "url": "https://mcp.api-inference.modelscope.net/<你的-endpoint-id>/mcp"
    },
    "local-tools": {
      "type": "stdio",
      "command": "python",
      "args": ["D:\\mcp\\server.py"],
      "env": {"TOKEN": "${MY_TOKEN}"}
    }
  }
}
```

- `type`：`stdio`（配 `command` / `args` / `env` / `cwd`）、`streamable_http`（配 `url`，
  也可写 `http`）、`sse`（配 `url`，旧版 SSE）；缺省时按 `url` / `command` 推断，
  `url` 以 `/sse` 结尾按 SSE 处理。
- `headers` 用于 HTTP Server 的鉴权；`${VAR}` 会替换成本机环境变量，变量缺失直接报错。
- `enabled: false`（或 `disabled: true`）保留配置但不连接；`connect_timeout`（默认 10 秒）、
  `timeout`（单次调用，默认 30 秒）、`max_output`（默认 2 万字）可按 Server 覆盖。
- 单个 Server 写错只会进 `/mcp` 的「配置问题」列表，不影响其他 Server。
- 最常见的两个坑：`url` 必须带协议头和路径（`http://127.0.0.1:9000/mcp`）——写成
  `127.0.0.1:9000` 会被校验拒掉，写成 `http://127.0.0.1:9000` 会连到根路径失败；最外层
  必须是 `"mcpServers": { ... }`，漏掉的话整份文件被当成空配置，启动摘要和 `/mcp` 都没有提示。
- 连不上会在启动摘要和 `/mcp` 里显示失败原因（该 Server 的工具返回 `ok=false` 的结果），
  本地工具与其他 Server 照常可用；各 Server 并行连接，启动最多等 `connect_timeout` 秒。
- `/mcp` 可查看每个 Server 的传输方式、连接状态、注册工具数与失败原因。
- OpenAI 兼容接口的函数名只能是 `[A-Za-z0-9_-]`：Server 里的中文工具名会注册成
  `tool_1`、`tool_2`……，中文原名与描述一起保留，模型按描述挑选。
- 依赖 `mcp>=2.2,<3`；stdio Server 是普通子进程，退出时随会话一起关闭。
- 自动生成的模板在 `core/mcp/config.py` 的 `MCP_TEMPLATE` 里：一个可用的
  `PeiHospitalMCP`（本机 9000 端口）加两条 `disabled` 示例，分别演示 stdio 与带鉴权头的
  HTTP 写法，取消 `disabled` 并填好参数即可启用。
- 模板与配置都是**本机文件**，`.agents/` 整个目录不入库；课堂演示时不必把私有
  endpoint 提交上去。
- 模板里的 `PeiHospitalMCP`（`Pet/` 里的宠物医院 MCP）默认监听 9000 端口，需要先跑起来，
  否则启动摘要会显示连接失败——不影响其他功能；服务起来后重启 YenaiAgent 即自动接入。

## 开发与测试

```bash
pip install -r requirements.txt   # 运行依赖与测试依赖都在这一份里
pytest tests -q          # 当前 187 个用例，约 20 秒
```

- 网络完全用 `tests/support.py` 里的 `FakeBackend` 脚本化替身，不发起真实请求；
  搜索与抓取工具也通过注入假 transport / 假 curl 测试，跑测试不需要联网。
- `tests/test_layers.py` 校验分层：`core` 不得 import `textual/rich/tui`，也不得做进程级 IO。
- `tests/test_mcp.py` 覆盖 `.mcp.json` 解析（stdio / HTTP、坏条目、缺失文件、`disabled`
  占位、`${VAR}` 展开）、配置发现（技能目录首次生成模板、已有文件不覆盖、`off` 不落盘、
  不认旧位置、`YENAI_MCP_CONFIG` 覆盖）、工具重名加前缀、`ToolOutcome` 透传，以及一个真实
  stdio MCP Server（`mcp.server.mcpserver.MCPServer`，1.x 回退 `FastMCP`）的 list / call
  往返和「坏 Server 不影响本地工具」的隔离场景；`tests/conftest.py` 里 autouse 地关掉 MCP，
  测试不连真实服务。
- `tests/test_skills.py` 覆盖技能发现与跳过规则、frontmatter 解析、清单注入与
  `loadSkill` 的路径解析 / 沙箱拒绝场景，以及多根扫描、重名去重与 `[skills]`
  配置解析；`createSkill` 部分覆盖名称规范化、`SKILL.md` 生成（frontmatter 可回读、
  正文保留、LF 无 BOM）、缺根自动创建、已存在不覆盖、跨根重名拒绝与端到端调用。
- TUI 用 Textual 的 `run_test` 无头驱动，覆盖流式渲染、消息卡片与工具卡片（含耗时、
  参数/结果分节、点击折叠）、错误提示、命令、首次配置页，以及「回复必须逐块出现」
  的流式回归测试（慢速后端断言中间态）。

## 与 Practice02 的差异

- 拆成 core / tui 两层，配置、流式、工具、存档不再是同一个 `main.py`。
- 界面改成卡片式：提问/回复带角色色条，工具调用单独成卡并显示耗时、参数、结果，
  可点击折叠；配色全部走主题变量，切换 Textual 主题时跟着变。
- 配置页与全部提示改为中文；新增 `/model` 命令，可随时切换模型并保留上下文。
- 工具执行结果统一回给模型：字符串原样返回，字典转 JSON（`ensure_ascii=False`），
  失败为 `{"ok": false, "error": ...}`，模型能自己纠错。
- 只有成功的问答才写入上下文和存档；失败与中断不会污染历史。
- 存档文件在首次成功问答时创建（旧版启动即创建，可能留下空文件）。
- 日期工具改为纯 Python 实现，输出格式保持 `YYYY-MM-DD HH:MM:SS 星期X（UTC+0800）`。
- 新增 Agent Skills：技能目录（默认 `.agents/skills/`，可配置多个根）里的技能按
  `SKILL.md` frontmatter 自动登记，清单进 System Prompt，正文按需经 `loadSkill`
  加载（Practice02 没有的能力）。
- 工具从 13 个扩展到 18 个：新增 `searchWeb`（联网搜索）、`fetchWeb`（抓网页）、
  `RunCli`（执行本地命令行）、`loadSkill` / `createSkill`（技能加载与创建），
  仍然全部通过注册表统一描述、执行与错误归一。
- 新增 MCP 客户端：技能目录里的 `.mcp.json`（首个技能根，缺失时自动生成模板）列出
  的 Server 启动时连接，`list_tools()` 的结果动态注册成工具，调用经 stdio /
  Streamable HTTP / SSE 转发；连不上只影响该 Server（Practice02 没有的能力）。

## 后续扩展

`core` 已经与界面解耦，新界面只需要：

1. 用 `ConfigStore` 读配置；
2. 用 `create_session(...)` 建会话；
3. 消费 `session.ask(question)` 产出的事件；
4. 需要时调用 `CancelToken.cancel()` 中断。

Web / Desktop 层可以照搬 `tui/` 的组织方式，而不改 `core/`。