from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from app.services.llm_types import ChatResult, CompletionLike, UsageLike, to_token_usage


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
class FakeUsage:
    """Matches app.services.llm_types.UsageLike for test completions."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class FakeCompletion:
    choices: list[FakeChoice]
    usage: UsageLike | None = field(default=None)


def make_completion(
    content: str | None = None,
    calls: list[dict[str, Any]] | None = None,
    usage: UsageLike | None = None,
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
        choices=[FakeChoice(message=FakeMessage(content=content, tool_calls=tool_calls))],
        usage=usage,
    )


class FakeLlmClient:
    """A scriptable stand-in for OpenRouterLlmClient used in tests."""

    def __init__(
        self,
        chat_responses: list[str] | None = None,
        completions: list[FakeCompletion] | None = None,
        chat_usages: list[UsageLike | None] | None = None,
    ) -> None:
        self.chat_responses = list(chat_responses or [])
        self.completions = list(completions or [])
        self.chat_usages = list(chat_usages or [])
        self.chat_calls: list[dict[str, Any]] = []
        self.completion_calls: list[dict[str, Any]] = []

    async def chat(
        self, model: str, system: str, user: str, *, json_mode: bool = False
    ) -> ChatResult:
        self.chat_calls.append(
            {"model": model, "system": system, "user": user, "json_mode": json_mode}
        )
        if not self.chat_responses:
            raise AssertionError("no canned chat response")
        content = self.chat_responses.pop(0)
        usage: UsageLike | None = None
        if self.chat_usages:
            usage = self.chat_usages.pop(0)
        return ChatResult(content=content, usage=to_token_usage(usage))

    async def chat_with_tools(
        self,
        model: str,
        system: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> CompletionLike:
        # Snapshot the messages list at call time: _agent_loop mutates one list in
        # place across turns, so a bare reference would make every completion_calls
        # entry point at the same final list. A shallow copy freezes the state.
        self.completion_calls.append(
            {"model": model, "messages": list(messages), "tools": tools}
        )
        if not self.completions:
            raise AssertionError("no canned completion")
        return cast(CompletionLike, self.completions.pop(0))


@dataclass
class FakeWebResult:
    title: str
    url: str
    content: str


class FakeWebSearcher:
    """Stand-in for app.services.web_search.WebSearcher used in docs tests."""

    def __init__(self, results: list[FakeWebResult] | None = None) -> None:
        self.enabled = True
        self._results = results or []
        self.calls: list[str] = []

    async def search(self, query: str) -> object:
        from app.services.web_search import WebResult, WebSearchOutcome

        self.calls.append(query)
        return WebSearchOutcome(
            query=query,
            results=[WebResult(r.title, r.url, r.content) for r in self._results],
            source_type="web",
            answer=None,
        )
