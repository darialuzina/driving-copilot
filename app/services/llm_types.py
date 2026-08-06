from __future__ import annotations

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


class CompletionLike(Protocol):
    choices: list[ChoiceLike]
