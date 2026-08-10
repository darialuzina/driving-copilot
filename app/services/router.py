from __future__ import annotations

import asyncio
import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Protocol, cast
from zoneinfo import ZoneInfo

import structlog
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.domain.errors import RouterUnavailableError
from app.services.llm_types import (
    ChatResult,
    CompletionLike,
    TokenUsage,
    to_token_usage,
    usage_log_kwargs,
)
from app.services.prompts import router_system_prompt

log = structlog.get_logger()

VALID_LABELS = frozenset({"lookup", "analytics", "log", "docs", "smalltalk", "other"})


class RouterDecision(BaseModel):
    label: str


class LlmClient(Protocol):
    async def chat(
        self, model: str, system: str, user: str, *, json_mode: bool = False
    ) -> ChatResult: ...

    async def chat_with_tools(
        self,
        model: str,
        system: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> CompletionLike: ...


class OpenRouterLlmClient:
    """Thin async wrapper over the OpenAI-compatible OpenRouter API."""

    def __init__(self, api_key: str, base_url: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def chat(
        self, model: str, system: str, user: str, *, json_mode: bool = False
    ) -> ChatResult:
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if json_mode:
            completion = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
        else:
            completion = await self._client.chat.completions.create(
                model=model, messages=messages, temperature=0.0
            )
        usage = to_token_usage(getattr(completion, "usage", None))
        # OpenRouter/models occasionally return a completion with no usable choices
        # (reasoning models, transient errors). Degrade to an empty string so the
        # router falls back to the answer model / "other" instead of hard-failing.
        if not completion.choices:
            return ChatResult(content="", usage=usage)
        return ChatResult(content=completion.choices[0].message.content or "", usage=usage)

    async def chat_with_tools(
        self,
        model: str,
        system: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> CompletionLike:
        all_messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system},
            *cast(list[ChatCompletionMessageParam], messages),
        ]
        completion = await self._client.chat.completions.create(
            model=model,
            messages=all_messages,
            tools=cast(list[ChatCompletionToolParam], tools),
            temperature=0.0,
        )
        return cast(CompletionLike, completion)


class RouterService:
    """Classify a user message into one of the six labels via the router model."""

    def __init__(self, client: LlmClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings
        self._log_path = settings.router_log_path
        self._tz = ZoneInfo(settings.timezone)

    def today(self) -> date:
        """Current date in the configured timezone, recomputed per call (never cached
        at process start) so relative-date expressions resolve against the real today.
        """
        return datetime.now(self._tz).date()

    async def classify(self, message: str) -> str:
        started = time.monotonic()
        model, usage, label = await self._classify_once(self._settings.router_model, message)
        if label not in VALID_LABELS:
            # Low-confidence fallback: retry once with the capable answer model.
            model, usage, label = await self._classify_once(self._settings.answer_model, message)
        if label not in VALID_LABELS:
            label = "other"
        elapsed_ms = int((time.monotonic() - started) * 1000)
        await self._log(message, label, elapsed_ms, model, usage)
        return label

    async def _classify_once(
        self, model: str, message: str
    ) -> tuple[str, TokenUsage | None, str]:
        started = time.monotonic()
        try:
            result = await self._client.chat(
                model=model,
                system=router_system_prompt(self.today()),
                user=message,
                json_mode=True,
            )
        except Exception as exc:  # network / auth — honest error path, no invented label.
            raise RouterUnavailableError(f"router LLM call failed: {exc}") from exc
        elapsed_ms = int((time.monotonic() - started) * 1000)
        log.info(
            "llm.call",
            caller="router",
            model=model,
            latency_ms=elapsed_ms,
            **usage_log_kwargs(result.usage),
        )
        return model, result.usage, extract_label(result.content)

    async def _log(
        self,
        message: str,
        label: str,
        elapsed_ms: int,
        model: str,
        usage: TokenUsage | None,
    ) -> None:
        record: dict[str, object] = {
            "label": label,
            "message": message,
            "model": model,
            "latency_ms": elapsed_ms,
            **usage_log_kwargs(usage),
        }
        log.info("router.classified", **record)
        await self._append_jsonl(record)

    async def _append_jsonl(self, record: dict[str, object]) -> None:
        path: Path = self._log_path
        line = json.dumps(record, ensure_ascii=False) + "\n"

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)

        await asyncio.to_thread(_write)


def extract_label(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
            return RouterDecision.model_validate(data).label.strip().lower()
        except (json.JSONDecodeError, ValidationError):
            pass
    return text.lower()
