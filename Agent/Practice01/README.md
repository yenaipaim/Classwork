# Practice01 - 多轮对话 CLI

单文件命令行对话工具，使用 OpenAI 兼容接口完成多轮对话、流式输出和工具调用。

## 启动

```powershell
python main.py
```

从仓库根目录启动：

```powershell
python Agent\Practice01\main.py
```

输入 `/exit`、按 `Ctrl+C` 或 `Ctrl+D` 退出。

## 功能

- 保留当前进程内最近 10 轮上下文
- 模型回复按流式片段逐步打印
- 等待首个 token 时显示原地转圈动画
- 失败或中断的轮次不写入上下文
- 每次运行创建独立的对话历史文件
- 模型可调用日期和闰年工具

## 工具

| 工具 | 参数 | 说明 |
|------|------|------|
| `get_date` | 无 | 获取本机日期、时间、星期和 UTC 偏移 |
| `isLeapyear` | `year` | 判断指定年份是否为闰年 |

单轮最多执行 5 次工具调用，`MAX_TOOL_ROUNDS` 可调整。

## 文件

```text
Practice01/
├── main.py            # 全部对话与工具逻辑
├── config.ini         # 本地模型配置
└── chat_history/      # 每次运行的问答存档
```

## 配置

首次运行时会询问：

```text
BaseURL：
APIKey：
ModelName：
```

配置保存在 `config.ini` 的 `[llm]` 段。该文件包含 API Key，不应提交。

## 历史记录

每次启动创建一个 `chat_history/年月日_时分秒.txt`，只追加成功完成的问答。
历史文件不会在启动时回读，运行上下文仍只保留在内存中。

## 主要常量

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `HISTORY_TURNS` | `10` | 发送给模型的最近轮数 |
| `MAX_TOKENS` | `512` | 单次回复 token 上限 |
| `REQUEST_TIMEOUT` | `60.0` | 请求超时秒数 |
| `SPINNER_INTERVAL` | `0.12` | 转圈动画帧间隔 |
| `MAX_TOOL_ROUNDS` | `5` | 单轮工具调用上限 |

## 依赖

```powershell
pip install openai
```

下一步的文件工具扩展见 [../Practice02/README.md](../Practice02/README.md)。

