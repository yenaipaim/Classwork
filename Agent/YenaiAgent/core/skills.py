"""Agent Skills 规范的 Skill 动态加载。

初始化时以「程序启动时的工作目录」为项目根，扫描技能根目录（默认为
`.agents/skills/`，也可由 `config.ini` 的 `[skills] roots` 或 `--skills-dir`
指定，支持多个根）下的各个 Skill 子目录：每个子目录顶层的 `SKILL.md` 以 YAML Frontmatter 声明必需的
`name` 与 `description`。本阶段只登记这两个字段，不读取正文。

完整内容按需进入上下文：`loadSkill` 工具被模型调用时才读文件，读取范围
始终限制在该 Skill 目录内部。

第九次课新增 `createSkill`：模型按用户的自然语言要求新建 Skill——在第一个技能根
目录（默认 `.agents/skills/`）下建一个 kebab-case 子目录，并写入符合 Agent Skills
规范的 `SKILL.md`（YAML Frontmatter + name + description + 正文）。名称会被统一
规范成小写字母、数字与连字符；同名 Skill 已存在时直接返回提示，绝不覆盖原内容。
Skill 附属的 references/、scripts/ 等目录与文件，由模型继续调用文件工具补齐。
"""

from __future__ import annotations

import locale
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

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

# config.ini 里配置额外技能根目录的段与键：roots = D:\skills;F:\Plugin\.agents\skills
SKILLS_SECTION = "skills"
SKILLS_ROOTS_KEY = "roots"

PROMPT_HEADER = "You have access to the following skills:"
PROMPT_FOOTER = (
    "Use the loadSkill tool to load the full instructions of a skill when needed. "
    "You can also load additional files referenced by a skill."
)

# createSkill 的命名规范：小写字母、数字与单个连字符（Agent Skills 推荐的 kebab-case）
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKILL_NAME_MAX_LENGTH = 64
# 自动补全 description 时取的最大长度
DERIVED_DESCRIPTION_MAX_CHARS = 200

# YAML 里可以安全写成普通标量的字符集（其余情况退化成折叠块标量）
_PLAIN_SCALAR_SAFE = re.compile(
    r"^[A-Za-z0-9\u4e00-\u9fff ,.()（）:;!?、。，；：！？\-/+=<>%']+$"
)


@dataclass(frozen=True, slots=True)
class SkillInfo:
    """一个已注册 Skill 的元信息（初始化阶段只保留这两项）。"""

    name: str
    description: str
    directory: Path


class SkillLibrary:
    """扫描并持有一个或多个技能根目录下的 Skill 清单。

    默认根是 ``<项目根>/.agents/skills/``；多个根按给定顺序扫描，同名 Skill
    先扫到的生效，后扫到的记入 ``skipped``（并注明已加载的位置）。
    """

    def __init__(
        self,
        project_root: Path | str | None = None,
        roots: Sequence[Path | str] | None = None,
    ) -> None:
        # 不传根目录时取「当前进程工作目录」——即程序启动时的工作目录
        root = Path.cwd() if project_root is None else project_root
        self._root = Path(root).expanduser().resolve()
        if roots is None:
            roots = resolve_skill_roots(self._root)
        self._roots = [_absolute(Path(item), self._root) for item in roots]
        self._skills: dict[str, SkillInfo] = {}
        self._skipped: list[dict[str, str]] = []
        self._scan()

    # ------------------------------------------------------------------ 属性

    @property
    def root(self) -> Path:
        return self._root

    @property
    def roots(self) -> list[Path]:
        """本次扫描过的全部技能根目录（按扫描顺序）。"""
        return list(self._roots)

    @property
    def skills_dir(self) -> Path:
        """第一个技能根目录（兼容旧调用）。"""
        return self._roots[0]

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

    # ------------------------------------------------------------------ 创建

    def create(self, name: str, skill_context: str) -> dict[str, Any]:
        """`createSkill` 的处理函数：新建一个符合规范的 Skill 目录与 SKILL.md。

        只写入第一个技能根目录（`skills_dir`，默认 `.agents/skills/`），且**从不覆盖**
        已有内容：目录已存在、Skill 名已被别的根目录占用、或名称无法规范成 kebab-case，
        都返回 `ok=False` 的明确提示。
        """
        slug = normalize_skill_name(name)
        if slug is None:
            return {
                "ok": False,
                "error": (
                    "Skill 名称无法规范成小写英文格式：%r。"
                    "请使用英文 kebab-case（小写字母、数字与单个连字符），例如 \"pdf-tools\"。"
                    % (name if isinstance(name, str) else "")
                ),
                "hint": "名称只允许 a-z、0-9 与连字符，不能以连字符开头或结尾。",
                "available": self.names(),
            }

        document, fields, body = build_skill_document(slug, skill_context)
        if body == "":
            return {
                "ok": False,
                "error": (
                    "skillContext 去掉 YAML Frontmatter 后没有正文，"
                    "SKILL.md 至少需要一段说明文字。"
                ),
                "hint": "请把要写入 SKILL.md 的完整内容（含 frontmatter 或正文）一起传入。",
                "would_create": "%s/%s" % (slug, SKILL_FILE),
            }

        root = self.skills_dir
        directory = (root / slug).resolve(strict=False)
        if not _inside(root, directory):
            return {"ok": False, "error": "目标目录越出技能根目录：%s" % directory}

        existing = self.get(slug)
        if existing is not None and existing.directory != directory:
            return {
                "ok": False,
                "error": "Skill 名称已被占用：%s（已加载自 %s）" % (slug, existing.directory),
                "hint": "换一个 name，或先修改已有的 Skill 文件。",
                "available": self.names(),
            }

        try:
            root.mkdir(parents=True, exist_ok=True)
            directory.mkdir()
        except FileExistsError:
            return {
                "ok": False,
                "error": "Skill「%s」已存在：%s" % (slug, directory),
                "hint": (
                    "为避免覆盖原有内容，不会改写已存在的 Skill 目录。"
                    "要修改它请用文件工具（edit_text_file / create_file）；"
                    "要新建请换一个 name。"
                ),
                "existing_files": _list_files(directory),
                "available": self.names(),
            }
        except OSError as exc:
            # 写不下去就整个回滚，不留半个空目录
            _remove_quietly(directory)
            return {"ok": False, "error": "创建 Skill 目录失败：%s" % exc}

        try:
            target = directory / SKILL_FILE
            with target.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(document)
        except FileExistsError:
            _remove_quietly(directory)
            return {
                "ok": False,
                "error": "Skill「%s」已存在：%s" % (slug, directory),
                "hint": "同名 Skill 不会被覆盖；请换 name，或直接用文件工具修改现有 SKILL.md。",
                "available": self.names(),
            }
        except OSError as exc:
            _remove_quietly(directory)
            return {"ok": False, "error": "写入 %s 失败：%s" % (SKILL_FILE, exc)}

        # 立刻登记，让同一会话里接下来的 loadSkill 能读到新文件
        before = set(self._skills)
        self._register(directory)
        registered = slug in self._skills

        result: dict[str, Any] = {
            "ok": True,
            "skill": slug,
            "directory": str(directory),
            "file": _display(self._root, target),
            "description": fields["description"],
            "bytes": target.stat().st_size,
            "registered": registered,
            "note": (
                "SKILL.md 已按 Agent Skills 规范写入（YAML Frontmatter 含 name 与 "
                "description）。需要 references/、scripts/ 等附属目录或其他文件时，"
                "请继续调用文件工具（create_directory / create_file / edit_text_file）。"
            ),
        }
        if not registered:
            skipped = self._skipped[-1] if self._skipped else {}
            result["skipped_reason"] = skipped.get("reason", "登记失败")
        elif before:
            result["skills_total"] = len(self._skills)
        return result

    # ------------------------------------------------------------------ 内部

    def _scan(self) -> None:
        for root in self._roots:
            if not root.is_dir():
                self._skip(root, "技能根目录不存在")
                continue
            for entry in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
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
            existing = self._skills[name]
            self._skip(
                directory,
                "Skill 名称重复：%s（已加载自 %s）" % (name, existing.directory),
            )
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
            candidates = [info.directory / raw]
            # 技能根目录与项目根都算「项目相对路径」的基准，按顺序尝试
            candidates.extend(root / raw for root in self._roots)
            candidates.append(self._root / raw)

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
            "按需加载某个 Skill 目录下的完整说明。"
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


# ---------------------------------------------------------------------- 创建 Skill


def build_create_skill_tool(library: SkillLibrary) -> ToolSpec:
    """构造 `createSkill` 工具：按用户的自然语言要求新建一个 Skill。"""

    # 参数名与 JSON Schema 的键完全一致（skillContext 用小驼峰，和 searchWeb /
    # fetchWeb 一样是给模型看的名字）：注册表按键名原样把参数交给处理函数。
    def handler(name: str, skillContext: str) -> dict[str, Any]:
        return library.create(name, skillContext)

    return ToolSpec(
        name="createSkill",
        description=(
            "根据用户的要求创建一个新的 Agent Skill：在技能目录（默认 .agents/skills/）下"
            "新建一个以 name 命名的小写英文子目录，并把 skillContext 写入其中的 SKILL.md。"
            "SKILL.md 会自动补齐符合 Agent Skills 规范的 YAML Frontmatter（name 与 "
            "description）；正文为空时返回错误，同名 Skill 已存在时只返回提示、绝不覆盖。"
            "若还需要 references/、scripts/ 等附属目录或其他文件，请继续调用文件工具创建。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "Skill 名称，统一使用小写英文：只允许字母、数字与单个连字符"
                        "（kebab-case，例如 pdf-tools）。中文名或大写会被自动规范，"
                        "无法规范时返回错误提示。"
                    ),
                },
                "skillContext": {
                    "type": "string",
                    "description": (
                        "要写入 SKILL.md 的完整内容（Markdown）。可以自带 YAML "
                        "Frontmatter——其中的 name 会被改成本次的小写英文名称，缺少 "
                        "description 时从正文首段自动补一句；也可以只给正文部分。"
                    ),
                },
            },
            "required": ["name", "skillContext"],
        },
        handler=handler,
    )


def normalize_skill_name(raw: Any) -> str | None:
    """把用户给的名字规范成 Agent Skills 的 kebab-case；规范不了返回 None。"""
    if not isinstance(raw, str):
        return None
    text = raw.strip().lower()
    if not text:
        return None
    # 空格、下划线与路径分隔符视为分词；其余非法字符（含中文、标点）直接丢弃
    text = re.sub(r"[\s_/\\]+", "-", text)
    text = re.sub(r"[^a-z0-9-]+", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    if not text:
        return None
    text = text[:SKILL_NAME_MAX_LENGTH].strip("-")
    if not text or not SKILL_NAME_PATTERN.match(text):
        return None
    return text


# --- createSkill：SKILL.md 生成 ---


def build_skill_document(
    slug: str, skill_context: Any
) -> tuple[str, dict[str, str], str]:
    """把 skillContext 整理成规范的 SKILL.md 文本。

    返回 \`(完整文件内容, frontmatter 字段, 正文)\`。已有的 YAML Frontmatter 会被
    保留（name / description 之外的键原样留下），name 强制写成本次的小写英文名，
    description 缺失时从正文推导。正文为空时第三项是空串，由调用方拒绝写入。
    """
    raw = "" if skill_context is None else str(skill_context)
    raw = raw.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    kept, fields, body_lines = _split_frontmatter(raw.split("\n"))

    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    body = "\n".join(body_lines).rstrip()

    description = (fields.get("description") or "").strip()
    if not description:
        description = _derive_description(body)

    lines = ["---", "name: %s" % slug]
    lines.extend(_frontmatter_lines("description", description))
    lines.extend(item for item in kept if item.strip())
    lines.append("---")
    lines.append("")
    document = "\n".join(lines) + "\n"
    if body:
        document += body + "\n"
    return document, {"name": slug, "description": description}, body


def _split_frontmatter(lines: list[str]) -> tuple[list[str], dict[str, str], list[str]]:
    """拆出 \`(保留的 frontmatter 原行, 已解析字段, 正文行)\`。

    没有成对 --- 包裹时整段按正文处理，由调用方补上完整 Frontmatter。
    """
    if not lines or lines[0].strip() != "---":
        return [], {}, list(lines)
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            end = index
            break
    if end is None:
        return [], {}, list(lines)

    block = lines[1:end]
    body = list(lines[end + 1 :])
    fields = parse_frontmatter("\n".join(lines[: end + 1])) or {}

    kept: list[str] = []
    dropping_block_scalar = False
    for line in block:
        stripped = line.strip()
        indented = bool(line[:1].isspace())
        if dropping_block_scalar:
            if not stripped or indented:
                continue  # 块标量的续行随该键一起丢掉，稍后用规范写法重出
            dropping_block_scalar = False
        if indented:
            kept.append(line)  # 嵌套映射等附属行，原样保留
            continue
        if not stripped or stripped.startswith("#"):
            kept.append(line)
            continue
        key, separator, rest = line.partition(":")
        if separator and key.strip().lower() in ("name", "description"):
            if rest.strip() in ("|", "|-", "|+", ">", ">-", ">+"):
                dropping_block_scalar = True
            continue
        kept.append(line)
    return kept, fields, body


def _frontmatter_lines(key: str, value: str) -> list[str]:
    """把一个字段写成合法 YAML：简单标量一行搞定，复杂值用折叠块标量。"""
    text = " ".join((value or "").split())
    if not text:
        text = "由 createSkill 创建的 Skill，请补充说明。"
    if _is_plain_scalar_safe(text):
        return ["%s: %s" % (key, text)]
    return ["%s: >-" % key, "  %s" % text]


def _is_plain_scalar_safe(text: str) -> bool:
    if text[:1] in ("- ", "? ", "& ", "*", "!", "%",  "@", "`", '"', "'", "{", "[", "|", ">"):
        return False
    if text.endswith(":") or ": " in text or "#" in text:
        return False
    return bool(_PLAIN_SCALAR_SAFE.match(text))


def _derive_description(body: str) -> str:
    """正文没写 description 时，取第一段可读文字充当描述。"""
    for line in body.splitlines():
        text = line.strip()
        if not text or set(text) <= set("-=*_#"):
            continue
        # 去掉标题符号、引用符号与有序 / 无序列表符号
        text = re.sub(r"^(?:#{1,6}\s+|>\s?|[-*+]\s+|\d+\.\s+)", "", text)
        text = re.sub(r"[*_\`\"]", "", text).strip()
        if not text:
            continue
        if len(text) > DERIVED_DESCRIPTION_MAX_CHARS:
            text = text[:DERIVED_DESCRIPTION_MAX_CHARS].rstrip() + "…"
        return text
    return "由 createSkill 创建的 Skill，请补充 description 与正文说明。"


def _list_files(directory: Path, limit: int = 20) -> list[str]:
    """已存在 Skill 目录内的文件清单（相对该目录），便于判断该改而不是新建。"""
    names: list[str] = []
    try:
        for item in sorted(directory.rglob("*"), key=str):
            if item.is_file():
                names.append(_display(directory, item))
                if len(names) >= limit:
                    break
    except OSError:
        return names
    return names


def _remove_quietly(directory: Path) -> None:
    """写入失败时清掉刚建的空目录，不留半成品。"""
    shutil.rmtree(directory, ignore_errors=True)




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


# ---------------------------------------------------------------------- 根目录


def split_skill_roots(raw: str) -> list[str]:
    """把 ``roots = a;b`` 这类配置字符串拆成路径列表（``;``、``,`` 或换行分隔）。"""
    return [piece.strip() for piece in re.split(r"[;,\n]+", raw or "") if piece.strip()]


def resolve_skill_roots(
    project_root: Path | str, configured: Sequence[str] = ()
) -> list[Path]:
    """把配置里的技能根目录解析成绝对路径。

    * 空配置时退回默认 ``<项目根>/.agents/skills/``（与旧版行为完全一致）；
    * 支持 ``;`` / ``,`` 分隔多个根、``~`` 与 ``%环境变量%``；
    * 相对路径按「程序启动目录」（project_root）解析，换机器不用改代码。
    """
    base = Path(project_root).expanduser().resolve()
    pieces: list[str] = []
    for raw in configured:
        pieces.extend(split_skill_roots(str(raw)))
    if not pieces:
        return [base.joinpath(*SKILLS_DIR_PARTS)]
    roots: list[Path] = []
    seen: set[Path] = set()
    for piece in pieces:
        path = _absolute(Path(piece), base)
        if path in seen:
            continue
        seen.add(path)
        roots.append(path)
    return roots


def _absolute(path: Path, base: Path) -> Path:
    """展开 ``~`` / 环境变量，并把相对路径挂到 base 上。"""
    expanded = Path(os.path.expandvars(str(path))).expanduser()
    if not expanded.is_absolute():
        expanded = base / expanded
    return expanded.resolve(strict=False)
