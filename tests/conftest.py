from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from app.services.llm_types import CompletionLike


@dataclass
class FakeFunction:
    name: str
    arguments: str


@dataclass
class FakeToolCall:
    id: str
    function: FakeFunction


@dataclass
class FakeMessage:
    content: str | None
    tool_calls: list[FakeToolCall] | None = None


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeCompletion:
    choices: list[FakeChoice]


def make_completion(
    content: str | None = None, calls: list[dict[str, Any]] | None = None
) -> FakeCompletion:
    tool_calls = None
    if calls:
        tool_calls = [
            FakeToolCall(
                id=c["id"],
                function=FakeFunction(name=c["name"], arguments=c.get("arguments", "{}")),
            )
            for c in calls
        ]
    return FakeCompletion(
        choices=[FakeChoice(message=FakeMessage(content=content, tool_calls=tool_calls))]
    )


class FakeLlmClient:
    """A scriptable stand-in for OpenRouterLlmClient used in tests."""

    def __init__(
        self,
        chat_responses: list[str] | None = None,
        completions: list[FakeCompletion] | None = None,
    ) -> None:
        self.chat_responses = list(chat_responses or [])
        self.completions = list(completions or [])
        self.chat_calls: list[dict[str, Any]] = []
        self.completion_calls: list[dict[str, Any]] = []

    async def chat(
        self, model: str, system: str, user: str, *, json_mode: bool = False
    ) -> str:
        self.chat_calls.append(
            {"model": model, "system": system, "user": user, "json_mode": json_mode}
        )
        if not self.chat_responses:
            raise AssertionError("no canned chat response")
        return self.chat_responses.pop(0)

    async def chat_with_tools(
        self,
        model: str,
        system: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> CompletionLike:
        self.completion_calls.append({"model": model, "messages": messages, "tools": tools})
        if not self.completions:
            raise AssertionError("no canned completion")
        return cast(CompletionLike, self.completions.pop(0))
