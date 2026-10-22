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
│   ├── session.py        # AgentSession / CancelToken：流式、工具循环、存档提交
│   ├── transcript.py     # chat_history/*.txt 存档（格式与旧版一致）
│   ├── llm/              # 后端协议、请求/流式块类型、工具调用收集器
│   └── tools/            # ToolSpec / ToolRegistry / 内置工具 / 文件工具（沙箱根注入）
├── tui/                  # 终端界面层：只做输入、展示与命令
│   ├── app.py            # YenaiApp：线程模型、流式刷新、斜杠命令
│   ├── i18n.py           # 全部中文文案与错误码 -> 文案映射
│   ├── screens/          # 配置弹窗（全中文）
│   ├── widgets/          # 消息卡片、可折叠的工具调用卡片
│   ├── styles.tcss       # 界面样式（角色色条、工具卡片配色）
│   └── __main__.py       # python -m tui
├── tests/                # 无网络测试：FakeBackend + Textual run_test
├── main.py               # python main.py
├── pyproject.toml        # 打包、入口点、pytest 配置
├── requirements.txt      # 运行依赖（openai、textual）
├── requirements-dev.txt  # 开发依赖（pytest、pytest-asyncio）
└── architecture.mmd      # 分层与依赖方向图
```

`config.ini`、`chat_history/` 与各类缓存由**仓库根目录**的 `.gitignore` 统一忽略。

## 分层契约

- `tui -> core` 单向依赖；`core` 不 import `textual` / `rich` / `tui`，也不
  `print` / `input` / `sys.exit`。
- 错误统一用 `ErrorCode` 表达，中文文案只放在 `tui/i18n.py`；用户看得到的提示
  全部是中文。
- 唯一的装配点是 `core/factory.py:create_session(config, *, workspace_root, history_dir, backend=None)`；
  界面层只拿 `AgentSession` 和 `AgentEvent`，不直接碰 OpenAI SDK。
- `core/tools/files.py` 的沙箱根由构造参数注入（旧版是模块级 `PROJECT_ROOT`），
  换界面或换工作目录时行为可预测。

## 快速开始

需要 Python 3.10+。

```bash
pip install -r requirements.txt
python main.py            # 或者：python -m tui
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
```

## 使用

- 在输入框输入问题，`Enter` 发送；每条消息是一张带左侧色条的卡片：你的消息为橙色条，
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
  - `/config` 重新打开配置页（保存后换新会话）
  - `/exit` 退出

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

共 13 个，顺序与旧版一致：

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
13. `list_tools`：列出所有工具

文件工具限制在沙箱根目录内：相对路径以沙箱根为基准，绝对路径也必须在根内；
只处理纯文本（UTF-8 / UTF-16 / GB18030，最大 2 MB）；删除根目录、重命名覆盖已有文件都会被拒绝。

## 开发与测试

```bash
pip install -r requirements-dev.txt
pytest tests -q          # 当前 55 个用例，约 4 秒
```

- 网络完全用 `tests/support.py` 里的 `FakeBackend` 脚本化替身，不发起真实请求。
- `tests/test_layers.py` 校验分层：`core` 不得 import `textual/rich/tui`，也不得做进程级 IO。
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

## 后续扩展

`core` 已经与界面解耦，新界面只需要：

1. 用 `ConfigStore` 读配置；
2. 用 `create_session(...)` 建会话；
3. 消费 `session.ask(question)` 产出的事件；
4. 需要时调用 `CancelToken.cancel()` 中断。

Web / Desktop 层可以照搬 `tui/` 的组织方式，而不改 `core/`。