"""单轮对话命令行工具：一次输入，一次回复，无历史记忆。"""

import configparser
import os
import sys
import threading

from openai import OpenAI

# 与脚本同目录
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")

SYSTEM_PROMPT = "回答简洁，减少副词，不用 emoji。"
MAX_TOKENS = 512
ERROR_TEXT = "额度已经耗尽或者配置信息错误"

LINE = "---------------"

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


def spinner(spin_stop, first_chunk):
    """等首个 token 期间原地转圈，收到首段内容或结束信号就擦掉动画行。"""
    i = 0
    while not spin_stop.is_set() and not first_chunk.is_set():
        lead = "" if i == 0 else "\r"
        print(f"{lead}{SPINNER_PREFIX}{SPINNER_FRAMES[i % len(SPINNER_FRAMES)]}", end="", flush=True)
        i += 1
        spin_stop.wait(SPINNER_INTERVAL)
    print("\r\x1b[K", end="", flush=True)


def stream_answer(client, model_name, question, on_first_chunk):
    """流式调用，逐段产出文本。

    若尚未输出任何内容就失败，产出统一错误文案；若中途断流，则保留已产出的
    半截回答并追加提示，不把它伪装成完整回答。
    """
    got_any = False
    try:
        stream = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            max_tokens=MAX_TOKENS,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            piece = chunk.choices[0].delta.content
            if not piece:
                continue
            if not got_any:
                got_any = True
                on_first_chunk()
            yield piece
    except KeyboardInterrupt:
        raise
    except Exception:
        if got_any:
            yield "\n[回复中断] " + ERROR_TEXT
        else:
            yield ERROR_TEXT


def main():
    if not os.path.exists(CONFIG_PATH):
        create_config()

    try:
        base_url, api_key, model_name = load_config()
    except Exception:
        print(ERROR_TEXT)
        return 1

    print("等待用户输入：")
    print(LINE)
    try:
        question = input()
    except EOFError:
        print()
        print("未收到输入，已退出。")
        return 1
    except KeyboardInterrupt:
        print()
        return 0
    # 输入回车后光标已在新行，这里补下分隔线
    print(LINE)

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=REQUEST_TIMEOUT)

    spin_stop = threading.Event()
    first_chunk = threading.Event()
    spinner_thread = threading.Thread(target=spinner, args=(spin_stop, first_chunk))

    printed = False
    set_cursor(False)
    spinner_thread.start()
    try:
        for piece in stream_answer(client, model_name, question, first_chunk.set):
            if not printed:
                spinner_thread.join()  # 等动画擦干净，正文从行首开始
                printed = True
            print(piece, end="", flush=True)
        if not printed:
            spin_stop.set()  # 没有内容产出时也要停掉动画，否则线程不退出
            spinner_thread.join()
    except KeyboardInterrupt:
        spin_stop.set()
        spinner_thread.join()
        print("\n已中断")
        return 0
    finally:
        set_cursor(True)

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
