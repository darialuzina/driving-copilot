from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class FunctionLike(Protocol):
    name: str
    arguments: str


class ToolCallLike(Protocol):
    id: str
    function: FunctionLike


class MessageLike(Protocol):
    content: str | None
    tool_calls: list[ToolCallLike] | None


class ChoiceLike(Protocol):
    message: MessageLike


class UsageLike(Protocol):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class CompletionLike(Protocol):
    choices: list[ChoiceLike]
    usage: UsageLike | None


@dataclass
class TokenUsage:
    """Normalized token usage logged with every LLM call (ai.md)."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class ChatResult:
    """Return value of a plain chat call: content + usage for logging."""

    content: str
    usage: TokenUsage | None = None


def to_token_usage(usage: UsageLike | None) -> TokenUsage | None:
    if usage is None:
        return None
    return TokenUsage(
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
    )


def usage_log_kwargs(usage: TokenUsage | None) -> dict[str, int]:
    """Flatten token usage into log kwargs; empty when unavailable."""
    if usage is None:
        return {}
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }
