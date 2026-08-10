"""Phase 2 live acceptance smoke test: the three provenance label paths (spec §9).

Runs the real agent loop (real OpenRouter LLM + real Tavily) against three docs
questions and prints the answer with the detected provenance label. Not part of
the pytest suite — run manually:

    uv run python scripts/phase2_live_smoke.py
"""
from __future__ import annotations

import asyncio
import sys
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.db.session import get_sessionmaker
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.lesson_note_repository import LessonNoteRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.skill_repository import SkillRepository
from app.services.agent import AgentService
from app.services.knowledge import KnowledgeBase
from app.services.router import OpenRouterLlmClient, RouterService
from app.services.tools import ToolContext, phase2_tools
from app.services.web_search import WebSearcher

CASES = [
    ("KB provenance", "can I fail for stalling?", "docs", "Rijprocedure B"),
    ("Web fallback", "how much does the practical exam cost?", "docs", "from cbr.nl just now"),
    (
        "General knowledge",
        "what is the default speed limit on a motorway in the Netherlands?",
        "docs",
        "not from the CBR docs",
    ),
]


async def main() -> int:
    settings = get_settings()
    if not settings.llm_api_key:
        print("LLM_API_KEY not set", file=sys.stderr)
        return 1
    client = OpenRouterLlmClient(settings.llm_api_key, settings.llm_base_url)
    router = RouterService(client, settings)
    agent = AgentService(client, settings)
    tools = phase2_tools()

    all_ok = True
    async with get_sessionmaker()() as session:
        ctx = ToolContext(
            sessions=SessionRepository(session),
            skills=SkillRepository(session),
            notes=LessonNoteRepository(session),
            audit=AuditLogRepository(session),
            timezone=ZoneInfo(settings.timezone),
            knowledge=KnowledgeBase(settings.knowledge_dir),
            web=WebSearcher(settings.tavily_api_key),
        )
        for name, message, expected_label, expected_marker in CASES:
            print(f"\n=== {name} ===")
            print(f"Q: {message}")
            routed = await router.classify(message)
            print(f"router label: {routed} (expected {expected_label})")
            reply = await agent.handle(message, routed, tools, ctx)
            print(f"A: {reply}")
            ok = (routed == expected_label) and (expected_marker.lower() in reply.lower())
            found = expected_marker.lower() in reply.lower()
            print(f"provenance marker '{expected_marker}': {'FOUND' if found else 'MISSING'}")
            print(f"result: {'PASS' if ok else 'FAIL'}")
            if not ok:
                all_ok = False

    print(f"\noverall: {'ALL PASS' if all_ok else 'SOME FAILED'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
