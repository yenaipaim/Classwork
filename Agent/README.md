# Agent — 命令行对话练习与分层智能体

基于 OpenAI 兼容接口的三代实现：从单文件 CLI，到带本地文件工具的 CLI，再到
core/TUI 分层重构。三者共用流式输出、多轮上下文和本地历史存档方式，工具能力与
界面形态不同。

## 目录

| 目录 | 能力 | 文档 |
|------|------|------|
| `Practice01/` | 多轮对话、流式输出、日期与闰年工具 | [Practice01/README.md](Practice01/README.md) |
| `Practice02/` | 在 Practice01 基础上增加 10 个本地文件操作工具 | [Practice02/README.md](Practice02/README.md) |
| `YenaiAgent/` | Practice02 的分层重写：`core` + Textual TUI，工具与沙箱保留，并支持 Agent Skills 技能加载 | [YenaiAgent/README.md](YenaiAgent/README.md) |

## 启动

从仓库根目录运行：

```powershell
python Agent\Practice01\main.py
python Agent\Practice02\main.py
python Agent\YenaiAgent\main.py
```

- Practice01 / Practice02：输入 `/exit` 退出
- YenaiAgent：`/exit` 或 `Ctrl+Q` 退出，`Ctrl+C` 中断当前回复

## 共同特性

- OpenAI 兼容的 Chat Completions 接口
- 流式输出模型回复
- 上下文只保存在当前进程内存中，每次运行在各自的 `chat_history/` 下生成存档
- 模型可以调用本地工具（日期、闰年、文件操作等）

## YenaiAgent 的不同

| 方面 | Practice02 | YenaiAgent |
|------|------------|------------|
| 代码结构 | 单文件 `main.py` + `file_tools.py` | `core/`（业务）+ `tui/`（界面）分层 |
| 界面 | 终端逐行打印 + 转圈动画 | Textual 全屏 TUI：消息卡片、工具卡片、配置页 |
| 依赖方向 | — | 严格 `tui → core`，core 不依赖任何 UI 库 |
| 装配方式 | 模块级全局 | `core/factory.py` 注入 backend / registry / 沙箱根 |
| 测试 | 手工验证 | `tests/` 覆盖 core 与 TUI（pytest，无头模式，158 个用例） |
| 工具 | 13 个 | 17 个：在旧版基础上增加 `searchWeb`（联网搜索）、`fetchWeb`（抓网页正文）、`RunCli`（本地命令行）、`loadSkill`（按需加载 Skill） |
| 技能 | 无 | Agent Skills：扫描技能目录、清单进 System Prompt、正文按需加载 |
| 输入 | `input()` 单行 | 多行输入框：`Enter` 发送、`Ctrl+J` 换行，卡片式消息流 |
| 工作区 | 固定为项目目录 | `--workspace` 启动指定，`/workspace` 运行时切换（文件沙箱 + `RunCli` 目录） |

## 配置

三个目录各自读取同目录下的 `config.ini`：

```ini
[llm]
base_url = https://example.com/v1
api_key = your-api-key
model_name = your-model
```

Practice01 / Practice02 在配置缺失时用终端问答创建；YenaiAgent 会弹出中文配置页
（也可手写该文件）。`config.ini`、`chat_history/` 与技能目录 `.agents/` 都属于本地
运行数据，已在仓库根 `.gitignore` 中排除，不应提交。

### YenaiAgent 的技能目录

默认扫描 `<程序启动目录>/.agents/skills/`；想用别的目录（可以多个），加一段配置
即可，不需要改代码：

```ini
[skills]
; 分号/逗号分隔，支持 ~ 和 %环境变量%；相对路径按程序启动目录解析
roots = D:\my-skills; F:\yenaipaim\Plugin\.agents\skills
```

也可以用 `--skills-dir 路径`（可重复）或环境变量 `YENAI_SKILLS_DIRS="a;b"` 临时指定。
多个根按顺序扫描，同名技能先扫到的生效；`/skills` 命令可查看扫描目录、已加载技能与
跳过原因。

## 依赖

```powershell
pip install openai textual trafilatura
```

`textual` 与 `trafilatura` 只有 YenaiAgent 需要（后者用于 `fetchWeb` 提取网页正文）；
YenaiAgent 目录下也有 `requirements.txt` 可以一次装齐。