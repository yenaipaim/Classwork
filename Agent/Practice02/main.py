"""命令行对话工具：多轮对话，上下文保留在内存中，退出即清空。"""

import configparser
import json
import os
import subprocess
import sys
import threading
from datetime import datetime

# 禁止本地模块导入时生成本地 __pycache__
sys.dont_write_bytecode = True

from openai import OpenAI

from file_tools import FILE_TOOL_NAMES, FILE_TOOLS, run_file_tool

# 与脚本同目录
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
# 历史记录目录：每次运行一个文件，只追加成功的问答
HISTORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_history")

SYSTEM_PROMPT = "回答简洁，减少副词，不用 emoji。"
MAX_TOKENS = 512
ERROR_TEXT = "额度已经耗尽或者配置信息错误"

# 保留的上下文轮数：每轮 = 一次提问 + 一次回答
HISTORY_TURNS = 10

LINE = "---------------"
EXIT_COMMAND = "/exit"

SPINNER_FRAMES = "\\|/-"
SPINNER_INTERVAL = 0.12
SPINNER_PREFIX = "生成中 "
REQUEST_TIMEOUT = 60.0

# 单轮内允许的连续工具调用次数上限，防止模型反复调用死循环
MAX_TOOL_ROUNDS = 5

# 提供给模型的工具清单
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_date",
            "description": "获取当前电脑的本地日期、时间与星期",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "isLeapyear",
            "description": "判断指定年份是否为闰年（Python 计算）",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "要判断的年份，例如 2024"}
                },
                "required": ["year"],
            },
        },
    },
]
TOOLS.extend(FILE_TOOLS)
TOOLS.append(
    {
        "type": "function",
        "function": {
            "name": "list_tools",
            "description": "列出当前程序注册的全部工具名称和用途",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
)


def create_config():
    """config.ini 不存在时，交互式收集三项配置并写入。"""
    base_url = input("BaseURL：").strip()
    api_key = input("APIKey：").strip()
    model_name = input("ModelName：").strip()

    parser = configparser.ConfigParser()
    parser["llm"] = {
        "base_url": base_url,
        "api_key": api_key,
        "model_name": model_name,
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        parser.write(f)
    print(f"配置已保存到 {CONFIG_PATH}")


def load_config():
    """读取 config.ini，返回 (base_url, api_key, model_name)。"""
    parser = configparser.ConfigParser()
    parser.read(CONFIG_PATH, encoding="utf-8")
    section = parser["llm"]
    return section["base_url"], section["api_key"], section["model_name"]


def set_cursor(visible):
    """隐藏/显示光标，避免等待时闪烁（不支持 ANSI 的终端会忽略）。"""
    print("\033[?25h" if visible else "\033[?25l", end="", flush=True)


def get_date():
    """执行系统 date 命令，返回当前日期、时间、星期与 UTC 偏移。

    终端里没有 date 命令（如直接在 cmd/PowerShell 下运行）时退回 Python 实现，
    保证工具调用不会因此失败。
    """
    try:
        out = subprocess.run(
            ["date", "+%Y-%m-%d %H:%M:%S %z %u"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode != 0:
            raise OSError(out.stderr.strip() or "date 命令返回非零")
        stamp, tz, iso_week = out.stdout.strip().split()
        week = "一二三四五六日"[int(iso_week) - 1]
        return "%s 星期%s（UTC%s）" % (stamp, week, tz)
    except (OSError, ValueError, subprocess.SubprocessError):
        now = datetime.now().astimezone()
        week = "一二三四五六日"[now.weekday()]
        return "%s 星期%s（UTC%s）" % (now.strftime("%Y-%m-%d %H:%M:%S"), week, now.strftime("%z"))


def is_leap_year(year):
    """闰年规则：能被 4 整除，且整百年必须能被 400 整除。"""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def list_tools():
    """返回当前注册的全部工具名称和描述。"""
    tools = [
        {
            "name": item["function"]["name"],
            "description": item["function"].get("description", ""),
        }
        for item in TOOLS
    ]
    return {"ok": True, "count": len(tools), "tools": tools}


def run_tool(name, arguments):
    """执行模型请求的工具，返回给模型的文本结果。"""
    if name == "get_date":
        return get_date()
    if name == "isLeapyear":
        return _check_leap_year(arguments)
    if name == "list_tools":
        return json.dumps(list_tools(), ensure_ascii=False)
    if name in FILE_TOOL_NAMES:
        return run_file_tool(name, arguments)
    return "未知工具：%s" % name


def _check_leap_year(arguments):
    """解析 isLeapyear 的参数并给出结论；参数非法时把原因回给模型。"""
    try:
        year = json.loads(arguments or "{}")["year"]
    except (ValueError, TypeError, KeyError):
        return "参数错误：需要提供整数年份，例如 {\"year\": 2024}"
    if isinstance(year, str):
        text = year.strip()
        if text.lstrip("-").isdigit():
            year = int(text)
    if isinstance(year, bool) or not isinstance(year, int):
        return "参数错误：年份必须是整数"
    if is_leap_year(year):
        return "%d 年是闰年" % year
    return "%d 年不是闰年" % year


def new_history_file(model_name):
    """为本次运行创建一个历史记录文件，返回路径。"""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    path = os.path.join(HISTORY_DIR, datetime.now().strftime("%Y%m%d_%H%M%S") + ".txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# 模型：%s\n# 开始：%s\n" % (model_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    return path


def save_turn(path, question, answer, tools=()):
    """把一次成功的问答追加到历史文件，含本轮内的工具调用；写失败不影响对话本身。"""
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n[%s] 用户\n%s\n" % (datetime.now().strftime("%H:%M:%S"), question))
            for item in tools:
                f.write(
                    "\n[工具] %s  %s\n参数：%s\n结果：%s\n"
                    % (item["name"], item["time"], item["arguments"] or "{}", item["result"])
                )
            f.write("\n[回复]\n%s\n" % answer)
    except OSError:
        pass


def spinner(spin_stop, first_chunk):
    """等首个 token 期间原地转圈，收到首段内容或结束信号就擦掉动画行。"""
    i = 0
    while not spin_stop.is_set() and not first_chunk.is_set():
        lead = "" if i == 0 else "\r"
        print(f"{lead}{SPINNER_PREFIX}{SPINNER_FRAMES[i % len(SPINNER_FRAMES)]}", end="", flush=True)
        i += 1
        spin_stop.wait(SPINNER_INTERVAL)
    print("\r\x1b[K", end="", flush=True)


class Outcome:
    """一次流式调用的结果：区分「模型产出的内容」「工具调用」与「失败」。"""

    def __init__(self):
        self.parts = []
        self.error = None
        # 工具调用按流式分片累积：index -> {id, name, arguments}
        self.tool_calls = {}

    @property
    def text(self):
        return "".join(self.parts)


def stream_answer(client, model_name, messages, on_first_chunk, outcome):
    """流式调用，逐段产出文本；工具调用的分片累积到 outcome.tool_calls。

    错误文案不再混进正文：调用方据此决定「失败提示照打、但不写入上下文」，
    避免模型把自己没说过的话当成历史。
    """
    try:
        stream = client.chat.completions.create(
            model=model_name,
            messages=messages,
            max_tokens=MAX_TOKENS,
            stream=True,
            tools=TOOLS,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                if not outcome.parts:
                    on_first_chunk()
                outcome.parts.append(delta.content)
                yield delta.content

            for call in getattr(delta, "tool_calls", None) or []:
                item = outcome.tool_calls.setdefault(
                    call.index, {"id": "", "name": "", "arguments": ""}
                )
                if call.id:
                    item["id"] = call.id
                func = getattr(call, "function", None)
                if func is not None:
                    if func.name:
                        item["name"] += func.name
                    if func.arguments:
                        item["arguments"] += func.arguments
    except KeyboardInterrupt:
        raise
    except Exception:
        outcome.error = ERROR_TEXT


def read_question():
    """读取一次输入。返回 (内容, 是否退出)；退出时内容为 None。"""
    try:
        line = input("请输入>>>")
    except EOFError:
        print()
        print("未收到输入，已退出。")
        return None, True
    except KeyboardInterrupt:
        print()
        return None, True
    # 输入回车后光标已在新行，这里补下分隔线
    print(LINE)
    if line.strip() == EXIT_COMMAND:
        return None, True
    return line, False


def ask_once(client, model_name, messages):
    """跑一轮请求并打印回复；模型请求工具时自动执行并继续，直到给出最终答案。

    返回 (回答文本, 是否失败, 工具调用列表)：失败时回答为 None；中途断流则返回已
    打印的半截内容并标记失败（不写入上下文，避免把残缺回答当成完整历史）。工具
    调用列表按执行顺序记录 name / arguments / result / time，供写历史时使用。
    """
    spin_stop = threading.Event()
    first_chunk = threading.Event()
    spinner_thread = None

    def stop_spinner():
        spin_stop.set()
        if spinner_thread is not None and spinner_thread.is_alive():
            spinner_thread.join()

    def start_spinner():
        """每个请求都重新转圈：工具调用后的第二次等待也要有动画。"""
        nonlocal spinner_thread
        spin_stop.clear()
        first_chunk.clear()
        spinner_thread = threading.Thread(
            target=spinner, args=(spin_stop, first_chunk), daemon=True
        )
        spinner_thread.start()

    printed = False
    rounds = 0
    answers = []
    tool_log = []
    error = None

    set_cursor(False)
    try:
        while True:
            outcome = Outcome()
            start_spinner()
            for piece in stream_answer(client, model_name, messages, first_chunk.set, outcome):
                if not printed:
                    stop_spinner()  # 等动画擦干净，正文从行首开始
                    printed = True
                print(piece, end="", flush=True)
                answers.append(piece)

            if outcome.error:
                error = outcome.error
                break

            calls = [outcome.tool_calls[i] for i in sorted(outcome.tool_calls)]
            if not calls:
                break
            if rounds >= MAX_TOOL_ROUNDS:
                error = "工具调用超过 %d 次，已中止" % MAX_TOOL_ROUNDS
                break
            rounds += 1

            stop_spinner()
            if printed:
                print()
                printed = False

            # 把这轮的 assistant 工具请求写回对话
            messages.append(
                {
                    "role": "assistant",
                    "content": outcome.text or None,
                    "tool_calls": [
                        {
                            "id": call["id"] or "call_%d" % i,
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": call["arguments"] or "{}",
                            },
                        }
                        for i, call in enumerate(calls)
                    ],
                }
            )
            # 依次执行工具并回填结果
            for i, call in enumerate(calls):
                result = run_tool(call["name"], call["arguments"])
                print("[工具] %s → %s" % (call["name"], result))
                tool_log.append(
                    {
                        "name": call["name"],
                        "arguments": call["arguments"],
                        "result": result,
                        "time": datetime.now().strftime("%H:%M:%S"),
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"] or "call_%d" % i,
                        "content": result,
                    }
                )
    except KeyboardInterrupt:
        stop_spinner()
        print("\n已中断")
        return None, True, tool_log
    finally:
        stop_spinner()
        set_cursor(True)

    text = "".join(answers)
    if error:
        if text:
            # 已经打印了半截，只能贴一句提示，不能假装回答完整
            print("\n[回复中断] " + error)
        else:
            print(error)
        return (text or None), True, tool_log

    print()
    return text, False, tool_log


def main():
    if not os.path.exists(CONFIG_PATH):
        create_config()

    try:
        base_url, api_key, model_name = load_config()
    except Exception:
        print(ERROR_TEXT)
        return 1

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=REQUEST_TIMEOUT)

    history = []  # 上下文只留存内存，退出即清空
    history_path = new_history_file(model_name)  # 历史记录落盘，仅作存档

    while True:
        question, quit_now = read_question()
        if quit_now:
            return 0

        # 只把最近 HISTORY_TURNS 轮发给模型，并保证开头是 user 而不是孤立的 assistant
        recent = history[-(HISTORY_TURNS * 2):]
        while recent and recent[0]["role"] != "user":
            recent.pop(0)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(recent)
        messages.append({"role": "user", "content": question})

        answer, failed, tool_log = ask_once(client, model_name, messages)
        if failed:
            # 失败或中断：本轮不入上下文，避免留下没有回复的提问或残缺回答
            continue
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
        save_turn(history_path, question, answer, tool_log)


if __name__ == "__main__":
    sys.exit(main())
