from __future__ import annotations

import asyncio

import pytest
from structlog.testing import capture_logs

from app.bot import with_transient_retry
from app.domain.errors import LlmCallError, RouterUnavailableError


async def test_retry_succeeds_after_one_transient_error_and_logs_class() -> None:
    # First call raises a transient LLM error, second returns the value. The
    # helper must retry once, return the value, and log the error class.
    calls = {"n": 0}

    async def factory() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise LlmCallError("transient boom")
        return "ok"

    with capture_logs() as logs:
        result = await with_transient_retry(factory, stage="agent", backoff_seconds=0.0)

    assert result == "ok"
    assert calls["n"] == 2
    retries = [e for e in logs if e["event"] == "bot.transient_retry"]
    assert len(retries) == 1
    assert retries[0]["stage"] == "agent"
    assert retries[0]["error_class"] == "LlmCallError"


async def test_retry_re_raises_when_second_call_also_fails() -> None:
    # Both attempts fail -> the second error propagates (caller shows fallback).
    calls = {"n": 0}

    async def factory() -> str:
        calls["n"] += 1
        raise RouterUnavailableError("still down")

    with capture_logs() as logs, pytest.raises(RouterUnavailableError):
        await with_transient_retry(factory, stage="router", backoff_seconds=0.0)

    assert calls["n"] == 2
    retries = [e for e in logs if e["event"] == "bot.transient_retry"]
    assert len(retries) == 1
    assert retries[0]["error_class"] == "RouterUnavailableError"


async def test_non_transient_error_is_not_retried() -> None:
    # A non-transient DomainError must propagate immediately, no retry.
    from app.domain.errors import ToolValidationError

    calls = {"n": 0}

    async def factory() -> str:
        calls["n"] += 1
        raise ToolValidationError("log_lesson", "bad params")

    with pytest.raises(ToolValidationError):
        await with_transient_retry(factory, stage="agent", backoff_seconds=0.0)
    assert calls["n"] == 1


async def test_no_retry_when_first_call_succeeds() -> None:
    calls = {"n": 0}

    async def factory() -> str:
        calls["n"] += 1
        return "ok"

    with capture_logs() as logs:
        result = await with_transient_retry(factory, stage="router", backoff_seconds=0.0)

    assert result == "ok"
    assert calls["n"] == 1
    assert not [e for e in logs if e["event"] == "bot.transient_retry"]


async def test_backoff_is_applied_between_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    calls = {"n": 0}

    async def factory() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise LlmCallError("transient")
        return "ok"

    await with_transient_retry(factory, stage="agent", backoff_seconds=1.5)
    assert slept == [1.5]
