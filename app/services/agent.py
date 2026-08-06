from __future__ import annotations

import json
import re
import time
from typing import TypedDict

import structlog

from app.config import Settings
from app.domain.errors import LlmCallError, ToolValidationError
from app.services.llm_types import (
    CompletionLike,
    MessageLike,
)
from app.services.prompts import (
    ANSWER_SYSTEM_PROMPT,
    PHASE2_PENDING_MESSAGE,
    REFUSAL_SYSTEM_PROMPT,
)
from app.services.router import LlmClient
from app.services.tools import Tool, ToolContext, dump_tool_result, tool_by_name

log = structlog.get_logger()

_MAX_TOOL_TURNS = 5
_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
# Integers not already part of an ISO date.
_NUMBER_RE = re.compile(r"(?<!\d)(\d{1,4})(?!\d)")


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
        if label in ("analytics", "docs"):
            # Phase 1 skeleton: these capabilities arrive in Phase 2.
            return PHASE2_PENDING_MESSAGE
        if label in ("smalltalk", "other"):
            return await self._freeform(message, refusal=(label == "other"))
        # log + lookup -> tool-calling agent loop.
        return await self._agent_loop(message, tools, ctx)

    async def _freeform(self, message: str, *, refusal: bool) -> str:
        system = REFUSAL_SYSTEM_PROMPT if refusal else ANSWER_SYSTEM_PROMPT
        try:
            return await self._client.chat(
                model=self._settings.answer_model, system=system, user=message
            )
        except Exception as exc:
            raise LlmCallError(f"answer LLM call failed: {exc}") from exc

    async def _agent_loop(self, message: str, tools: list[Tool], ctx: ToolContext) -> str:
        tool_schemas = [t.openai_schema() for t in tools]
        messages: list[dict[str, object]] = [{"role": "user", "content": message}]
        tool_results_json: list[str] = []

        for _turn in range(_MAX_TOOL_TURNS):
            try:
                completion = await self._client.chat_with_tools(
                    model=self._settings.answer_model,
                    system=ANSWER_SYSTEM_PROMPT,
                    messages=messages,
                    tools=tool_schemas,
                )
            except Exception as exc:
                raise LlmCallError(f"answer LLM call failed: {exc}") from exc

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
                                "Corrective note: only use dates and counts that appear "
                                "verbatim in the tool results. Reply again."
                            ),
                        }
                    )
                    try:
                        retry_completion = await self._client.chat_with_tools(
                            model=self._settings.answer_model,
                            system=ANSWER_SYSTEM_PROMPT,
                            messages=messages,
                            tools=tool_schemas,
                        )
                    except Exception as exc:
                        raise LlmCallError(f"answer LLM call failed: {exc}") from exc
                    answer = _content(_assistant_message(retry_completion))
                    if not containment_ok(answer, tool_results_json):
                        answer = f"\u26a0\ufe0f {answer}"
                log.info("agent.answer", turns=_turn, tools=len(tool_results_json))
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
            f"log:{int(time.time() * 1000)}" if tool.tier.value == "write_auto" else None
        )
        try:
            return await tool.run(arguments, ctx, idempotency_key)
        except ToolValidationError as exc:
            # Structured error back to the model so it can retry with valid params.
            return {"tool": name, "error": exc.reason}


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


def containment_ok(answer: str, tool_results_json: list[str]) -> bool:
    """Every date and standalone number in the answer must appear in the tool JSON."""
    if not tool_results_json:
        return True
    blob = " ".join(tool_results_json)
    if any(match not in blob for match in _DATE_RE.findall(answer)):
        return False
    # Skip numbers that are part of a date already checked.
    answer_without_dates = _DATE_RE.sub("", answer)
    return all(match in blob for match in _NUMBER_RE.findall(answer_without_dates))
