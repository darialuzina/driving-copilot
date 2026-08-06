from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import AuditLogModel, LessonNoteModel, SkillModel
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.lesson_note_repository import LessonNoteRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.skill_repository import SkillRepository
from app.services.agent import AgentService
from app.services.backfill import load_backfill
from app.services.tools import ToolContext, phase1_tools
from tests.conftest import FakeLlmClient, make_completion

BACKFILL = Path("fixtures/backfill.yaml")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        answer_model="answer",
        router_model="router",
        router_log_path=tmp_path / "router.jsonl",
    )


@pytest.fixture
def ctx(session: AsyncSession) -> ToolContext:
    return ToolContext(
        sessions=SessionRepository(session),
        skills=SkillRepository(session),
        notes=LessonNoteRepository(session),
        audit=AuditLogRepository(session),
        timezone=ZoneInfo("Europe/Amsterdam"),
    )


def _tool_call(call_id: str, name: str, arguments: dict[str, object]) -> dict[str, object]:
    return {"id": call_id, "name": name, "arguments": json.dumps(arguments)}


def _tool_result_payload(client: FakeLlmClient) -> dict[str, object]:
    message = client.completion_calls[1]["messages"][-1]
    return json.loads(cast(str, message["content"]))


async def test_acceptance_log_lesson_creates_note_linked_to_parking(
    session: AsyncSession, ctx: ToolContext, settings: Settings
) -> None:
    # "сегодня делали парковку, все ок" -> router label `log` -> log_lesson tool.
    client = FakeLlmClient(
        completions=[
            make_completion(
                calls=[
                    _tool_call(
                        "c1",
                        "log_lesson",
                        {
                            "date": "today",
                            "skills": [
                                {
                                    "skill": "parking",
                                    "assessment": "good",
                                    "note": "did parking, all ok",
                                }
                            ],
                        },
                    )
                ]
            ),
            make_completion(content="Logged ✓ parking (good)."),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle("сегодня делали парковку, все ок", "log", phase1_tools(), ctx)

    assert "parking" in reply.lower()
    notes = (await session.execute(select(LessonNoteModel))).scalars().all()
    assert len(notes) == 1
    assert notes[0].skill_id is not None
    skill = await session.get(SkillModel, notes[0].skill_id)
    assert skill is not None
    assert "parking" in skill.name
    audits = (await session.execute(select(AuditLogModel))).scalars().all()
    assert any(a.action == "log_lesson" for a in audits)


async def test_acceptance_next_lesson_answers_from_db_empty(
    ctx: ToolContext, settings: Settings
) -> None:
    client = FakeLlmClient(
        completions=[
            make_completion(calls=[_tool_call("c1", "get_next_lessons", {})]),
            make_completion(content="You have no upcoming lessons scheduled."),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle("when is my next lesson?", "lookup", phase1_tools(), ctx)
    assert "no upcoming" in reply.lower()
    payload = _tool_result_payload(client)
    assert payload["tool"] == "get_next_lessons"
    assert payload["count"] == 0


async def test_acceptance_what_did_we_do_on_july_30_returns_backfilled_notes(
    session: AsyncSession, ctx: ToolContext, settings: Settings
) -> None:
    await load_backfill(session, BACKFILL)
    client = FakeLlmClient(
        completions=[
            make_completion(calls=[_tool_call("c1", "get_lesson_history", {"limit": 10})]),
            make_completion(
                content=(
                    "On 2026-07-30 you practiced speed adaptation and roundabouts "
                    "(both needs_attention), among others."
                )
            ),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle("what did we do on July 30?", "lookup", phase1_tools(), ctx)
    assert "2026-07-30" in reply
    payload = _tool_result_payload(client)
    sessions = cast(list[dict[str, object]], payload["sessions"])
    july30 = next(s for s in sessions if s["date"] == "2026-07-30")
    assert july30["instructor"] == "Desevio"
    notes = cast(list[dict[str, object]], july30["notes"])
    skill_names = {n["skill"] for n in notes}
    assert "roundabouts" in skill_names
    assert "speed adaptation" in skill_names


async def test_acceptance_refusal_out_of_scope(ctx: ToolContext, settings: Settings) -> None:
    client = FakeLlmClient(
        chat_responses=["I can't help with buying a car — I track your lessons and notes."]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle("what tires should I buy?", "other", phase1_tools(), ctx)
    assert "can't" in reply.lower() or "cannot" in reply.lower()


async def test_agent_degrades_on_empty_completion(ctx: ToolContext, settings: Settings) -> None:
    from tests.conftest import FakeCompletion

    client = FakeLlmClient(completions=[FakeCompletion(choices=[])])
    agent = AgentService(client, settings)
    reply = await agent.handle("hi", "lookup", phase1_tools(), ctx)
    assert "couldn't" in reply.lower()
