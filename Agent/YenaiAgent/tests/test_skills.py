"""Skill 动态加载测试：发现、Frontmatter、System Prompt 注入与 loadSkill 工具。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.config import AppConfig
from core.context import build_messages
from core.errors import ToolError
from core.factory import build_registry
from core.session import AgentSession
from core.skills import (
    PROMPT_FOOTER,
    PROMPT_HEADER,
    SkillLibrary,
    build_load_skill_tool,
    parse_frontmatter,
)
from support import FakeBackend, text_chunks, tool_script

SIMPLE_MD = """---
name: alpha
description: Alpha skill for testing.
---

# Alpha

SECRET_BODY_MARKER
"""


def make_project(root: Path) -> Path:
    """搭一个含各种合法/非法 Skill 的项目目录。"""
    skills = root / ".agents" / "skills"

    alpha = skills / "alpha"
    (alpha / "references").mkdir(parents=True)
    (alpha / "notes").mkdir()
    (alpha / "SKILL.md").write_text(SIMPLE_MD, encoding="utf-8")
    (alpha / "references" / "extra.md").write_text("EXTRA_CONTENT", encoding="utf-8")
    (alpha / "references" / "tips.md").write_text("TIPS_A", encoding="utf-8")
    (alpha / "notes" / "tips.md").write_text("TIPS_B", encoding="utf-8")

    # 长 description 用块标量 + 嵌套 metadata，模拟真实 Agent Skills 写法
    beta = skills / "beta"
    (beta / "reference").mkdir(parents=True)
    (beta / "SKILL.md").write_text(
        "---\n"
        "name: beta\n"
        "description: |\n"
        "  Multi line description\n"
        "  continued here.\n"
        "metadata:\n"
        "  owner: someone\n"
        "---\n\n"
        "# Beta\n\nBETA_BODY\n",
        encoding="utf-8",
    )
    (beta / "reference" / "guide.md").write_text("GUIDE_CONTENT", encoding="utf-8")

    # 各种应当被跳过的目录
    (skills / "no-md").mkdir()
    bad_fm = skills / "bad-fm"
    bad_fm.mkdir()
    (bad_fm / "SKILL.md").write_text("# 没有 frontmatter\n", encoding="utf-8")
    bad_desc = skills / "bad-desc"
    bad_desc.mkdir()
    (bad_desc / "SKILL.md").write_text(
        "---\nname: bad-desc\n---\n", encoding="utf-8"
    )
    dup = skills / "dup"
    dup.mkdir()
    (dup / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: duplicate\n---\n", encoding="utf-8"
    )
    (skills / "loose.txt").write_text("not a skill", encoding="utf-8")

    (root / "outside.txt").write_text("OUTSIDE_CONTENT", encoding="utf-8")
    return root


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return make_project(tmp_path / "proj")


@pytest.fixture
def library(project: Path) -> SkillLibrary:
    return SkillLibrary(project)


# ---------------------------------------------------------------- Frontmatter


def test_parse_frontmatter_simple_and_quoted() -> None:
    fields = parse_frontmatter('---\nname: "a b"\ndescription: \'x: y\'\n---\nbody')
    assert fields == {"name": "a b", "description": "x: y"}


def test_parse_frontmatter_block_scalar_and_nested_map() -> None:
    text = (
        "---\n"
        "name: beta\n"
        "description: |\n"
        "  line one\n"
        "  line two\n"
        "metadata:\n"
        "  owner: someone\n"
        "---\nbody"
    )
    fields = parse_frontmatter(text)
    assert fields is not None
    assert fields["name"] == "beta"
    assert fields["description"] == "line one\nline two"
    assert "owner" not in fields


def test_parse_frontmatter_folded_scalar() -> None:
    text = "---\nname: f\ndescription: >\n  folded\n  lines\n---\n"
    assert parse_frontmatter(text)["description"] == "folded lines"


def test_parse_frontmatter_rejects_missing_or_unterminated() -> None:
    assert parse_frontmatter("# just markdown") is None
    assert parse_frontmatter("---\nname: x\nno closing fence") is None


# ---------------------------------------------------------------- 发现与注册


def test_scan_registers_valid_and_skips_invalid(library: SkillLibrary) -> None:
    assert library.names() == ["alpha", "beta"]
    reasons = {item["directory"].split("\\")[-1]: item["reason"] for item in library.skipped}
    assert "SKILL.md" in reasons["no-md"]
    assert "Frontmatter" in reasons["bad-fm"]
    assert "name/description" in reasons["bad-desc"]
    assert "重复" in reasons["dup"]


def test_scan_only_reads_metadata_not_body(library: SkillLibrary) -> None:
    info = library.get("alpha")
    assert info is not None
    assert info.description == "Alpha skill for testing."
    # SkillInfo 只有名称、描述与目录三个字段，没有正文
    assert set(info.__dataclass_fields__) == {"name", "description", "directory"}


def test_lookup_is_case_insensitive_fallback(library: SkillLibrary) -> None:
    assert library.get("ALPHA") is not None
    assert library.get("  alpha  ").name == "alpha"
    assert library.get("gamma") is None
    assert library.get("") is None


def test_missing_skills_dir_is_empty(tmp_path: Path) -> None:
    library = SkillLibrary(tmp_path)
    assert bool(library) is False
    assert library.prompt_block() == ""


# ---------------------------------------------------------------- 提示词注入


def test_prompt_block_lists_skills(library: SkillLibrary) -> None:
    block = library.prompt_block()
    assert block.startswith(PROMPT_HEADER)
    assert block.rstrip().endswith(PROMPT_FOOTER)
    assert "- alpha: Alpha skill for testing." in block
    assert "- beta: Multi line description continued here." in block
    assert "SECRET_BODY_MARKER" not in block  # 不包含正文


def test_build_messages_appends_skill_block(library: SkillLibrary) -> None:
    config = AppConfig(base_url="http://x", api_key="k", model_name="m")
    messages = build_messages([], "hi", config, library.prompt_block())
    assert messages[0]["role"] == "system"
    assert messages[0]["content"].startswith(config.system_prompt)
    assert PROMPT_HEADER in messages[0]["content"]


def test_build_messages_without_extra_system_unchanged() -> None:
    config = AppConfig(base_url="http://x", api_key="k", model_name="m")
    plain = build_messages([], "hi", config)
    assert plain[0]["content"] == config.system_prompt


# ---------------------------------------------------------------- loadSkill 工具


def test_registry_registers_load_skill_only_with_skills(workspace: Path) -> None:
    assert "loadSkill" not in build_registry(workspace).names()

    library = SkillLibrary(make_project(workspace))
    registry = build_registry(workspace, skills=library)
    names = registry.names()
    assert "loadSkill" in names
    assert names.index("loadSkill") == names.index("RunCli") + 1


def test_load_skill_tool_schema(library: SkillLibrary) -> None:
    schema = build_load_skill_tool(library).schema()
    function = schema["function"]
    assert function["name"] == "loadSkill"
    assert function["parameters"]["required"] == ["name"]
    assert set(function["parameters"]["properties"]) == {"name", "filename"}


def test_load_only_name_returns_skill_md(library: SkillLibrary) -> None:
    result = library.load("alpha")
    assert result["ok"] is True
    assert result["file"] == "SKILL.md"
    assert "SECRET_BODY_MARKER" in result["content"]


def test_load_filename_relative_to_skill_dir(library: SkillLibrary) -> None:
    result = library.load("alpha", "references/extra.md")
    assert result["ok"] is True
    assert result["file"] == "references/extra.md"
    assert result["content"] == "EXTRA_CONTENT"


def test_load_filename_project_relative(library: SkillLibrary) -> None:
    result = library.load("alpha", ".agents/skills/alpha/references/extra.md")
    assert result["ok"] is True
    assert result["content"] == "EXTRA_CONTENT"


def test_load_filename_absolute(library: SkillLibrary, project: Path) -> None:
    absolute = project / ".agents" / "skills" / "alpha" / "references" / "extra.md"
    result = library.load("alpha", str(absolute))
    assert result["ok"] is True
    assert result["content"] == "EXTRA_CONTENT"


def test_load_unique_basename_searches_recursively(library: SkillLibrary) -> None:
    result = library.load("beta", "guide.md")
    assert result["ok"] is True
    assert result["file"] == "reference/guide.md"
    assert result["content"] == "GUIDE_CONTENT"


def test_load_ambiguous_basename_returns_candidates(library: SkillLibrary) -> None:
    result = library.load("alpha", "tips.md")
    assert result["ok"] is False
    assert result["candidates"] == ["notes/tips.md", "references/tips.md"]


def test_load_missing_file_raises_tool_error(library: SkillLibrary) -> None:
    with pytest.raises(ToolError):
        library.load("alpha", "references/nope.md")


def test_load_refuses_paths_outside_skill_dir(library: SkillLibrary) -> None:
    # 绝对路径指向 Skill 目录之外：不允许读取
    with pytest.raises(ToolError):
        library.load("alpha", str(library.root / "outside.txt"))
    # 相对路径穿越（..）同样越界
    with pytest.raises(ToolError):
        library.load("alpha", "../../outside.txt")


def test_load_skill_directory_is_rejected(library: SkillLibrary) -> None:
    with pytest.raises(ToolError):
        library.load("alpha", "references")


def test_load_unknown_skill_lists_available(library: SkillLibrary) -> None:
    result = library.load("gamma")
    assert result["ok"] is False
    assert result["available"] == ["alpha", "beta"]


def test_load_skill_via_registry(library: SkillLibrary, workspace: Path) -> None:
    registry = build_registry(workspace, skills=library)
    outcome = registry.execute("loadSkill", json.dumps({"name": "alpha"}))
    assert outcome.ok is True
    assert "SECRET_BODY_MARKER" in json.loads(outcome.output)["content"]

    bad = registry.execute("loadSkill", json.dumps({"name": "gamma"}))
    assert bad.ok is False


# ---------------------------------------------------------------- 会话集成


def test_session_injects_skills_and_loads_on_demand(project: Path, tmp_path) -> None:
    library = SkillLibrary(project)
    config = AppConfig(base_url="http://x", api_key="k", model_name="m")
    backend = FakeBackend(
        [
            tool_script("call-1", "loadSkill", json.dumps({"name": "beta"})),
            text_chunks("已加载"),
        ]
    )
    registry = build_registry(project, skills=library)
    session = AgentSession(backend, registry, config, skills=library)

    events = list(session.ask("加载 beta 技能"))

    # 第一次请求：System Prompt 只带技能清单，不带正文
    first_system = backend.requests[0].messages[0]
    assert first_system["role"] == "system"
    assert PROMPT_HEADER in first_system["content"]
    assert "BETA_BODY" not in first_system["content"]

    # 第二轮请求：SKILL.md 全文通过工具结果进入上下文
    tool_message = backend.requests[1].messages[-1]
    assert tool_message["role"] == "tool"
    assert "BETA_BODY" in json.loads(tool_message["content"])["content"]

    assert events[-1].text == "已加载"


def test_session_without_skills_keeps_old_behavior(project: Path, tmp_path) -> None:
    config = AppConfig(base_url="http://x", api_key="k", model_name="m")
    backend = FakeBackend([text_chunks("好")])
    registry = build_registry(project)
    session = AgentSession(backend, registry, config)

    list(session.ask("你好"))

    assert PROMPT_HEADER not in backend.requests[0].messages[0]["content"]
    assert "loadSkill" not in registry.names()
