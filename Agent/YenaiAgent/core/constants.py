"""与界面无关的默认参数。"""

from __future__ import annotations

SYSTEM_PROMPT = "回答简洁，减少副词，不用 emoji。"
MAX_TOKENS = 512

# 保留的上下文轮数：每轮 = 一次提问 + 一次回答
HISTORY_TURNS = 10

# 单轮内允许的连续工具调用次数上限，防止模型反复调用死循环
MAX_TOOL_ROUNDS = 5

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