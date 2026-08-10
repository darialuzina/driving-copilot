from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.domain.errors import RouterUnavailableError
from app.services.llm_types import ChatResult, UsageLike
from app.services.router import RouterService
from tests.conftest import FakeLlmClient, FakeUsage


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        router_model="router",
        answer_model="answer",
        router_log_path=tmp_path / "router.jsonl",
    )


async def test_classify_valid_label(tmp_path: Path) -> None:
    client = FakeLlmClient(chat_responses=['{"label": "lookup"}'])
    service = RouterService(client, _settings(tmp_path))
    assert await service.classify("when is my next lesson?") == "lookup"
    assert client.chat_calls[0]["json_mode"] is True


async def test_classify_fallback_to_answer_model_then_other(tmp_path: Path) -> None:
    # First (router_model) returns garbage, then answer_model also garbage -> "other".
    client = FakeLlmClient(chat_responses=["banana", "still nope"])
    service = RouterService(client, _settings(tmp_path))
    label = await service.classify("what tires should I buy?")
    assert label == "other"
    assert len(client.chat_calls) == 2


async def test_classify_logs_jsonl_with_model_and_tokens(tmp_path: Path) -> None:
    usage: UsageLike = FakeUsage(prompt_tokens=12, completion_tokens=3, total_tokens=15)
    client = FakeLlmClient(chat_responses=['{"label": "smalltalk"}'], chat_usages=[usage])
    log_path = tmp_path / "router.jsonl"
    service = RouterService(
        client, Settings(router_model="r", answer_model="a", router_log_path=log_path)
    )
    await service.classify("hi!")
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["label"] == "smalltalk"
    assert record["message"] == "hi!"
    assert record["model"] == "r"
    assert record["latency_ms"] >= 0
    assert record["prompt_tokens"] == 12
    assert record["completion_tokens"] == 3
    assert record["total_tokens"] == 15


async def test_classify_logs_without_usage_when_absent(tmp_path: Path) -> None:
    client = FakeLlmClient(chat_responses=['{"label": "smalltalk"}'])
    log_path = tmp_path / "router.jsonl"
    service = RouterService(
        client, Settings(router_model="r", answer_model="a", router_log_path=log_path)
    )
    await service.classify("hi!")
    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record["model"] == "r"
    assert "latency_ms" in record
    # Token fields are omitted (not zeroed) when the provider returns no usage.
    assert "prompt_tokens" not in record


async def test_classify_router_api_error_raises(tmp_path: Path) -> None:
    class BoomClient(FakeLlmClient):
        async def chat(
            self, model: str, system: str, user: str, *, json_mode: bool = False
        ) -> ChatResult:
            raise RuntimeError("network down")

    with pytest.raises(RouterUnavailableError):
        await RouterService(BoomClient(), _settings(tmp_path)).classify("hi")


async def test_telemetry_write_failure_does_not_crash_request(tmp_path: Path) -> None:
    # Regression: an unwritable logs dir must produce a warning, never raise.
    # The router jsonl is eval data — losing a line is preferable to dropping
    # the user's message (ai.md "observability failures degrade silently").
    from structlog.testing import capture_logs

    log_path = tmp_path / "readonly" / "router.jsonl"
    # Pre-create the parent dir read-only so the open("a") write fails.
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.chmod(0o500)
    try:
        client = FakeLlmClient(chat_responses=['{"label": "smalltalk"}'])
        service = RouterService(
            client, Settings(router_model="r", answer_model="a", router_log_path=log_path)
        )
        with capture_logs() as logs:
            label = await service.classify("hi!")
        # The message still answered.
        assert label == "smalltalk"
        # A telemetry warning was emitted, not an exception raised.
        warnings = [e for e in logs if e["event"] == "router.telemetry_write_failed"]
        assert len(warnings) == 1
        assert str(log_path) == warnings[0]["path"]
    finally:
        # Restore perms so tmp_path cleanup works.
        log_path.parent.chmod(0o700)
