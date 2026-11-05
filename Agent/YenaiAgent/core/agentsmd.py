"""AGENTS.md：项目约定文件的读取与提示词包装。

注入策略是「一次注入，全程复用」：会话首次加载时读一次文件，之后每一轮都
把同一段文本放在 System Prompt 末尾，不再重读文件、也不再追加新消息。
好处是前缀稳定 —— 内容一个字都不变，模型侧的提示词缓存才不会每轮失效。
原文同时写入会话事件日志，`/resume` 恢复会话时无需重新读盘也能复用。
"""

from __future__ import annotations

from pathlib import Path

#: 注入块的开头，模型据此知道这段是项目约定而不是用户提问
PROJECT_PROMPT_TITLE = "项目约定（来自 AGENTS.md，会话首次加载时注入，后续轮次直接复用）："
#: 文件被截断时的说明
TRUNCATED_NOTE = "\n\n（AGENTS.md 超过 %d 字符，后面已截断）"


def project_prompt_path(root: Path | str, name: str) -> Path:
    """项目根目录下的约定文件路径；name 为空时返回一个不存在的路径。"""
    base = Path(root)
    if not name:
        return base / ""
    return base / name


def read_project_prompt(
    root: Path | str, name: str, max_chars: int = 20000
) -> str:
    """读取约定文件并包成提示词块；文件不存在或为空时返回空串。

    读盘失败（权限、编码、目录）都当成「没有约定文件」处理：这只是一段
    附加说明，不该因为它让会话起不来。
    """
    path = project_prompt_path(root, name)
    try:
        if not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if not text:
        return ""
    return wrap_project_prompt(text, max_chars)


def wrap_project_prompt(text: str, max_chars: int = 20000) -> str:
    """加标题，超长截断；换行统一成 \\n，保证每轮注入的内容逐字节一致。"""
    body = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    note = ""
    if max_chars > 0 and len(body) > max_chars:
        body = body[:max_chars].rstrip()
        note = TRUNCATED_NOTE % max_chars
    return PROJECT_PROMPT_TITLE + "\n\n" + body + note
