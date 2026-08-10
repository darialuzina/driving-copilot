from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, TypedDict, cast

import structlog

from app.config import Settings
from app.domain.errors import LlmCallError, ToolValidationError, WebSearchError
from app.services.llm_types import (
    CompletionLike,
    MessageLike,
    to_token_usage,
    usage_log_kwargs,
)
from app.services.prompts import (
    ANSWER_SYSTEM_PROMPT,
    REFUSAL_SYSTEM_PROMPT,
)
from app.services.router import LlmClient
from app.services.tools import Tool, ToolContext, dump_tool_result, tool_by_name, tools_for_label

log = structlog.get_logger()

_MAX_TOOL_TURNS = 5
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
# Integers not already part of an ISO date.
_NUMBER_RE = re.compile(r"(?<!\d)(\d{1,4})(?!\d)")
# A number presented as an id reference: "note 5", "session #3", "id 12".
_ID_REF_RE = re.compile(
    r"\b(?:note|notes|session|sessions|skill|skills|id)\s*#?\s*(\d{1,9})\b",
    re.IGNORECASE,
)
_ID_KEYS = ("id", "note_id", "session_id", "skill_id", "general_note_id")
_ID_LIST_KEYS = ("note_ids",)

# Recursive JSON value type — keeps basedpyright strict happy while walking tool results.
type JsonType = dict[str, JsonType] | list[JsonType] | str | int | float | bool | None


class _ToolFunctionDict(TypedDict):
    name: str
    arguments: str


class _ToolCallDict(TypedDict):
    id: str
    function: _ToolFunctionDict


class AgentService:
    """Runs the answer-model tool-calling loop and the guardrail check."""

    def __init__(self, client: LlmClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def handle(self, message: str, label: str, tools: list[Tool], ctx: ToolContext) -> str:
        if label in ("smalltalk", "other"):
            return await self._freeform(message, refusal=(label == "other"))
        # log + lookup + analytics + docs -> typed tool-calling agent loop.
        # The router's coarse job is path safety: docs get no write tools and no DB
        # read tools (only the docs stack). See tools_for_label.
        subset = tools_for_label(label, tools)
        return await self._agent_loop(message, subset, ctx)

    async def _freeform(self, message: str, *, refusal: bool) -> str:
        system = REFUSAL_SYSTEM_PROMPT if refusal else ANSWER_SYSTEM_PROMPT
        started = time.monotonic()
        try:
            result = await self._client.chat(
                model=self._settings.answer_model, system=system, user=message
            )
        except Exception as exc:
            raise LlmCallError(f"answer LLM call failed: {exc}") from exc
        elapsed_ms = int((time.monotonic() - started) * 1000)
        log.info(
            "llm.call",
            caller="agent.freeform",
            model=self._settings.answer_model,
            latency_ms=elapsed_ms,
            **usage_log_kwargs(result.usage),
        )
        return result.content

    async def _agent_loop(self, message: str, tools: list[Tool], ctx: ToolContext) -> str:
        tool_schemas = [t.openai_schema() for t in tools]
        messages: list[dict[str, object]] = [{"role": "user", "content": message}]
        tool_results_json: list[str] = []
        total_tokens = 0
        total_latency_ms = 0

        for _turn in range(_MAX_TOOL_TURNS):
            started = time.monotonic()
            try:
                completion = await self._client.chat_with_tools(
                    model=self._settings.answer_model,
                    system=ANSWER_SYSTEM_PROMPT,
                    messages=messages,
                    tools=tool_schemas,
                )
            except Exception as exc:
                raise LlmCallError(f"answer LLM call failed: {exc}") from exc
            elapsed_ms = int((time.monotonic() - started) * 1000)
            usage = to_token_usage(completion.usage)
            total_tokens += usage.total_tokens if usage else 0
            total_latency_ms += elapsed_ms
            log.info(
                "llm.call",
                caller="agent.loop",
                model=self._settings.answer_model,
                latency_ms=elapsed_ms,
                turn=_turn,
                **usage_log_kwargs(usage),
            )

            # A malformed completion (no choices) degrades to an honest empty answer
            # rather than crashing on choices[0].
            if not completion.choices:
                log.warning("agent.empty_completion", turns=_turn)
                return "I couldn't generate an answer just now — please try rephrasing."

            msg = _assistant_message(completion)
            tool_calls = _tool_calls(msg)

            if not tool_calls:
                answer = _content(msg)
                checked = containment_ok(answer, tool_results_json)
                if not checked and tool_results_json:
                    # One corrective retry, then send visibly degraded.
                    messages.append(_assistant_to_history(msg))
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                "Corrective note: only use dates, counts, and ids that appear "
                                "verbatim in the tool results. Reply again."
                            ),
                        }
                    )
                    retry_usage = await self._retry(messages, tool_schemas)
                    total_tokens += retry_usage[0]
                    total_latency_ms += retry_usage[1]
                    answer = retry_usage[2]
                    if not containment_ok(answer, tool_results_json):
                        answer = f"\u26a0\ufe0f {answer}"
                log.info(
                    "agent.answer",
                    turns=_turn + 1,
                    tools=len(tool_results_json),
                    model=self._settings.answer_model,
                    latency_ms=total_latency_ms,
                    total_tokens=total_tokens,
                )
                return answer

            messages.append(_assistant_to_history(msg))
            for call in tool_calls:
                result = await self._execute(call, tools, ctx)
                dumped = dump_tool_result(result)
                tool_results_json.append(dumped)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": dumped,
                    }
                )
        # Loop exhausted without a final answer.
        return "I worked on this too long without finishing. Try rephrasing?"

    async def _retry(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
    ) -> tuple[int, int, str]:
        """One corrective retry after a guardrail failure. Returns (tokens, latency, answer)."""
        started = time.monotonic()
        try:
            retry_completion = await self._client.chat_with_tools(
                model=self._settings.answer_model,
                system=ANSWER_SYSTEM_PROMPT,
                messages=messages,
                tools=tool_schemas,
            )
        except Exception as exc:
            raise LlmCallError(f"answer LLM call failed: {exc}") from exc
        elapsed_ms = int((time.monotonic() - started) * 1000)
        usage = to_token_usage(retry_completion.usage)
        tokens = usage.total_tokens if usage else 0
        log.info(
            "llm.call",
            caller="agent.retry",
            model=self._settings.answer_model,
            latency_ms=elapsed_ms,
            **usage_log_kwargs(usage),
        )
        answer = _content(_assistant_message(retry_completion))
        return tokens, elapsed_ms, answer

    async def _execute(
        self, call: _ToolCallDict, tools: list[Tool], ctx: ToolContext
    ) -> dict[str, object]:
        name = call["function"]["name"]
        tool = tool_by_name(tools, name)
        if tool is None:
            return {"tool": name, "error": f"unknown tool '{name}'"}
        try:
            arguments = json.loads(call["function"].get("arguments") or "{}")
        except json.JSONDecodeError as exc:
            return {"tool": name, "error": f"invalid arguments JSON: {exc}"}
        idempotency_key = (
            make_write_idempotency_key(name, arguments, ctx.today().isoformat())
            if tool.tier.value == "write_auto"
            else None
        )
        try:
            return await tool.run(arguments, ctx, idempotency_key)
        except ToolValidationError as exc:
            # Structured error back to the model so it can retry with valid params.
            return {"tool": name, "error": exc.reason}
        except WebSearchError as exc:
            # The live fallback failed (config/network). Tell the model honestly; it
            # must not invent cbr.nl content — it should say the live search is
            # unavailable or fall back to the KB / general-knowledge label.
            return {"tool": name, "error": f"web search unavailable: {exc}"}


def _assistant_message(completion: CompletionLike) -> MessageLike:
    return completion.choices[0].message


def _tool_calls(msg: MessageLike) -> list[_ToolCallDict]:
    calls = msg.tool_calls
    if not calls:
        return []
    out: list[_ToolCallDict] = []
    for call in calls:
        out.append(
            {
                "id": call.id,
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
        )
    return out


def _content(msg: MessageLike) -> str:
    return msg.content or ""


def _assistant_to_history(msg: MessageLike) -> dict[str, object]:
    history: dict[str, object] = {"role": "assistant"}
    content = _content(msg)
    if content:
        history["content"] = content
    calls = _tool_calls(msg)
    if calls:
        history["tool_calls"] = [
            {
                "id": c["id"],
                "type": "function",
                "function": c["function"],
            }
            for c in calls
        ]
    return history


def make_write_idempotency_key(
    tool_name: str, arguments: dict[str, Any], today_iso: str
) -> str:
    """Deterministic idempotency key for a write tool call.

    Derived from a stable hash of the call arguments plus the current date so that
    identical retries collide (returning the stored result) while distinct calls —
    different content, or the same content on a different day — do not.
    """
    canonical = json.dumps(
        arguments, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    digest = hashlib.sha256(f"{tool_name}|{canonical}|{today_iso}".encode())
    return f"{tool_name}:{digest.hexdigest()[:16]}"


def containment_ok(answer: str, tool_results_json: list[str]) -> bool:
    """Every date, standalone number, and id reference in the answer must exist in the
    collected tool JSON. Dates/numbers use a substring check against the JSON blob;
    id-like numbers must additionally appear as an actual id value in the tool results.
    """
    if not tool_results_json:
        return True
    blob = " ".join(tool_results_json)
    if any(match not in blob for match in _DATE_RE.findall(answer)):
        return False
    # Skip numbers that are part of a date already checked.
    answer_without_dates = _DATE_RE.sub("", answer)
    if any(match not in blob for match in _NUMBER_RE.findall(answer_without_dates)):
        return False
    # id-like numbers must be real ids in the tool results, not just substrings.
    known_ids = _collect_ids(tool_results_json)
    if known_ids:
        for ref in _ID_REF_RE.findall(answer_without_dates):
            if ref not in known_ids:
                return False
    return True


def _collect_ids(tool_results_json: list[str]) -> set[str]:
    """All id values present in the tool results (single ids + id lists)."""
    ids: set[str] = set()
    for raw in tool_results_json:
        try:
            data = cast(JsonType, json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            continue
        _collect_ids_from(data, ids)
    return ids


def _collect_ids_from(obj: JsonType, ids: set[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in _ID_LIST_KEYS and isinstance(value, list):
                for item in value:
                    if isinstance(item, int):
                        ids.add(str(item))
            elif (key in _ID_KEYS or key.endswith("_id")) and isinstance(value, int):
                ids.add(str(value))
            else:
                _collect_ids_from(value, ids)
    elif isinstance(obj, list):
        for item in obj:
            _collect_ids_from(item, ids)
