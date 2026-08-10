from __future__ import annotations

from pathlib import Path

import pytest

from app.services.knowledge import CbrTopic, KnowledgeBase

KNOWLEDGE = Path("knowledge")


@pytest.fixture
def kb() -> KnowledgeBase:
    return KnowledgeBase(KNOWLEDGE)


def test_get_topic_returns_seeded_content_with_source(kb: KnowledgeBase) -> None:
    result = kb.get_topic("assessment_criteria")
    assert result["source_type"] == "kb"
    assert "cbr.nl" in str(result["source_url"])
    assert "AEX" in str(result["content"])
    assert result["topic"] == "assessment_criteria"


def test_get_topic_all_four_topics_present(kb: KnowledgeBase) -> None:
    for topic in CbrTopic:
        result = kb.get_topic(topic.value)
        assert "content" in result
        assert str(result["content"]).strip() != ""
        assert result["source_type"] == "kb"


def test_get_topic_unknown_topic_returns_structured_error(kb: KnowledgeBase) -> None:
    result = kb.get_topic("not_a_real_topic")
    assert "error" in result
    assert "assessment_criteria" in str(result["error"])


def test_search_finds_stalling_assessment_section(kb: KnowledgeBase) -> None:
    matches = kb.search("stalling fail exam")
    assert matches, "expected at least one match for stalling/fail/exam"
    # The assessment-criteria file has the 'Can you fail for stalling?' section.
    headings = " | ".join(m.heading for m in matches)
    assert "stall" in headings.lower() or "fail" in headings.lower()
    assert all(m.source.startswith("https://www.cbr.nl") for m in matches)


def test_search_finds_bijzondere_verrichtingen(kb: KnowledgeBase) -> None:
    matches = kb.search("bijzondere verrichtingen")
    assert matches
    assert any("verrichtingen" in m.heading.lower() for m in matches)


def test_search_empty_query_returns_nothing(kb: KnowledgeBase) -> None:
    assert kb.search("") == []


def test_search_dutch_term_matches(kb: KnowledgeBase) -> None:
    matches = kb.search("koppeling schakelen")
    assert matches
    assert any("koppeling" in m.snippet.lower() or "schakel" in m.heading.lower() for m in matches)


def test_rijprocedure_b_file_has_sectioned_content(kb: KnowledgeBase) -> None:
    matches = kb.search("wegrijden kijkgedrag")
    assert matches
    assert any("Wegrijden" in m.heading for m in matches)


def test_search_results_carry_file_and_source(kb: KnowledgeBase) -> None:
    matches = kb.search("hellingproef")
    if matches:
        for m in matches:
            assert m.file.endswith(".md")
            assert m.source.startswith("https://www.cbr.nl")


def test_get_topic_content_is_consistent_with_search(kb: KnowledgeBase) -> None:
    # The bijzondere_verrichtingen topic should be searchable too.
    topic = kb.get_topic("bijzondere_verrichtingen")
    content = str(topic["content"])
    matches = kb.search("bijzondere verrichtingen")
    assert matches
    assert any(m.file == "cbr-bijzondere-verrichtingen.md" for m in matches)
    assert "fileparkeren" in content.lower() or "parallel" in content.lower()
