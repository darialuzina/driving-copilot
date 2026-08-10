from __future__ import annotations

import pytest

from app.services.tools import (
    AddLessonTool,
    CancelLessonTool,
    CbrSearchTool,
    GetCbrInfoTool,
    GetNotesTool,
    GetPaceTool,
    GetSectionTool,
    GetSkillProgressTool,
    GetTocTool,
    LogLessonTool,
    RiskTier,
    Tool,
    WebSearchCbrTool,
    phase2_tools,
    tools_for_label,
)

_READ_TOOL_INSTANCES: list[Tool] = [
    GetSkillProgressTool(),
    GetNotesTool(),
    GetPaceTool(),
    CbrSearchTool(),
    WebSearchCbrTool(),
    GetCbrInfoTool(),
    GetTocTool(),
    GetSectionTool(),
]


def test_tools_for_label_docs_has_no_write_tools() -> None:
    # spec: docs flow has no write tools (and no DB read tools).
    tools = tools_for_label("docs", phase2_tools())
    names = {t.name for t in tools}
    assert names == {"get_cbr_info", "get_toc", "get_section", "cbr_search", "web_search_cbr"}
    assert "log_lesson" not in names
    assert "get_next_lessons" not in names


def test_tools_for_label_lookup_is_read_only() -> None:
    tools = tools_for_label("lookup", phase2_tools())
    names = {t.name for t in tools}
    assert "log_lesson" not in names
    assert "get_next_lessons" in names
    assert "get_lesson_history" in names
    assert "get_notes" in names
    assert "get_cbr_info" not in names


def test_tools_for_label_analytics_includes_gap_analysis() -> None:
    tools = tools_for_label("analytics", phase2_tools())
    names = {t.name for t in tools}
    assert "get_gap_analysis" in names
    assert "get_skill_progress" in names
    assert "get_pace" in names
    assert "log_lesson" not in names


def test_tools_for_label_log_includes_write_and_read() -> None:
    tools = tools_for_label("log", phase2_tools())
    names = {t.name for t in tools}
    assert "log_lesson" in names
    assert "add_lesson" in names
    assert "cancel_lesson" in names
    assert "get_next_lessons" in names
    assert "get_cbr_info" not in names  # docs tools not exposed on the log path


def test_tools_for_label_smalltalk_and_other_give_no_tools() -> None:
    assert tools_for_label("smalltalk", phase2_tools()) == []
    assert tools_for_label("other", phase2_tools()) == []


def test_phase2_registry_has_all_fourteen_tools() -> None:
    names = {t.name for t in phase2_tools()}
    assert names == {
        "get_next_lessons",
        "get_lesson_history",
        "get_notes",
        "get_pace",
        "get_skill_progress",
        "get_gap_analysis",
        "get_cbr_info",
        "get_toc",
        "get_section",
        "cbr_search",
        "web_search_cbr",
        "log_lesson",
        "add_lesson",
        "cancel_lesson",
    }


@pytest.mark.parametrize("tool", _READ_TOOL_INSTANCES)
def test_phase2_read_tools_declare_read_tier(tool: Tool) -> None:
    assert tool.tier is RiskTier.READ


@pytest.mark.parametrize("tool", [AddLessonTool(), CancelLessonTool(), LogLessonTool()])
def test_manual_lesson_write_tools_declare_write_auto_tier(tool: Tool) -> None:
    assert tool.tier is RiskTier.WRITE_AUTO


def test_get_cbr_info_schema_restricts_topic_enum() -> None:
    schema = GetCbrInfoTool().openai_schema()["function"]["parameters"]
    assert "exam_structure" in str(schema)
    assert "bijzondere_verrichtingen" in str(schema)
    assert "self_reflection" in str(schema)
