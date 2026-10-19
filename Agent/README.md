# Agent CLI Practices

基于 OpenAI 兼容接口的命令行对话练习。两个练习共用流式输出、多轮上下文和
本地历史记录方式，但工具能力不同。

## 练习目录

| 目录 | 能力 | 文档 |
|------|------|------|
| `Practice01/` | 多轮对话、流式输出、日期与闰年工具 | [Practice01/README.md](Practice01/README.md) |
| `Practice02/` | 在 Practice01 基础上增加 10 个本地文件操作工具 | [Practice02/README.md](Practice02/README.md) |

## 共同特性

- OpenAI 兼容的 Chat Completions 接口
- 流式打印模型回复
- 等待首个 token 时显示终端转圈动画
- 上下文只保存在当前进程内存中
- 每次运行在各自的 `chat_history/` 下生成历史存档
- 模型可以调用 Python/本地工具

## 启动

从仓库根目录运行：

```powershell
python Agent\Practice01\main.py
python Agent\Practice02\main.py
```

输入 `/exit` 退出。

## 配置

两个练习分别在各自目录读取 `config.ini`：

```ini
[llm]
base_url = https://example.com/v1
api_key = your-api-key
model_name = your-model
```

配置不存在时，程序会交互式创建。

## 依赖

```powershell
pip install openai
```

`config.ini` 和 `chat_history/` 都属于本地运行数据，不应提交到公共仓库。

