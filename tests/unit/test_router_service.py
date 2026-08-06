from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.domain.errors import RouterUnavailableError
from app.services.router import RouterService
from tests.conftest import FakeLlmClient


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


async def test_classify_logs_jsonl(tmp_path: Path) -> None:
    client = FakeLlmClient(chat_responses=['{"label": "smalltalk"}'])
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


async def test_classify_router_api_error_raises(tmp_path: Path) -> None:
    class BoomClient(FakeLlmClient):
        async def chat(
            self, model: str, system: str, user: str, *, json_mode: bool = False
        ) -> str:
            raise RuntimeError("network down")

    with pytest.raises(RouterUnavailableError):
        await RouterService(BoomClient(), _settings(tmp_path)).classify("hi")
