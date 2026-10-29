"""Agent Skills 规范的 Skill 动态加载。

初始化时以「程序启动时的工作目录」为项目根，扫描 `.agents/skills/` 下的各个
Skill 子目录：每个子目录顶层的 `SKILL.md` 以 YAML Frontmatter 声明必需的
`name` 与 `description`。本阶段只登记这两个字段，不读取正文。

完整内容按需进入上下文：`loadSkill` 工具被模型调用时才读文件，读取范围
始终限制在该 Skill 目录内部。
"""

from __future__ import annotations

import locale
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ToolError
from .tools.spec import ToolSpec

# Frontmatter 位于文件开头，扫描阶段只读这么多字节，避免把正文整个载入内存
FRONTMATTER_MAX_BYTES = 64 * 1024
# loadSkill 单个文件的读取上限，与文件工具保持一致
MAX_SKILL_FILE_BYTES = 2 * 1024 * 1024
# 注入 System Prompt 时单条描述的截断长度
PROMPT_DESCRIPTION_MAX_CHARS = 400

SKILL_FILE = "SKILL.md"
SKILLS_DIR_PARTS = (".agents", "skills")

PROMPT_HEADER = "You have access to the following skills:"
PROMPT_FOOTER = (
    "Use the loadSkill tool to load the full instructions of a skill when needed. "
    "You can also load additional files referenced by a skill."
)


@dataclass(frozen=True, slots=True)
class SkillInfo:
    """一个已注册 Skill 的元信息（初始化阶段只保留这两项）。"""

    name: str
    description: str
    directory: Path


class SkillLibrary:
    """扫描并持有项目根下 `.agents/skills/` 的 Skill 清单。"""

    def __init__(self, project_root: Path | str | None = None) -> None:
        # 不传根目录时取「当前进程工作目录」——即程序启动时的工作目录
        root = Path.cwd() if project_root is None else project_root
        self._root = Path(root).expanduser().resolve()
        self._skills_dir = self._root.joinpath(*SKILLS_DIR_PARTS)
        self._skills: dict[str, SkillInfo] = {}
        self._skipped: list[dict[str, str]] = []
        self._scan()

    # ------------------------------------------------------------------ 属性

    @property
    def root(self) -> Path:
        return self._root

    @property
    def skills_dir(self) -> Path:
        return self._skills_dir

    @property
    def skills(self) -> list[SkillInfo]:
        return list(self._skills.values())

    @property
    def skipped(self) -> list[dict[str, str]]:
        """扫描时被跳过的目录及原因，便于排查为什么某个 Skill 不可用。"""
        return [dict(item) for item in self._skipped]

    def __bool__(self) -> bool:
        return bool(self._skills)

    # ------------------------------------------------------------------ 查询

    def get(self, name: str) -> SkillInfo | None:
        """按名称查找：先精确匹配，再忽略大小写匹配。"""
        if not isinstance(name, str) or not name.strip():
            return None
        key = name.strip()
        info = self._skills.get(key)
        if info is not None:
            return info
        folded = key.casefold()
        for candidate in self._skills.values():
            if candidate.name.casefold() == folded:
                return candidate
        return None

    def names(self) -> list[str]:
        return list(self._skills)

    # ------------------------------------------------------------------ 提示词

    def prompt_block(self) -> str:
        """拼出注入 System Prompt 的技能清单；没有 Skill 时返回空串。"""
        if not self._skills:
            return ""
        lines = [PROMPT_HEADER, ""]
        for info in self._skills.values():
            lines.append("- %s: %s" % (info.name, _one_line(info.description)))
        lines.append("")
        lines.append(PROMPT_FOOTER)
        return "\n".join(lines)

    # ------------------------------------------------------------------ 读取

    def load(self, name: str, filename: str | None = None) -> dict[str, Any]:
        """`loadSkill` 的处理函数：只在被调用时才把文件内容交给模型。"""
        info = self.get(name)
        if info is None:
            return {
                "ok": False,
                "error": "未找到名为「%s」的 Skill" % name,
                "available": self.names(),
            }

        target_name = (filename or "").strip()
        if not target_name:
            path = info.directory / SKILL_FILE
            if not path.is_file():
                return {
                    "ok": False,
                    "error": "Skill「%s」缺少 %s" % (info.name, SKILL_FILE),
                }
            return self._read_result(info, path)

        resolved = self._resolve_file(info, target_name)
        if isinstance(resolved, dict):
            return resolved
        return self._read_result(info, resolved)

    # ------------------------------------------------------------------ 内部

    def _scan(self) -> None:
        if not self._skills_dir.is_dir():
            return
        for entry in sorted(
            self._skills_dir.iterdir(), key=lambda item: item.name.casefold()
        ):
            if entry.name.startswith(".") or not entry.is_dir():
                continue
            self._register(entry)

    def _register(self, directory: Path) -> None:
        skill_md = directory / SKILL_FILE
        if not skill_md.is_file():
            self._skip(directory, "目录内没有 %s" % SKILL_FILE)
            return

        try:
            text = _read_head(skill_md)
        except OSError as exc:
            self._skip(directory, "无法读取 %s：%s" % (SKILL_FILE, exc))
            return

        fields = parse_frontmatter(text)
        if fields is None:
            self._skip(directory, "%s 缺少 YAML Frontmatter" % SKILL_FILE)
            return

        name = (fields.get("name") or "").strip()
        description = (fields.get("description") or "").strip()
        if not name or not description:
            self._skip(directory, "Frontmatter 缺少必需字段 name/description")
            return
        if name in self._skills:
            self._skip(directory, "Skill 名称重复：%s" % name)
            return

        self._skills[name] = SkillInfo(name, description, directory.resolve())

    def _skip(self, directory: Path, reason: str) -> None:
        self._skipped.append({"directory": str(directory), "reason": reason})

    def _resolve_file(self, info: SkillInfo, filename: str) -> Path | dict[str, Any]:
        """把 filename 解析成 Skill 目录内的文件。

        兼容三种写法：相对 Skill 目录、相对项目根、绝对路径；精确匹配优先，
        匹配不到时按文件名在 Skill 目录内递归搜索，唯一命中才读取。
        """
        raw = Path(filename).expanduser()
        if raw.is_absolute():
            candidates = [raw]
        else:
            candidates = [info.directory / raw, self._root / raw]

        for candidate in candidates:
            resolved = candidate.resolve(strict=False)
            if not resolved.is_file():
                continue
            if not _inside(info.directory, resolved):
                break  # 落到 Skill 目录外面：转入搜索，最后统一报错
            return resolved

        matches = self._search_by_name(info, Path(filename).name)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return {
                "ok": False,
                "error": "「%s」匹配到多个文件，请用更完整的相对路径重试" % filename,
                "candidates": [
                    _display(info.directory, item) for item in matches
                ],
            }
        raise ToolError(
            "Skill「%s」内找不到文件：%s（读取范围仅限该 Skill 目录）"
            % (info.name, filename)
        )

    def _search_by_name(self, info: SkillInfo, basename: str) -> list[Path]:
        """在 Skill 目录内递归找同名文件，返回去重后的绝对路径。"""
        found: dict[Path, Path] = {}
        folded = basename.casefold()
        for item in info.directory.rglob("*"):
            if not item.is_file():
                continue
            if item.name != basename and item.name.casefold() != folded:
                continue
            resolved = item.resolve(strict=False)
            if not _inside(info.directory, resolved):
                continue
            found[resolved] = resolved
        return [found[key] for key in sorted(found, key=str)]

    def _read_result(self, info: SkillInfo, path: Path) -> dict[str, Any]:
        content, encoding, truncated = _read_text(path)
        result: dict[str, Any] = {
            "ok": True,
            "skill": info.name,
            "file": _display(info.directory, path),
            "encoding": encoding,
            "content": content,
        }
        if truncated:
            result["truncated"] = True
            result["note"] = "文件超过 %d 字节，仅返回开头部分" % MAX_SKILL_FILE_BYTES
        return result


def build_load_skill_tool(library: SkillLibrary) -> ToolSpec:
    """构造 `loadSkill` 工具：Skill 全文只在被调用时进入对话上下文。"""

    def handler(name: str, filename: str | None = None) -> dict[str, Any]:
        return library.load(name, filename)

    return ToolSpec(
        name="loadSkill",
        description=(
            "按需加载 .agents/skills 目录下某个 Skill 的完整说明。"
            "System Prompt 里只有技能清单；调用本工具后才会返回 SKILL.md 全文"
            "（或指定的附加文件），内容会进入对话上下文。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Skill 名称，取自 System Prompt 中的技能清单",
                },
                "filename": {
                    "type": "string",
                    "description": (
                        "可选：该 Skill 目录内需要加载的附加文件（相对 Skill 目录、"
                        "项目相对或绝对路径，也支持只给文件名）；省略时加载 SKILL.md 全文"
                    ),
                },
            },
            "required": ["name"],
        },
        handler=handler,
    )


# ---------------------------------------------------------------------- Frontmatter


def parse_frontmatter(text: str) -> dict[str, str] | None:
    """解析文件开头的 YAML Frontmatter，只提取顶层标量字段。

    没有成对的 ```---``` 包裹时返回 None。支持简单 `key: value`、引号包裹
    的值，以及 `|` / `>` 块标量（Agent Skills 里长 description 的常见写法）；
    嵌套映射（如 metadata）会被整体跳过。name/description 之外的复杂 YAML
    不做完整解析——本模块只需要这两个必需字段。
    """
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            end = index
            break
    if end is None:
        return None

    fields: dict[str, str] = {}
    block = lines[1:end]
    index = 0
    while index < len(block):
        line = block[index]
        if not line.strip() or line[:1].isspace():
            index += 1
            continue
        key, separator, rest = line.partition(":")
        if not separator:
            index += 1
            continue
        key = key.strip()
        rest = rest.strip()

        if rest in ("|", "|-", "|+", ">", ">-", ">+"):
            # 块标量：收集后续缩进行；> 折叠成单行，| 保留换行
            block_lines: list[str] = []
            index += 1
            while index < len(block) and (
                not block[index].strip() or block[index][:1].isspace()
            ):
                stripped = block[index].strip()
                if stripped:
                    block_lines.append(stripped)
                index += 1
            joiner = " " if rest.startswith(">") else "\n"
            fields[key] = joiner.join(block_lines).strip()
            continue

        if not rest:
            # 嵌套映射或空值：跳过整个缩进块
            index += 1
            while index < len(block) and block[index][:1].isspace():
                index += 1
            continue

        fields[key] = _unquote(rest)
        index += 1
    return fields


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


# ---------------------------------------------------------------------- 文件读取


def _read_head(path: Path) -> str:
    with path.open("rb") as handle:
        data = handle.read(FRONTMATTER_MAX_BYTES)
    return data.decode("utf-8-sig", errors="replace")


def _read_text(path: Path) -> tuple[str, str, bool]:
    """读取文本文件，返回 (内容, 编码, 是否被截断)。"""
    size = path.stat().st_size
    truncated = size > MAX_SKILL_FILE_BYTES
    data = path.read_bytes()[:MAX_SKILL_FILE_BYTES]
    if b"\x00" in data:
        raise ToolError("文件包含二进制内容，不是纯文本：%s" % path.name)

    encodings = ["utf-8-sig", "utf-8", locale.getpreferredencoding(False), "gb18030"]
    seen: set[str] = set()
    for encoding in encodings:
        normalized = encoding.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            return data.decode(encoding), encoding, truncated
        except UnicodeDecodeError:
            continue
    raise ToolError("无法识别文本编码：%s" % path.name)


# ---------------------------------------------------------------------- 路径工具


def _inside(directory: Path, path: Path) -> bool:
    return path == directory or directory in path.parents


def _display(directory: Path, path: Path) -> str:
    try:
        return path.relative_to(directory).as_posix()
    except ValueError:
        return str(path)


def _one_line(description: str) -> str:
    text = " ".join(description.split())
    if len(text) > PROMPT_DESCRIPTION_MAX_CHARS:
        text = text[:PROMPT_DESCRIPTION_MAX_CHARS].rstrip() + "…"
    return text
