"""本地文件操作工具。

所有文件路径都限定在 Practice02 目录内，避免模型通过路径穿越或符号链接
访问、修改项目目录之外的内容。
"""

import codecs
import json
import locale
import mimetypes
import os
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
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


class FileToolError(ValueError):
    """文件工具的可预期错误，错误文本会直接返回给模型。"""


def _inside_project(path):
    return path == PROJECT_ROOT or PROJECT_ROOT in path.parents


def _resolve_project_path(value, field_name="path"):
    if not isinstance(value, str) or not value.strip():
        raise FileToolError("%s 必须是非空字符串" % field_name)

    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    resolved = candidate.resolve(strict=False)
    if not _inside_project(resolved):
        raise FileToolError("%s 必须位于项目目录内：%s" % (field_name, PROJECT_ROOT))
    return resolved


def _display_path(path):
    relative = path.relative_to(PROJECT_ROOT)
    return "." if str(relative) == "." else str(relative)


def _require_directory(path):
    if not path.exists():
        raise FileToolError("目录不存在：%s" % _display_path(path))
    if not path.is_dir():
        raise FileToolError("路径不是目录：%s" % _display_path(path))


def _require_file(path):
    if not path.exists():
        raise FileToolError("文件不存在：%s" % _display_path(path))
    if not path.is_file():
        raise FileToolError("路径不是文件：%s" % _display_path(path))


def _mime_type(path):
    mime_type, _ = mimetypes.guess_type(path.name, strict=False)
    return mime_type or "application/octet-stream"


def _supports_text(path):
    suffix = path.suffix.lower()
    mime_type = _mime_type(path)
    return suffix == "" or suffix in TEXT_SUFFIXES or mime_type.startswith("text/")


def _decode_text(path):
    size = path.stat().st_size
    if size > MAX_TEXT_BYTES:
        raise FileToolError(
            "文本文件超过 %d 字节，拒绝读取：%s" % (MAX_TEXT_BYTES, _display_path(path))
        )

    data = path.read_bytes()
    if data.startswith(codecs.BOM_UTF8):
        return data.decode("utf-8-sig"), "utf-8-sig"
    if data.startswith(codecs.BOM_UTF16_LE):
        return data.decode("utf-16"), "utf-16"
    if data.startswith(codecs.BOM_UTF16_BE):
        return data.decode("utf-16"), "utf-16"
    if b"\x00" in data:
        raise FileToolError("文件包含二进制内容，不是纯文本：%s" % _display_path(path))

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
    raise FileToolError("无法识别文本编码：%s" % _display_path(path))


def get_current_working_directory():
    return {
        "ok": True,
        "cwd": os.getcwd(),
        "project_root": str(PROJECT_ROOT),
    }


def list_directory_contents(directory):
    path = _resolve_project_path(directory, "directory")
    _require_directory(path)

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
                "path": _display_path(entry),
                "size": entry.stat(follow_symlinks=False).st_size,
            }
        )

    return {
        "ok": True,
        "directory": _display_path(path),
        "count": len(entries),
        "entries": entries,
    }


def get_file_type(path):
    resolved = _resolve_project_path(path)
    if not resolved.exists():
        raise FileToolError("文件不存在：%s" % _display_path(resolved))

    if resolved.is_dir():
        return {
            "ok": True,
            "path": _display_path(resolved),
            "type": "directory",
            "suffix": "",
            "mime_type": "inode/directory",
            "is_text": False,
        }
    if not resolved.is_file():
        raise FileToolError("路径不是普通文件：%s" % _display_path(resolved))

    is_text = _supports_text(resolved)
    if is_text:
        try:
            _decode_text(resolved)
        except (FileToolError, OSError, UnicodeError):
            is_text = False

    return {
        "ok": True,
        "path": _display_path(resolved),
        "type": "file",
        "suffix": resolved.suffix.lower(),
        "mime_type": _mime_type(resolved),
        "is_text": is_text,
        "size": resolved.stat().st_size,
    }


def read_text_file(path):
    resolved = _resolve_project_path(path)
    _require_file(resolved)
    if not _supports_text(resolved):
        raise FileToolError("仅支持读取纯文本文件：%s" % _display_path(resolved))

    content, encoding = _decode_text(resolved)
    return {
        "ok": True,
        "path": _display_path(resolved),
        "encoding": encoding,
        "content": content,
    }


def create_file(directory, filename):
    parent = _resolve_project_path(directory, "directory")
    _require_directory(parent)
    if not isinstance(filename, str) or not filename.strip():
        raise FileToolError("filename 必须是非空字符串")
    if Path(filename).name != filename or filename in (".", ".."):
        raise FileToolError("filename 只能是文件名，不能包含目录路径")

    target = _resolve_project_path(str(parent / filename), "filename")
    with target.open("x", encoding="utf-8"):
        pass
    return {
        "ok": True,
        "path": _display_path(target),
        "message": "文件已创建",
    }


def edit_text_file(path, content):
    resolved = _resolve_project_path(path)
    _require_file(resolved)
    if not _supports_text(resolved):
        raise FileToolError("仅支持编辑纯文本文件：%s" % _display_path(resolved))
    if not isinstance(content, str):
        raise FileToolError("content 必须是字符串")

    _, encoding = _decode_text(resolved)
    with resolved.open("w", encoding=encoding, newline="") as handle:
        handle.write(content)
    return {
        "ok": True,
        "path": _display_path(resolved),
        "encoding": encoding,
        "size": resolved.stat().st_size,
        "message": "文件内容已替换",
    }


def create_directory(directory):
    path = _resolve_project_path(directory, "directory")
    path.mkdir(parents=True, exist_ok=False)
    return {
        "ok": True,
        "path": _display_path(path),
        "message": "目录已创建",
    }


def delete_directory(directory):
    path = _resolve_project_path(directory, "directory")
    _require_directory(path)
    if path == PROJECT_ROOT:
        raise FileToolError("不能删除项目根目录")

    shutil.rmtree(path)
    return {
        "ok": True,
        "path": _display_path(path),
        "message": "目录已删除",
    }


def delete_file(path):
    resolved = _resolve_project_path(path)
    _require_file(resolved)
    resolved.unlink()
    return {
        "ok": True,
        "path": _display_path(resolved),
        "message": "文件已删除",
    }


FILE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_working_directory",
            "description": "获取当前 Python 进程的工作目录和项目根目录",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory_contents",
            "description": "列出项目内指定目录的直接子文件和子目录，不递归",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "项目内目录路径，可使用相对或绝对路径",
                    }
                },
                "required": ["directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_type",
            "description": "获取项目内指定文件的扩展名、MIME 类型及是否为纯文本",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "项目内文件路径"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_text_file",
            "description": "读取项目内纯文本文件的全部内容，支持 UTF-8、GB18030 等常见编码",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "项目内纯文本文件路径"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "在项目内指定目录下创建一个新的空文件，不覆盖已有文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "已存在的项目内目录"},
                    "filename": {"type": "string", "description": "不含目录部分的文件名"},
                },
                "required": ["directory", "filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_text_file",
            "description": "用给定内容完整替换项目内纯文本文件的现有内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "项目内纯文本文件路径"},
                    "content": {"type": "string", "description": "替换后的完整文件内容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_directory",
            "description": "在项目内创建目录，缺少的父目录会一并创建",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "要创建的项目内目录路径"}
                },
                "required": ["directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_directory",
            "description": "递归删除项目内指定目录及其全部内容，不能删除项目根目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "要删除的项目内目录路径"}
                },
                "required": ["directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "删除项目内指定文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要删除的项目内文件路径"}
                },
                "required": ["path"],
            },
        },
    },
]


FILE_TOOL_HANDLERS = {
    "get_current_working_directory": get_current_working_directory,
    "list_directory_contents": list_directory_contents,
    "get_file_type": get_file_type,
    "read_text_file": read_text_file,
    "create_file": create_file,
    "edit_text_file": edit_text_file,
    "create_directory": create_directory,
    "delete_directory": delete_directory,
    "delete_file": delete_file,
}

FILE_TOOL_NAMES = frozenset(FILE_TOOL_HANDLERS)


def _json_result(payload):
    return json.dumps(payload, ensure_ascii=False)


def run_file_tool(name, arguments):
    handler = FILE_TOOL_HANDLERS.get(name)
    if handler is None:
        return _json_result({"ok": False, "error": "未知文件工具：%s" % name})

    try:
        if arguments is None or not str(arguments).strip():
            parsed = {}
        else:
            parsed = json.loads(arguments)
        if not isinstance(parsed, dict):
            raise FileToolError("工具参数必须是 JSON 对象")
        return _json_result(handler(**parsed))
    except FileToolError as exc:
        return _json_result({"ok": False, "error": str(exc)})
    except json.JSONDecodeError as exc:
        return _json_result({"ok": False, "error": "工具参数不是合法 JSON：%s" % exc})
    except TypeError as exc:
        return _json_result({"ok": False, "error": "工具参数错误：%s" % exc})
    except (OSError, UnicodeError) as exc:
        return _json_result({"ok": False, "error": "文件操作失败：%s" % exc})
