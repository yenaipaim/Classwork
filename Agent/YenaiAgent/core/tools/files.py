"""本地文件工具：沙箱根由外部注入。

模型能碰到的范围完全由构造参数 ``root`` 决定；所有相对路径都以它为基准，
解析后必须仍落在 root 内，从而挡住 ``..`` 与符号链接穿越。
"""

from __future__ import annotations

import codecs
import locale
import mimetypes
import os
import shutil
from pathlib import Path

from ..errors import ToolError
from .spec import ToolRegistry, ToolSpec

MAX_TEXT_BYTES = 2 * 1024 * 1024

TEXT_SUFFIXES = {
    ".bat",
    ".c",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".env",
    ".gitignore",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".log",
    ".lua",
    ".md",
    ".php",
    ".properties",
    ".ps1",
    ".py",
    ".rb",
    ".rst",
    ".sh",
    ".sql",
    ".svg",
    ".tex",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}


class FileToolbox:
    """一组绑定到固定沙箱根的文件工具。"""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root).expanduser().resolve()
        if not self._root.is_dir():
            raise ToolError("沙箱根目录不存在：%s" % self._root)

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------------------ 注册

    def specs(self) -> list[ToolSpec]:
        """按旧版顺序返回 10 个文件工具的规格。"""
        definitions = [
            (
                "get_current_working_directory",
                "获取当前 Python 进程的工作目录和项目根目录",
                {"type": "object", "properties": {}, "required": []},
                self.get_current_working_directory,
            ),
            (
                "list_directory_contents",
                "列出项目内指定目录的直接子文件和子目录，不递归",
                {
                    "type": "object",
                    "properties": {
                        "directory": {
                            "type": "string",
                            "description": "项目内目录路径，可使用相对或绝对路径",
                        }
                    },
                    "required": ["directory"],
                },
                self.list_directory_contents,
            ),
            (
                "get_file_type",
                "获取项目内指定文件的扩展名、MIME 类型及是否为纯文本",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "项目内文件路径"}
                    },
                    "required": ["path"],
                },
                self.get_file_type,
            ),
            (
                "read_text_file",
                "读取项目内纯文本文件的全部内容，支持 UTF-8、GB18030 等常见编码",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "项目内纯文本文件路径"}
                    },
                    "required": ["path"],
                },
                self.read_text_file,
            ),
            (
                "create_file",
                "在项目内指定目录下创建一个新的空文件，不覆盖已有文件",
                {
                    "type": "object",
                    "properties": {
                        "directory": {"type": "string", "description": "已存在的项目内目录"},
                        "filename": {"type": "string", "description": "不含目录部分的文件名"},
                    },
                    "required": ["directory", "filename"],
                },
                self.create_file,
            ),
            (
                "edit_text_file",
                "用给定内容完整替换项目内纯文本文件的现有内容",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "项目内纯文本文件路径"},
                        "content": {"type": "string", "description": "替换后的完整文件内容"},
                    },
                    "required": ["path", "content"],
                },
                self.edit_text_file,
            ),
            (
                "create_directory",
                "在项目内创建目录，缺少的父目录会一并创建",
                {
                    "type": "object",
                    "properties": {
                        "directory": {"type": "string", "description": "要创建的项目内目录路径"}
                    },
                    "required": ["directory"],
                },
                self.create_directory,
            ),
            (
                "delete_directory",
                "递归删除项目内指定目录及其全部内容，不能删除项目根目录",
                {
                    "type": "object",
                    "properties": {
                        "directory": {"type": "string", "description": "要删除的项目内目录路径"}
                    },
                    "required": ["directory"],
                },
                self.delete_directory,
            ),
            (
                "delete_file",
                "删除项目内指定文件",
                {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "要删除的项目内文件路径"}
                    },
                    "required": ["path"],
                },
                self.delete_file,
            ),
            (
                "rename_path",
                "重命名项目内的文件或目录，新名称必须与原路径位于同一目录",
                {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "要重命名的项目内文件或目录路径",
                        },
                        "new_name": {"type": "string", "description": "新名称，不能包含目录路径"},
                    },
                    "required": ["path", "new_name"],
                },
                self.rename_path,
            ),
        ]
        return [
            ToolSpec(name=name, description=description, parameters=parameters, handler=handler)
            for name, description, parameters, handler in definitions
        ]

    def register(self, registry: ToolRegistry) -> ToolRegistry:
        for spec in self.specs():
            registry.register(spec)
        return registry

    # ------------------------------------------------------------------ 工具

    def get_current_working_directory(self) -> dict:
        return {"ok": True, "cwd": os.getcwd(), "project_root": str(self._root)}

    def list_directory_contents(self, directory: str) -> dict:
        path = self._resolve(directory, "directory")
        self._require_directory(path)

        entries = []
        for entry in sorted(path.iterdir(), key=lambda item: item.name.casefold()):
            if entry.is_symlink():
                entry_type = "symlink"
            elif entry.is_dir():
                entry_type = "directory"
            elif entry.is_file():
                entry_type = "file"
            else:
                entry_type = "other"
            entries.append(
                {
                    "name": entry.name,
                    "type": entry_type,
                    "path": self._display(entry),
                    "size": entry.stat(follow_symlinks=False).st_size,
                }
            )
        return {
            "ok": True,
            "directory": self._display(path),
            "count": len(entries),
            "entries": entries,
        }

    def get_file_type(self, path: str) -> dict:
        resolved = self._resolve(path)
        if not resolved.exists():
            raise ToolError("文件不存在：%s" % self._display(resolved))

        if resolved.is_dir():
            return {
                "ok": True,
                "path": self._display(resolved),
                "type": "directory",
                "suffix": "",
                "mime_type": "inode/directory",
                "is_text": False,
            }
        if not resolved.is_file():
            raise ToolError("路径不是普通文件：%s" % self._display(resolved))

        is_text = self._supports_text(resolved)
        if is_text:
            try:
                self._decode_text(resolved)
            except (ToolError, OSError, UnicodeError):
                is_text = False

        return {
            "ok": True,
            "path": self._display(resolved),
            "type": "file",
            "suffix": resolved.suffix.lower(),
            "mime_type": self._mime_type(resolved),
            "is_text": is_text,
            "size": resolved.stat().st_size,
        }

    def read_text_file(self, path: str) -> dict:
        resolved = self._resolve(path)
        self._require_file(resolved)
        if not self._supports_text(resolved):
            raise ToolError("仅支持读取纯文本文件：%s" % self._display(resolved))

        content, encoding = self._decode_text(resolved)
        return {
            "ok": True,
            "path": self._display(resolved),
            "encoding": encoding,
            "content": content,
        }

    def create_file(self, directory: str, filename: str) -> dict:
        parent = self._resolve(directory, "directory")
        self._require_directory(parent)
        self._require_plain_name(filename, "filename")

        target = self._resolve(str(parent / filename), "filename")
        with target.open("x", encoding="utf-8"):
            pass
        return {"ok": True, "path": self._display(target), "message": "文件已创建"}

    def edit_text_file(self, path: str, content: str) -> dict:
        resolved = self._resolve(path)
        self._require_file(resolved)
        if not self._supports_text(resolved):
            raise ToolError("仅支持编辑纯文本文件：%s" % self._display(resolved))
        if not isinstance(content, str):
            raise ToolError("content 必须是字符串")

        _, encoding = self._decode_text(resolved)
        with resolved.open("w", encoding=encoding, newline="") as handle:
            handle.write(content)
        return {
            "ok": True,
            "path": self._display(resolved),
            "encoding": encoding,
            "size": resolved.stat().st_size,
            "message": "文件内容已替换",
        }

    def create_directory(self, directory: str) -> dict:
        path = self._resolve(directory, "directory")
        path.mkdir(parents=True, exist_ok=False)
        return {"ok": True, "path": self._display(path), "message": "目录已创建"}

    def delete_directory(self, directory: str) -> dict:
        path = self._resolve(directory, "directory")
        self._require_directory(path)
        if path == self._root:
            raise ToolError("不能删除项目根目录")

        shutil.rmtree(path)
        return {"ok": True, "path": self._display(path), "message": "目录已删除"}

    def delete_file(self, path: str) -> dict:
        resolved = self._resolve(path)
        self._require_file(resolved)
        resolved.unlink()
        return {"ok": True, "path": self._display(resolved), "message": "文件已删除"}

    def rename_path(self, path: str, new_name: str) -> dict:
        source = self._resolve(path)
        if not source.exists():
            raise ToolError("文件或目录不存在：%s" % self._display(source))
        if source == self._root:
            raise ToolError("不能重命名项目根目录")
        self._require_plain_name(new_name, "new_name")

        target = self._resolve(str(source.parent / new_name), "new_name")
        if target.exists():
            raise ToolError("目标路径已存在：%s" % self._display(target))

        entry_type = "directory" if source.is_dir() else "file"
        source.rename(target)
        return {
            "ok": True,
            "old_path": self._display(source),
            "new_path": self._display(target),
            "type": entry_type,
            "message": "重命名成功",
        }

    # ------------------------------------------------------------------ 内部

    def _inside(self, path: Path) -> bool:
        return path == self._root or self._root in path.parents

    def _resolve(self, value, field_name: str = "path") -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ToolError("%s 必须是非空字符串" % field_name)

        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = self._root / candidate
        resolved = candidate.resolve(strict=False)
        if not self._inside(resolved):
            raise ToolError("%s 必须位于项目目录内：%s" % (field_name, self._root))
        return resolved

    def _display(self, path: Path) -> str:
        relative = path.relative_to(self._root)
        return "." if str(relative) == "." else str(relative)

    def _require_directory(self, path: Path) -> None:
        if not path.exists():
            raise ToolError("目录不存在：%s" % self._display(path))
        if not path.is_dir():
            raise ToolError("路径不是目录：%s" % self._display(path))

    def _require_file(self, path: Path) -> None:
        if not path.exists():
            raise ToolError("文件不存在：%s" % self._display(path))
        if not path.is_file():
            raise ToolError("路径不是文件：%s" % self._display(path))

    def _require_plain_name(self, value, field_name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ToolError("%s 必须是非空字符串" % field_name)
        if Path(value).name != value or value in (".", ".."):
            raise ToolError("%s 只能是名称，不能包含目录路径" % field_name)

    def _mime_type(self, path: Path) -> str:
        mime_type, _ = mimetypes.guess_type(path.name, strict=False)
        return mime_type or "application/octet-stream"

    def _supports_text(self, path: Path) -> bool:
        suffix = path.suffix.lower()
        return suffix == "" or suffix in TEXT_SUFFIXES or self._mime_type(path).startswith("text/")

    def _decode_text(self, path: Path) -> tuple[str, str]:
        if path.stat().st_size > MAX_TEXT_BYTES:
            raise ToolError(
                "文本文件超过 %d 字节，拒绝读取：%s" % (MAX_TEXT_BYTES, self._display(path))
            )

        data = path.read_bytes()
        if data.startswith(codecs.BOM_UTF8):
            return data.decode("utf-8-sig"), "utf-8-sig"
        if data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
            return data.decode("utf-16"), "utf-16"
        if b"\x00" in data:
            raise ToolError("文件包含二进制内容，不是纯文本：%s" % self._display(path))

        encodings = ["utf-8", locale.getpreferredencoding(False), "gb18030"]
        seen = set()
        for encoding in encodings:
            normalized = encoding.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            try:
                return data.decode(encoding), encoding
            except UnicodeDecodeError:
                continue
        raise ToolError("无法识别文本编码：%s" % self._display(path))