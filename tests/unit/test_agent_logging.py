from __future__ import annotations

from pathlib import Path

from structlog.testing import capture_logs

from app.config import Settings
from app.services.agent import AgentService
from app.services.tools import phase1_tools
from tests.conftest import FakeLlmClient, FakeUsage


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        answer_model="answer",
        router_model="router",
        router_log_path=tmp_path / "router.jsonl",
    )


async def test_freeform_logs_llm_call_with_model_latency_tokens(tmp_path: Path) -> None:
    usage = FakeUsage(prompt_tokens=8, completion_tokens=2, total_tokens=10)
    client = FakeLlmClient(chat_responses=["hi there!"], chat_usages=[usage])
    agent = AgentService(client, _settings(tmp_path))
    with capture_logs() as logs:
        reply = await agent.handle("hi", "smalltalk", phase1_tools(), ctx=None)  # type: ignore[arg-type]
    assert reply == "hi there!"
    llm_calls = [e for e in logs if e["event"] == "llm.call"]
    assert len(llm_calls) == 1
    call = llm_calls[0]
    assert call["caller"] == "agent.freeform"
    assert call["model"] == "answer"
    assert call["latency_ms"] >= 0
    assert call["prompt_tokens"] == 8
    assert call["completion_tokens"] == 2
    assert call["total_tokens"] == 10


async def test_freeform_logs_without_usage_when_absent(tmp_path: Path) -> None:
    client = FakeLlmClient(chat_responses=["no can do"])
    agent = AgentService(client, _settings(tmp_path))
    with capture_logs() as logs:
        await agent.handle("what tires?", "other", phase1_tools(), ctx=None)  # type: ignore[arg-type]
    llm_calls = [e for e in logs if e["event"] == "llm.call"]
    assert len(llm_calls) == 1
    assert llm_calls[0]["model"] == "answer"
    assert "prompt_tokens" not in llm_calls[0]
