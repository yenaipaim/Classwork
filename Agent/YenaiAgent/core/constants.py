"""与界面无关的默认参数。"""

from __future__ import annotations

SYSTEM_PROMPT = "回答简洁，减少副词，不用 emoji。"
MAX_TOKENS = 512

# 保留的上下文轮数：每轮 = 一次提问 + 一次回答
HISTORY_TURNS = 10

# 单轮内允许的连续工具调用次数上限，防止模型反复调用死循环
MAX_TOOL_ROUNDS = 5

REQUEST_TIMEOUT = 60.0