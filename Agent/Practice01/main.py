"""命令行对话工具：多轮对话，上下文保留在内存中，退出即清空。"""

import configparser
import os
import sys
import threading
from datetime import datetime

from openai import OpenAI

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


def new_history_file(model_name):
    """为本次运行创建一个历史记录文件，返回路径。"""
    os.makedirs(HISTORY_DIR, exist_ok=True)
    path = os.path.join(HISTORY_DIR, datetime.now().strftime("%Y%m%d_%H%M%S") + ".txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# 模型：%s\n# 开始：%s\n" % (model_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    return path


def save_turn(path, question, answer):
    """把一次成功的问答追加到历史文件；写失败不影响对话本身。"""
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n[%s] 用户\n%s\n" % (datetime.now().strftime("%H:%M:%S"), question))
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
    """一次流式调用的结果：把「模型产出的内容」与「失败」分开。"""

    def __init__(self):
        self.parts = []
        self.error = None

    @property
    def text(self):
        return "".join(self.parts)


def stream_answer(client, model_name, messages, on_first_chunk, outcome):
    """流式调用，逐段产出文本。

    错误文案不混进正文：调用方据此决定「失败提示照打、但不写入上下文」，
    避免模型把自己没说过的话当成历史。
    """
    try:
        stream = client.chat.completions.create(
            model=model_name,
            messages=messages,
            max_tokens=MAX_TOKENS,
            stream=True,
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
    except KeyboardInterrupt:
        raise
    except Exception:
        outcome.error = ERROR_TEXT


def read_question():
    """读取一次输入。返回 (内容, 是否退出)；退出时内容为 None。"""
    print("等待用户输入：")
    try:
        line = input()
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
    """跑一次请求并打印回复；返回 (回答文本, 是否失败)。"""
    spin_stop = threading.Event()
    first_chunk = threading.Event()
    spinner_thread = threading.Thread(
        target=spinner, args=(spin_stop, first_chunk), daemon=True
    )

    outcome = Outcome()
    printed = False

    set_cursor(False)
    spinner_thread.start()
    try:
        for piece in stream_answer(client, model_name, messages, first_chunk.set, outcome):
            if not printed:
                spin_stop.set()  # 等动画擦干净，正文从行首开始
                spinner_thread.join()
                printed = True
            print(piece, end="", flush=True)
    except KeyboardInterrupt:
        spin_stop.set()
        print("\n已中断")
        return None, True
    finally:
        spin_stop.set()
        if spinner_thread.is_alive():
            spinner_thread.join()
        set_cursor(True)

    if outcome.error:
        if printed:
            # 已经打印了半截，只能贴一句提示，不能假装回答完整
            print("\n[回复中断] " + outcome.error)
        else:
            print(outcome.error)
        return (outcome.text or None), True

    print()
    return outcome.text, False


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

        answer, failed = ask_once(client, model_name, messages)
        if failed:
            # 失败或中断：本轮不入上下文，避免留下没有回复的提问或残缺回答
            continue
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
        save_turn(history_path, question, answer)


if __name__ == "__main__":
    sys.exit(main())
