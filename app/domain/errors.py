from __future__ import annotations


class DomainError(Exception):
    """Base domain error."""


class ToolValidationError(DomainError):
    """A tool was called with invalid parameters. Reported back to the model for retry."""

    def __init__(self, tool: str, reason: str) -> None:
        super().__init__(f"Tool '{tool}' invalid: {reason}")
        self.tool = tool
        self.reason = reason


class RouterUnavailableError(DomainError):
    """The router LLM call failed hard (network/auth). The honest error path."""


class LlmCallError(DomainError):
    """An LLM call failed and no safe fallback exists."""


class ParseError(DomainError):
    """Structured output could not be parsed after retries."""
