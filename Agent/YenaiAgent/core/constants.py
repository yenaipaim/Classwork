"""与界面无关的默认参数。"""

from __future__ import annotations

SYSTEM_PROMPT = "回答简洁，减少副词，不用 emoji。"
# 单次回复的输出上限（含 Function Calling 的参数）。
# 1024 会连带截断 tool_call 的参数 JSON——模型写长文件时参数写到一半被砍断，
# 得到的就是「工具参数不是合法 JSON：Unterminated string」。放宽到 4096。
# 仍被截断时 session 会在结尾提示“达到输出上限”，可以接着说“继续”。
MAX_TOKENS = 4096

# 保留的上下文轮数：每轮 = 一次提问 + 一次回答
HISTORY_TURNS = 10

# 单轮内允许的连续工具调用轮数上限，防止模型反复调用死循环。
# 这是“轮”不是“次”：模型一次回复里并发 3 个工具仍然只算 1 轮。
# 40 轮足够覆盖查资料、写文件、调外部 CLI 的文档生成任务；触顶时不再报错中止，
# 而是把已产生的回答保留下来，用户可以接着追问。
MAX_TOOL_ROUNDS = 40

# 同一个工具 + 同一组参数连续被调用这么多次，就判定模型在原地打转
MAX_REPEATED_TOOL_CALLS = 3

REQUEST_TIMEOUT = 60.0

# 网络搜索：百度千帆「智能搜索生成」接口
SEARCH_ENDPOINT = "https://qianfan.baidubce.com/v2/ai_search/chat/completions"
SEARCH_TIMEOUT = 30.0
SEARCH_TOP_K = 5
SEARCH_MAX_TOP_K = 10

# 网页抓取：本地 curl 下载 + trafilatura 提取正文
FETCH_TIMEOUT = 30.0
FETCH_MAX_CHARS = 20000
FETCH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# 命令行工具：单次执行超时与单路输出上限
CLI_TIMEOUT = 30.0
CLI_MAX_TIMEOUT = 120.0
CLI_MAX_OUTPUT = 8000

# 上下文压缩：默认窗口大小（拿不到真实窗口时用，并在界面上标注「默认」）、
# 告警阈值（达到窗口的这个比例就提示用户执行 /compact 并暂停普通输入）、
# 摘要目标长度与压缩请求自身的输出上限/超时。
DEFAULT_CONTEXT_WINDOW = 128_000
CONTEXT_WARN_RATIO = 0.7
COMPACT_TARGET_TOKENS = 5_000
COMPACT_MAX_TOKENS = 8_192
COMPACT_TIMEOUT = 300.0
# 归档目录：相对项目根，压缩前把原始上下文完整写到这里
CONTEXT_ARCHIVE_DIR = ".agents/context"

# MCP：配置文件默认名、连接/初始化超时、单次工具调用超时与回填上下文的上限
MCP_CONFIG_FILENAME = ".mcp.json"
MCP_CONNECT_TIMEOUT = 10.0
MCP_CALL_TIMEOUT = 30.0
MCP_MAX_OUTPUT = 20000
# 会话事件日志：/new、/resume、/save 用它保存与恢复历史会话
SESSIONS_DIR = ".agents/sessions"
SESSION_LOG_VERSION = 1
# 一次列表/补全最多读多少个会话（按时间倒序）
SESSION_LIST_LIMIT = 50

# 项目约定文件：会话首次加载时注入一次，之后一直留在历史里复用
AGENTS_MD_FILENAME = "AGENTS.md"
AGENTS_MD_MAX_CHARS = 20000
