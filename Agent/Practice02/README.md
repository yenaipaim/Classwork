# Practice02 - 本地文件操作 CLI

在 [Practice01](../Practice01/README.md) 的多轮对话、流式输出和工具调用基础上，
增加 10 个受项目目录约束的本地文件工具，并提供一个工具清单功能。

> 本目录保留为课程原始版本。重构版见 [../YenaiAgent/README.md](../YenaiAgent/README.md)：
> 保留 13 个工具与存档格式，拆成 `core` / `tui` 两层并改为 Textual 全屏界面，
> 另加联网搜索、网页抓取、本地命令行与 Agent Skills 技能加载（共 17 个工具）。

## 启动

```powershell
python main.py
```

从仓库根目录启动：

```powershell
python Agent\Practice02\main.py
```

输入 `/exit` 退出。

## 文件

```text
Practice02/
├── main.py            # CLI、对话循环、工具注册与分发
├── file_tools.py      # 10 个文件工具和路径校验
├── architecture.mmd   # Mermaid 代码架构图
├── config.ini         # 本地模型配置
└── chat_history/      # 每次运行的问答存档
```

`main.py` 会在导入本地模块前设置 `sys.dont_write_bytecode = True`，
因此正常运行不会生成 `__pycache__`。

## 工具清单

| 工具 | 参数 | 说明 |
|------|------|------|
| `get_date` | 无 | 获取本机日期、时间、星期和 UTC 偏移 |
| `isLeapyear` | `year` | 判断指定年份是否为闰年 |
| `get_current_working_directory` | 无 | 返回进程工作目录和项目根目录 |
| `list_directory_contents` | `directory` | 列出直接子文件和子目录 |
| `get_file_type` | `path` | 返回扩展名、MIME 类型和文本状态 |
| `read_text_file` | `path` | 读取纯文本文件 |
| `create_file` | `directory`、`filename` | 创建空文件，不覆盖同名文件 |
| `edit_text_file` | `path`、`content` | 完整替换纯文本文件内容 |
| `create_directory` | `directory` | 创建目录及缺少的父目录 |
| `delete_directory` | `directory` | 递归删除目录及全部内容 |
| `delete_file` | `path` | 删除指定文件 |
| `rename_path` | `path`、`new_name` | 在同一目录内重命名文件或目录 |
| `list_tools` | 无 | 列出当前注册的全部工具名称和描述 |

当前共注册 13 个工具。

## 文件安全

- 所有文件路径必须位于当前 `Practice02` 目录内。
- 相对路径以 `Practice02` 为基准，不依赖启动时的工作目录。
- 路径越界或通过符号链接指向项目外时会被拒绝。
- 不能删除 `Practice02` 根目录。
- `rename_path` 只能在同一目录内改名，不能覆盖已有文件或目录。
- 读取和编辑只支持纯文本，二进制文件会返回错误。
- 单个文本文件读取上限为 2 MB。
- 目录列表只包含直接子项，不递归。

## 文本处理

- 支持 UTF-8、UTF-16、GB18030 等常见编码。
- `edit_text_file` 是完整替换，不是追加或局部编辑。
- 编辑时尽量沿用文件原有编码。
- `create_file` 只创建空文件，已存在同名文件时失败。

## 配置与历史

配置文件格式与 Practice01 相同：

```ini
[llm]
base_url = https://example.com/v1
api_key = your-api-key
model_name = your-model
```

每次运行会在 `chat_history/` 下生成一个问答与工具调用存档。
`config.ini` 和 `chat_history/` 都不应提交到公共仓库。

## 架构图

[architecture.mmd](architecture.mmd) 使用 Mermaid `flowchart TD` 描述配置初始化、
终端对话循环、流式模型调用、工具分发、文件工具校验和历史记录流程。
可将该文件直接粘贴到支持 Mermaid 的编辑器或在线预览工具中查看。

## 依赖

```powershell
pip install openai
```

