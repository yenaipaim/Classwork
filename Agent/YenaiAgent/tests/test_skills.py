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
    build_create_skill_tool,
    build_load_skill_tool,
    normalize_skill_name,
    parse_frontmatter,
    resolve_skill_roots,
    split_skill_roots,
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


# ---------------------------------------------------------------- 多个技能根目录


def test_library_scans_multiple_roots_and_dedupes(tmp_path: Path) -> None:
    first = make_project(tmp_path / "one")
    second = tmp_path / "two"
    (second / "gamma").mkdir(parents=True)
    (second / "gamma" / "SKILL.md").write_text(
        "---\nname: gamma\ndescription: Gamma skill.\n---\nbody", encoding="utf-8"
    )
    # 第二个根里放一份同名 alpha：先扫到的第一根生效，这里应被记为重复
    (second / "alpha-copy").mkdir()
    (second / "alpha-copy" / "SKILL.md").write_text(SIMPLE_MD, encoding="utf-8")

    roots = [first / ".agents" / "skills", second]
    library = SkillLibrary(first, roots=roots)

    assert library.roots == [roots[0].resolve(), second.resolve()]
    assert library.skills_dir == roots[0].resolve()
    assert [info.name for info in library.skills] == ["alpha", "beta", "gamma"]
    assert library.get("alpha").directory == (roots[0] / "alpha").resolve()
    duplicates = [item for item in library.skipped if "名称重复" in item["reason"]]
    assert len(duplicates) == 2
    assert "已加载自" in duplicates[-1]["reason"]


def test_library_records_missing_root(tmp_path: Path) -> None:
    missing = tmp_path / "absent"
    library = SkillLibrary(tmp_path, roots=[missing])

    assert library.skills == []
    assert library.skipped == [
        {"directory": str(missing.resolve()), "reason": "技能根目录不存在"}
    ]


def test_split_and_resolve_skill_roots(tmp_path: Path) -> None:
    assert split_skill_roots(" a ; b ,\n c ") == ["a", "b", "c"]
    assert split_skill_roots("") == []

    base = tmp_path / "proj"
    base.mkdir()
    # 空配置 → 与旧版完全一致的默认根
    assert resolve_skill_roots(base) == [base.resolve() / ".agents" / "skills"]

    roots = resolve_skill_roots(
        base, ["shared", "shared;%s" % (base / "abs"), str(base / "abs")]
    )
    assert roots == [base.resolve() / "shared", (base / "abs").resolve()]


def test_create_session_accepts_explicit_skill_roots(tmp_path: Path) -> None:
    from core.factory import create_session

    project = tmp_path / "proj"
    project.mkdir()
    extra = tmp_path / "extra"
    (extra / "delta").mkdir(parents=True)
    (extra / "delta" / "SKILL.md").write_text(
        "---\nname: delta\ndescription: Delta skill.\n---\n", encoding="utf-8"
    )
    config = AppConfig(base_url="http://x", api_key="k", model_name="m")

    session = create_session(
        config,
        workspace_root=project,
        history_dir=tmp_path / "history",
        backend=FakeBackend([text_chunks("好")]),
        project_root=project,
        skill_roots=[str(extra)],
    )

    assert session.skills is not None
    assert [info.name for info in session.skills.skills] == ["delta"]
    assert "loadSkill" in session.registry.names()


# ---------------------------------------------------------------- createSkill 工具


def test_create_skill_registered_after_load_skill(workspace: Path) -> None:
    assert "createSkill" not in build_registry(workspace).names()

    # 空技能库也要能新建第一个技能：loadSkill 不注册，createSkill 照常注册
    empty = SkillLibrary(workspace)
    assert empty.names() == []
    empty_registry = build_registry(workspace, skills=empty)
    assert "createSkill" in empty_registry.names()
    assert "loadSkill" not in empty_registry.names()

    library = SkillLibrary(make_project(workspace))
    names = build_registry(workspace, skills=library).names()
    assert "loadSkill" in names
    assert names.index("createSkill") == names.index("loadSkill") + 1
    assert names.index("createSkill") < names.index("list_tools")


def test_create_skill_tool_schema(library: SkillLibrary) -> None:
    schema = build_create_skill_tool(library).schema()
    function = schema["function"]
    assert function["name"] == "createSkill"
    assert function["parameters"]["required"] == ["name", "skillContext"]
    assert set(function["parameters"]["properties"]) == {"name", "skillContext"}


def test_normalize_skill_name_to_kebab_case() -> None:
    assert normalize_skill_name("PDF Tools") == "pdf-tools"
    assert normalize_skill_name("  Deploy_Helper  ") == "deploy-helper"
    assert normalize_skill_name("a---b") == "a-b"
    assert normalize_skill_name("--x--") == "x"
    assert normalize_skill_name("v1.2.3") == "v123"
    # 纯中文、空白与空串都规范不出来
    assert normalize_skill_name("\u90e8\u7f72\u52a9\u624b") is None
    assert normalize_skill_name("   ") is None
    assert normalize_skill_name("") is None
    assert normalize_skill_name(None) is None
    # 长度截到 64 且不以连字符结尾
    capped = normalize_skill_name("a" * 200)
    assert capped is not None and len(capped) == 64


def test_create_skill_writes_spec_compliant_skill_md(project: Path, library: SkillLibrary) -> None:
    result = library.create(
        "PDF Tools",
        "\u5904\u7406 PDF \u6587\u6863\u7684\u6280\u80fd\u3002\n\n# \u6b65\u9aa4\n\n1. \u8bfb\u53d6\n",
    )

    assert result["ok"] is True
    assert result["skill"] == "pdf-tools"
    assert result["registered"] is True
    assert result["file"] == ".agents/skills/pdf-tools/SKILL.md"

    target = project / ".agents" / "skills" / "pdf-tools" / "SKILL.md"
    text = target.read_text(encoding="utf-8")
    assert text.startswith("---\nname: pdf-tools\ndescription: ")
    assert "\r" not in text and "\ufeff" not in text
    assert text.endswith("\n")
    assert "1. \u8bfb\u53d6" in text  # 正文原样保留
    # 生成的 frontmatter 能被自己的解析器读回
    fields = parse_frontmatter(text)
    assert fields is not None
    assert fields["name"] == "pdf-tools"
    assert fields["description"]

    # 同一会话立即可用：登记进清单，loadSkill 能读到
    assert "pdf-tools" in library.names()
    assert "pdf-tools" in library.prompt_block()
    loaded = library.load("pdf-tools")
    assert loaded["ok"] is True and "1. \u8bfb\u53d6" in loaded["content"]


def test_create_skill_creates_missing_root(tmp_path: Path) -> None:
    library = SkillLibrary(tmp_path)
    assert not (tmp_path / ".agents").exists()

    result = library.create("fresh", "# Fresh\n\nBODY")

    assert result["ok"] is True
    target = tmp_path / ".agents" / "skills" / "fresh" / "SKILL.md"
    assert target.is_file()
    assert "fresh" in library.names()


def test_create_skill_refuses_existing_without_touching_it(project: Path, library: SkillLibrary) -> None:
    original = (project / ".agents" / "skills" / "alpha" / "SKILL.md").read_text(encoding="utf-8")

    result = library.create("alpha", "# \u8986\u76d6")

    assert result["ok"] is False
    assert "\u5df2\u5b58\u5728" in result["error"]
    assert "SKILL.md" in result["existing_files"]
    # 原文件一个字节都没动
    assert (project / ".agents" / "skills" / "alpha" / "SKILL.md").read_text(encoding="utf-8") == original


def test_create_skill_refuses_unregistered_directory(project: Path, library: SkillLibrary) -> None:
    # 目录存在但缺少 SKILL.md（启动时被跳过）：同样不覆盖
    result = library.create("no-md", "# whatever")

    assert result["ok"] is False
    assert "\u5df2\u5b58\u5728" in result["error"]
    assert not (project / ".agents" / "skills" / "no-md" / "SKILL.md").exists()


def test_create_skill_refuses_name_taken_by_other_root(tmp_path: Path) -> None:
    first = make_project(tmp_path / "one")
    second = tmp_path / "two"
    (second / "gamma").mkdir(parents=True)
    (second / "gamma" / "SKILL.md").write_text(
        "---\nname: gamma\ndescription: Gamma skill.\n---\nbody", encoding="utf-8"
    )
    library = SkillLibrary(first, roots=[first / ".agents" / "skills", second])

    result = library.create("gamma", "# cloned body")

    assert result["ok"] is False
    assert "\u5360\u7528" in result["error"]
    assert not (first / ".agents" / "skills" / "gamma").exists()


def test_create_skill_rejects_unusable_name_and_creates_nothing(project: Path, library: SkillLibrary) -> None:
    before = set(p.name for p in (project / ".agents" / "skills").iterdir())

    result = library.create("\u90e8\u7f72\u52a9\u624b", "# body")

    assert result["ok"] is False
    assert "kebab-case" in result["error"]
    after = set(p.name for p in (project / ".agents" / "skills").iterdir())
    assert before == after


def test_create_skill_requires_body(tmp_path: Path) -> None:
    library = SkillLibrary(tmp_path)

    result = library.create("empty", "   \n\n  ")

    assert result["ok"] is False
    assert "\u6b63\u6587" in result["error"]
    assert not (tmp_path / ".agents" / "skills" / "empty").exists()


def test_create_skill_keeps_model_frontmatter_and_extra_keys(project: Path, library: SkillLibrary) -> None:
    context = (
        "---\n"
        "name: Some Other Name\n"
        "description: |\n"
        "  multi line\n"
        "  description\n"
        "license: MIT\n"
        "metadata:\n"
        "  owner: me\n"
        "---\n\n"
        "# Body\n\nBODY_TEXT\n"
    )
    result = library.create("fancy-skill", context)

    assert result["ok"] is True
    text = (project / ".agents" / "skills" / "fancy-skill" / "SKILL.md").read_text(encoding="utf-8")
    fields = parse_frontmatter(text)
    assert fields is not None
    assert fields["name"] == "fancy-skill"  # 以目录名为准
    assert fields["description"] == "multi line description"
    assert fields["license"] == "MIT"
    assert "metadata:\n  owner: me" in text  # 嵌套字段原样保留
    assert "BODY_TEXT" in text


def test_create_skill_derives_description_from_body(project: Path, library: SkillLibrary) -> None:
    result = library.create("derived", "# \u6784\u5efa\u6d41\u7a0b\n\n\u5148\u88c5\u4f9d\u8d56\u3002\n")

    assert result["ok"] is True
    fields = parse_frontmatter(
        (project / ".agents" / "skills" / "derived" / "SKILL.md").read_text(encoding="utf-8")
    )
    assert fields["description"] == "\u6784\u5efa\u6d41\u7a0b"


def test_create_skill_quotes_description_when_needed(project: Path, library: SkillLibrary) -> None:
    context = "---\nname: x\ndescription: has: colon inside\n---\n\nBODY"
    result = library.create("colon", context)

    assert result["ok"] is True
    text = (project / ".agents" / "skills" / "colon" / "SKILL.md").read_text(encoding="utf-8")
    assert "description: >-" in text
    assert parse_frontmatter(text)["description"] == "has: colon inside"


def test_create_skill_via_registry(library: SkillLibrary, workspace: Path) -> None:
    registry = build_registry(workspace, skills=library)

    created = registry.execute(
        "createSkill",
        json.dumps({"name": "via-registry", "skillContext": "# Via registry\n\nBODY"}),
    )
    assert created.ok is True
    payload = json.loads(created.output)
    assert payload["ok"] is True and payload["skill"] == "via-registry"

    # 建完立刻能加载
    loaded = registry.execute("loadSkill", json.dumps({"name": "via-registry"}))
    assert loaded.ok is True
    assert "BODY" in json.loads(loaded.output)["content"]

    # 同名再建：明确提示，不覆盖
    again = registry.execute(
        "createSkill", json.dumps({"name": "via-registry", "skillContext": "# new"})
    )
    assert again.ok is False
    assert "\u5df2\u5b58\u5728" in again.output

    # 缺参数：参数错误而不是崩溃
    missing = registry.execute("createSkill", json.dumps({"name": "x"}))
    assert missing.ok is False
