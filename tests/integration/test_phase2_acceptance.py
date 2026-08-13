from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.lesson_note_repository import LessonNoteRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.skill_repository import SkillRepository
from app.services.agent import AgentService
from app.services.backfill import load_backfill
from app.services.knowledge import KnowledgeBase
from app.services.semantic import SkillStatus
from app.services.tools import (
    GetGapAnalysisTool,
    ToolContext,
    phase2_tools,
)
from app.services.web_search import WebSearcher
from tests.conftest import FakeLlmClient, FakeWebResult, FakeWebSearcher, make_completion

BACKFILL = Path("fixtures/backfill.yaml")
KNOWLEDGE = Path("knowledge")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        answer_model="answer",
        router_model="router",
        router_log_path=tmp_path / "router.jsonl",
    )


def _ctx(
    session: AsyncSession, *, web: object | None = None, exam_date: date | None = None
) -> ToolContext:
    return ToolContext(
        sessions=SessionRepository(session),
        skills=SkillRepository(session),
        notes=LessonNoteRepository(session),
        audit=AuditLogRepository(session),
        timezone=ZoneInfo("Europe/Amsterdam"),
        knowledge=KnowledgeBase(KNOWLEDGE),
        web=cast(WebSearcher, web if web is not None else WebSearcher("")),
        exam_date=exam_date,
    )


def _tool_call(call_id: str, name: str, arguments: dict[str, object]) -> dict[str, object]:
    return {"id": call_id, "name": name, "arguments": json.dumps(arguments)}


def _tool_result_payload(client: FakeLlmClient, turn: int = 1) -> dict[str, object]:
    message = client.completion_calls[turn]["messages"][-1]
    return json.loads(cast(str, message["content"]))


# --- Gap analysis: derived picture must match spec section 11 ---


async def test_gap_analysis_matches_backfill_derived_picture(
    session: AsyncSession, settings: Settings
) -> None:
    await load_backfill(session, BACKFILL)
    ctx = _ctx(session)
    result = await GetGapAnalysisTool().run({}, ctx, idempotency_key=None)

    weak = {s["name"] for s in result["weak"]}
    not_started = {s["name"] for s in result["not_started"]}
    # Spec section 11: weak = roundabouts (2x), speed adaptation (2x),
    # mirror routine, anticipating other road users.
    expected_weak = {
        "roundabouts",
        "speed adaptation",
        "mirror routine",
        "anticipating other road users",
    }
    assert expected_weak <= weak
    # No evidence for parking -> not_started, not weak.
    assert "parallel parking" not in weak
    assert "parallel parking" in not_started


async def test_gap_analysis_weak_ranked_by_exam_weight(
    session: AsyncSession, settings: Settings
) -> None:
    await load_backfill(session, BACKFILL)
    ctx = _ctx(session)
    result = await GetGapAnalysisTool().run({}, ctx, idempotency_key=None)
    # All weak skills are exam-relevant in the backfill; the ordering is stable by id.
    for s in result["weak"]:
        assert s["exam_relevant"] is True
    # The weak list is ordered by the rank key: exam-relevant first, then severity,
    # then id ascending (the stable tie-breaker). All weak here are exam-relevant,
    # so ids must be ascending.
    weak_ids = [s["id"] for s in result["weak"]]
    assert weak_ids == sorted(weak_ids)
    # No scheduled lessons and no solid skills, and no exam date set (backfill has none)
    # -> DRIVE-5: verdict is no_exam_date, on_track is None (never False), and every
    # exam-relevant skill counts as weak-or-missing.
    assert result["pace"]["verdict"] == "no_exam_date"
    assert result["pace"]["on_track"] is None
    assert result["pace"]["weak_or_missing_count"] >= len(result["weak"])


async def test_get_skill_progress_reflects_improvement_with_dates(
    session: AsyncSession, settings: Settings
) -> None:
    await load_backfill(session, BACKFILL)
    ctx = _ctx(session)
    from app.services.tools import GetSkillProgressTool

    result = await GetSkillProgressTool().run({}, ctx, idempotency_key=None)
    by_name = {s["name"]: s for s in result["skills"]}
    # Clutch: ok (2026-07-30) -> good (2026-08-06): two assessments, last not needs_attention,
    # last two not both good -> in_progress (per spec definitions).
    clutch = by_name["gear use & clutch control"]
    assert clutch["status"] == SkillStatus.IN_PROGRESS.value
    assert clutch["last_note_assessment"] == "good"
    assert clutch["last_practiced"] == "2026-08-06"
    # Roundabouts: two needs_attention -> weak.
    assert by_name["roundabouts"]["status"] == SkillStatus.WEAK.value
    # Skills with no notes -> not_started.
    assert by_name["parallel parking"]["status"] == SkillStatus.NOT_STARTED.value


async def test_get_notes_filters_by_skill_and_query(
    session: AsyncSession, settings: Settings
) -> None:
    await load_backfill(session, BACKFILL)
    ctx = _ctx(session)
    from app.services.tools import GetNotesTool

    by_skill = await GetNotesTool().run({"skill": "roundabouts"}, ctx, idempotency_key=None)
    assert by_skill["count"] >= 2
    assert all(n["skill"] == "roundabouts" for n in by_skill["notes"])
    for n in by_skill["notes"]:
        assert n["date"] in {"2026-07-30", "2026-08-06"}

    with_query = await GetNotesTool().run(
        {"skill": "roundabouts", "query": "difficult"}, ctx, idempotency_key=None
    )
    assert with_query["count"] >= 1
    assert all("difficult" in n["note"].lower() for n in with_query["notes"])


async def test_get_notes_unmatched_skill_returns_empty(session: AsyncSession) -> None:
    await load_backfill(session, BACKFILL)
    ctx = _ctx(session)
    from app.services.tools import GetNotesTool

    result = await GetNotesTool().run({"skill": "quantum drifting"}, ctx, idempotency_key=None)
    assert result["count"] == 0
    assert result["unmatched_skill"] == "quantum drifting"


async def test_get_pace_no_exam_date_counts_all_upcoming(
    session: AsyncSession, settings: Settings
) -> None:
    ctx = _ctx(session)
    from app.services.tools import GetPaceTool

    result = await GetPaceTool().run({}, ctx, idempotency_key=None)
    assert result["exam_date"] is None
    # DRIVE-5: with no exam date, verdict is no_exam_date and on_track is None (not False).
    assert result["verdict"] == "no_exam_date"
    assert result["on_track"] is None
    assert result["weak_or_missing_count"] >= 1


# --- Analytics routed through the agent loop (audit #9/#2 fixed) ---


async def test_analytics_label_routes_through_agent_loop_not_pending(
    session: AsyncSession, settings: Settings
) -> None:
    await load_backfill(session, BACKFILL)
    ctx = _ctx(session)
    client = FakeLlmClient(
        completions=[
            make_completion(calls=[_tool_call("c1", "get_gap_analysis", {})]),
            make_completion(
                content=(
                    "Your weak areas are roundabouts and speed adaptation "
                    "(both needs_attention on 2026-08-06)."
                )
            ),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle("what are my weak areas?", "analytics", phase2_tools(), ctx)
    assert "roundabouts" in reply.lower()
    payload = _tool_result_payload(client)
    assert payload["tool"] == "get_gap_analysis"
    weak = {s["name"] for s in cast(list[dict[str, object]], payload["weak"])}
    assert "roundabouts" in weak


# --- Docs: KB provenance (Rijprocedure section citation) ---


async def test_docs_kb_answer_cites_rijprocedure_section(
    session: AsyncSession, settings: Settings
) -> None:
    ctx = _ctx(session)
    client = FakeLlmClient(
        completions=[
            make_completion(
                calls=[_tool_call("c1", "cbr_search", {"query": "stalling fail exam"})]
            ),
            make_completion(
                content=(
                    "Rijprocedure B, §Toepassing Hoofdstuk 1: bediening koppeling "
                    "is not essential on its own, so a single stall is not "
                    "automatically a fail, but repeated stalling or stalling that "
                    "affects safety can be."
                )
            ),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle("can I fail for stalling?", "docs", phase2_tools(), ctx)
    assert "Rijprocedure B" in reply


async def test_docs_get_cbr_info_returns_seeded_topic(
    session: AsyncSession, settings: Settings
) -> None:
    ctx = _ctx(session)
    client = FakeLlmClient(
        completions=[
            make_completion(
                calls=[_tool_call("c1", "get_cbr_info", {"topic": "bijzondere_verrichtingen"})]
            ),
            make_completion(
                content=(
                    "Rijprocedure B, §3.7: the examiner picks about two "
                    "bijzondere verrichtingen, e.g. fileparkeren and hellingproef."
                )
            ),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle(
        "what do they check on bijzondere verrichtingen?", "docs", phase2_tools(), ctx
    )
    payload = _tool_result_payload(client)
    assert payload["tool"] == "get_cbr_info"
    assert payload["source_type"] == "kb"
    assert "§3.7" in reply


# --- Docs: KB-miss -> live web fallback with provenance label ---


async def test_docs_kb_miss_uses_live_fallback_with_label(
    session: AsyncSession, settings: Settings
) -> None:
    web = FakeWebSearcher(
        results=[
            FakeWebResult(
                title="Tarieven CBR",
                url="https://www.cbr.nl/nl/tarieven",
                content="Het praktijkexamen personenauto kost EUR 380.",
            )
        ]
    )
    ctx = _ctx(session, web=web)
    client = FakeLlmClient(
        completions=[
            # First turn: cbr_search returns nothing for a KB-miss (fees/cost/price
            # are not in the knowledge base).
            make_completion(calls=[_tool_call("c1", "cbr_search", {"query": "fees cost price"})]),
            # Second turn: model falls back to the live web tool.
            make_completion(
                calls=[_tool_call("c2", "web_search_cbr", {"query": "praktijkexamen kosten"})]
            ),
            # Third turn: model answers with the live-fallback provenance prefix.
            make_completion(
                content=("from cbr.nl just now: the practical exam (personenauto) costs EUR 380.")
            ),
            # Possible guardrail retry (keep the same honest answer).
            make_completion(
                content=("from cbr.nl just now: the practical exam (personenauto) costs EUR 380.")
            ),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle("how much does the exam cost?", "docs", phase2_tools(), ctx)
    assert "from cbr.nl just now" in reply
    # The reply must derive from the fake web result, not be invented.
    assert "380" in reply
    assert web.calls == ["praktijkexamen kosten"]
    # The cbr_search hit returned nothing (KB miss).
    first_payload = _tool_result_payload(client, turn=1)
    assert first_payload["tool"] == "cbr_search"
    assert first_payload["count"] == 0
    web_payload = _tool_result_payload(client, turn=2)
    assert web_payload["tool"] == "web_search_cbr"
    assert web_payload["source_type"] == "web"


# --- Docs: general-knowledge provenance when no source has the answer ---


async def test_docs_general_knowledge_prefix_for_traffic_law(
    session: AsyncSession, settings: Settings
) -> None:
    web = FakeWebSearcher(results=[])  # live also returns nothing
    ctx = _ctx(session, web=web)
    client = FakeLlmClient(
        completions=[
            make_completion(
                calls=[_tool_call("c1", "cbr_search", {"query": "motorway national default limit"})]
            ),
            make_completion(
                calls=[_tool_call("c2", "web_search_cbr", {"query": "maximumsnelheid snelweg"})]
            ),
            make_completion(
                content=(
                    "not from the CBR docs — general knowledge, verify in your "
                    "theory book: the default motorway limit in the Netherlands is "
                    "120 km/h, unless signs say otherwise."
                )
            ),
            # Guardrail retry: the honest general-knowledge answer stays the same.
            make_completion(
                content=(
                    "not from the CBR docs — general knowledge, verify in your "
                    "theory book: the default motorway limit in the Netherlands is "
                    "120 km/h, unless signs say otherwise."
                )
            ),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle(
        "what is the speed limit on the highway?", "docs", phase2_tools(), ctx
    )
    assert "not from the CBR docs" in reply
    assert "general knowledge" in reply


# --- Docs flow gets no write tools (audit #9/#2 path safety) ---


async def test_docs_flow_exposes_no_write_tool_to_model(
    session: AsyncSession, settings: Settings
) -> None:
    ctx = _ctx(session)
    client = FakeLlmClient(
        completions=[
            make_completion(calls=[_tool_call("c1", "cbr_search", {"query": "exam structure"})]),
            make_completion(content="Rijprocedure B, §Toepassing covers the exam parts."),
        ]
    )
    agent = AgentService(client, settings)
    await agent.handle("what do they check in the exam?", "docs", phase2_tools(), ctx)
    tool_schemas = client.completion_calls[0]["tools"]
    names: set[str] = set()
    for s in cast(list[dict[str, object]], tool_schemas):
        fn = cast(dict[str, object], s["function"])
        names.add(cast(str, fn["name"]))
    assert "log_lesson" not in names
    assert names == {"get_cbr_info", "get_toc", "get_section", "cbr_search", "web_search_cbr"}


# --- Out-of-scope still refuses honestly (unchanged Phase 1 behaviour) ---


async def test_other_label_refuses_and_lists_capabilities(
    session: AsyncSession, settings: Settings
) -> None:
    ctx = _ctx(session)
    client = FakeLlmClient(
        chat_responses=[
            "I can't help with buying a car — I track your lessons, "
            "progress and CBR exam knowledge."
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle("what tires should I buy?", "other", phase2_tools(), ctx)
    assert "can't" in reply.lower() or "cannot" in reply.lower()


# --- Web fallback unavailable -> honest error, no invented content ---


async def test_web_search_unavailable_returns_honest_error_to_model(
    session: AsyncSession, settings: Settings
) -> None:
    ctx = _ctx(session, web=WebSearcher(""))  # disabled
    client = FakeLlmClient(
        completions=[
            make_completion(calls=[_tool_call("c1", "cbr_search", {"query": "exam fees"})]),
            make_completion(calls=[_tool_call("c2", "web_search_cbr", {"query": "kosten"})]),
            make_completion(
                content=(
                    "I couldn't find exam fees in the CBR knowledge base and "
                    "the live search is unavailable right now."
                )
            ),
            # Guardrail retry: provenance rule #5 is enforced on every docs answer, so
            # this marker-less honest no-result answer is retried once then degraded.
            make_completion(
                content=(
                    "I couldn't find exam fees in the CBR knowledge base and "
                    "the live search is unavailable right now."
                )
            ),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle("how much is the exam?", "docs", phase2_tools(), ctx)
    assert "unavailable" in reply.lower()
    assert reply.startswith("\u26a0\ufe0f")
    web_payload = _tool_result_payload(client, turn=2)
    assert "error" in web_payload


# --- Stale flag: a solid skill not practised in 21+ days (review 5.2) ---


async def test_get_skill_progress_flags_stale_solid_skill(
    session: AsyncSession, settings: Settings
) -> None:
    # Build a solid skill (last two assessments good) older than 21 days, in-transaction.
    skills_repo = SkillRepository(session)
    sessions_repo = SessionRepository(session)
    notes_repo = LessonNoteRepository(session)
    all_skills = await skills_repo.all()
    target = next(s for s in all_skills if s.name == "parallel parking")
    s1 = await sessions_repo.create(date=date(2026, 6, 19), status="completed", source="manual")
    await notes_repo.create(
        session_id=s1.id, skill_id=target.id, note="clean parking", assessment="good"
    )
    s2 = await sessions_repo.create(date=date(2026, 7, 6), status="completed", source="manual")
    await notes_repo.create(
        session_id=s2.id, skill_id=target.id, note="still clean", assessment="good"
    )
    ctx = _ctx(session)
    from app.services.tools import GetSkillProgressTool

    result = await GetSkillProgressTool().run({}, ctx, idempotency_key=None)
    by_name = {s["name"]: s for s in result["skills"]}
    entry = by_name["parallel parking"]
    assert entry["status"] == SkillStatus.SOLID.value
    assert entry["last_practiced"] == "2026-07-06"
    assert entry["stale"] is True


# --- Guardrail degrades fabricated dates on the analytics path (review 3.2) ---


async def test_analytics_guardrail_degrades_fabricated_date(
    session: AsyncSession, settings: Settings
) -> None:
    await load_backfill(session, BACKFILL)
    ctx = _ctx(session)
    client = FakeLlmClient(
        completions=[
            make_completion(calls=[_tool_call("c1", "get_gap_analysis", {})]),
            # First answer invents a date that does not appear in the tool results.
            make_completion(content="Your weakest area is roundabouts, last seen 2026-12-31."),
            # Retry still invents it -> visibly degraded.
            make_completion(content="Your weakest area is roundabouts, last seen 2026-12-31."),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle("what is my weakest area?", "analytics", phase2_tools(), ctx)
    assert reply.startswith("\u26a0\ufe0f")
    assert "2026-12-31" in reply


# --- Provenance rule #5 enforced on the docs path (review 3.1) ---


async def test_docs_answer_without_provenance_marker_is_degraded(
    session: AsyncSession, settings: Settings
) -> None:
    ctx = _ctx(session)
    client = FakeLlmClient(
        completions=[
            make_completion(calls=[_tool_call("c1", "cbr_search", {"query": "exam structure"})]),
            # First answer: a knowledge claim with no provenance marker.
            make_completion(content="The exam has several parts and checks various skills."),
            # Retry: still no marker -> visibly degraded.
            make_completion(content="The exam has several parts and checks various skills."),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle("what is the exam?", "docs", phase2_tools(), ctx)
    assert reply.startswith("\u26a0\ufe0f")
    # The three markers must all be absent from the degraded reply.
    assert "Rijprocedure B, §" not in reply
    assert "from cbr.nl just now" not in reply
    assert "not from the CBR docs" not in reply


async def test_docs_kb_citation_passes_provenance_guardrail(
    session: AsyncSession, settings: Settings
) -> None:
    ctx = _ctx(session)
    client = FakeLlmClient(
        completions=[
            make_completion(calls=[_tool_call("c1", "cbr_search", {"query": "stalling fail"})]),
            make_completion(
                content="Rijprocedure B, §Toepassing: a single stall is not an automatic fail."
            ),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle("can I fail for stalling?", "docs", phase2_tools(), ctx)
    assert not reply.startswith("\u26a0\ufe0f")
    assert "Rijprocedure B, §" in reply


async def test_docs_live_marker_passes_provenance_guardrail(
    session: AsyncSession, settings: Settings
) -> None:
    web = FakeWebSearcher(
        results=[FakeWebResult("Tarieven", "https://www.cbr.nl/tarieven", "Exam costs EUR 380.")]
    )
    ctx = _ctx(session, web=web)
    client = FakeLlmClient(
        completions=[
            make_completion(calls=[_tool_call("c1", "cbr_search", {"query": "fees"})]),
            make_completion(calls=[_tool_call("c2", "web_search_cbr", {"query": "kosten"})]),
            make_completion(content="from cbr.nl just now: the exam costs EUR 380."),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle("how much is the exam?", "docs", phase2_tools(), ctx)
    assert not reply.startswith("\u26a0\ufe0f")
    assert "from cbr.nl just now" in reply


async def test_docs_general_knowledge_marker_passes_provenance_guardrail(
    session: AsyncSession, settings: Settings
) -> None:
    web = FakeWebSearcher(results=[])
    ctx = _ctx(session, web=web)
    client = FakeLlmClient(
        completions=[
            make_completion(calls=[_tool_call("c1", "cbr_search", {"query": "motorway limit"})]),
            make_completion(calls=[_tool_call("c2", "web_search_cbr", {"query": "snelweg"})]),
            make_completion(
                content=(
                    "not from the CBR docs — general knowledge, verify in your "
                    "theory book: motorway limits are shown on blue signs."
                )
            ),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle("what is the motorway limit?", "docs", phase2_tools(), ctx)
    assert not reply.startswith("\u26a0\ufe0f")
    assert "not from the CBR docs" in reply


# --- DRIVE-7: language enforcement (REPLY IN directive + guardrail) ---


async def test_english_question_answered_in_english_over_russian_drift(
    session: AsyncSession, settings: Settings
) -> None:
    # English question; the model's first answer drifts into Russian (the bug).
    # The guardrail retries once; the retry answers in English and passes.
    await load_backfill(session, BACKFILL)
    ctx = _ctx(session)
    client = FakeLlmClient(
        completions=[
            make_completion(calls=[_tool_call("c1", "get_gap_analysis", {})]),
            # First answer drifted into Russian despite the English directive.
            make_completion(
                content=(
                    "Ваши слабые места — rotondes и speed adaptation "
                    "(оба needs_attention на 2026-08-06)."
                )
            ),
            # Corrective retry: now answers in English.
            make_completion(
                content=(
                    "Your weak areas are roundabouts and speed adaptation "
                    "(both needs_attention on 2026-08-06)."
                )
            ),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle("what are my weak areas?", "analytics", phase2_tools(), ctx)
    assert not reply.startswith("\u26a0\ufe0f")
    assert "roundabouts" in reply.lower()
    # The reply is English (no significant Cyrillic drift).
    from app.services.agent import answer_language_ok

    assert answer_language_ok(reply, "English") is True


async def test_english_question_persistent_russian_drift_degrades(
    session: AsyncSession, settings: Settings
) -> None:
    await load_backfill(session, BACKFILL)
    ctx = _ctx(session)
    client = FakeLlmClient(
        completions=[
            make_completion(calls=[_tool_call("c1", "get_gap_analysis", {})]),
            # Both answers drift into Russian -> visibly degraded with ⚠️.
            make_completion(content="Ваши слабые места — rotondes и speed adaptation."),
            make_completion(content="Ваши слабые места — rotondes и speed adaptation."),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle("what are my weak areas?", "analytics", phase2_tools(), ctx)
    assert reply.startswith("\u26a0\ufe0f")


async def test_russian_question_answered_in_russian(
    session: AsyncSession, settings: Settings
) -> None:
    await load_backfill(session, BACKFILL)
    ctx = _ctx(session)
    client = FakeLlmClient(
        completions=[
            make_completion(calls=[_tool_call("c1", "get_gap_analysis", {})]),
            make_completion(
                content=(
                    "Ваши слабые места — rotondes и speed adaptation "
                    "(оба needs_attention на 2026-08-06)."
                )
            ),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle("какие у меня слабые места?", "analytics", phase2_tools(), ctx)
    assert not reply.startswith("\u26a0\ufe0f")
    from app.services.agent import answer_language_ok

    assert answer_language_ok(reply, "Russian") is True


async def test_reply_in_directive_injected_into_answer_prompt(
    session: AsyncSession, settings: Settings
) -> None:
    # The freeform path records the system prompt in chat_calls; assert the
    # code-detected REPLY IN directive is present and matches the message language.
    ctx = _ctx(session)
    client = FakeLlmClient(chat_responses=["Привет!"])
    agent = AgentService(client, settings)
    await agent.handle("привет", "smalltalk", phase2_tools(), ctx)
    system_prompt = cast(str, client.chat_calls[0]["system"])
    assert "REPLY IN: Russian." in system_prompt

    client_en = FakeLlmClient(chat_responses=["Hi!"])
    agent_en = AgentService(client_en, settings)
    await agent_en.handle("hi", "smalltalk", phase2_tools(), ctx)
    system_prompt_en = cast(str, client_en.chat_calls[0]["system"])
    assert "REPLY IN: English." in system_prompt_en
