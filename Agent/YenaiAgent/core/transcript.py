"""对话存档：与旧版 ``chat_history/*.txt`` 格式保持一致。

存档只是留痕，任何写入失败都不应影响对话本身，因此这里吞掉 OSError。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Sequence

from .events import ToolCallRecord


class Transcript:
    """每个会话一个文本文件，首次成功问答时才真正落盘。"""

    def __init__(self, directory: Path | str, model_name: str) -> None:
        self._directory = Path(directory)
        self._model_name = model_name
        self._path: Path | None = None

    @property
    def path(self) -> Path | None:
        return self._path

    def reset(self) -> None:
        """下一次成功问答写入新文件。"""
        self._path = None

    def save_turn(
        self,
        question: str,
        answer: str,
        tool_calls: Sequence[ToolCallRecord] = (),
    ) -> None:
        try:
            path = self._ensure_file()
            with path.open("a", encoding="utf-8") as handle:
                handle.write(
                    "\n[%s] 用户\n%s\n"
                    % (datetime.now().strftime("%H:%M:%S"), question)
                )
                for call in tool_calls:
                    handle.write(
                        "\n[工具] %s  %s\n参数：%s\n结果：%s\n"
                        % (
                            call.name,
                            call.started_at,
                            call.arguments or "{}",
                            call.output,
                        )
                    )
                handle.write("\n[回复]\n%s\n" % answer)
        except OSError:
            pass

    def _ensure_file(self) -> Path:
        if self._path is not None:
            return self._path

        self._directory.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        base = now.strftime("%Y%m%d_%H%M%S")
        path = self._directory / ("%s.txt" % base)
        index = 1
        while path.exists():
            path = self._directory / ("%s_%d.txt" % (base, index))
            index += 1

        with path.open("x", encoding="utf-8") as handle:
            handle.write(
                "# 模型：%s\n# 开始：%s\n"
                % (self._model_name, now.strftime("%Y-%m-%d %H:%M:%S"))
            )
        self._path = path
        return path