from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.services.router import OpenRouterLlmClient


@dataclass
class _Choices:
    choices: list[object]


class _Completions:
    def __init__(self, completion: object) -> None:
        self._completion = completion

    async def create(self, **kwargs: object) -> object:
        return self._completion


class _Chat:
    def __init__(self, completion: object) -> None:
        self.completions = _Completions(completion)


class _FakeOpenAI:
    def __init__(self, completion: object) -> None:
        self.chat = _Chat(completion)


def _client_with(completion: object) -> OpenRouterLlmClient:
    client = OpenRouterLlmClient(api_key="k", base_url="http://x")
    client._client = _FakeOpenAI(completion)  # type: ignore[attr-defined]
    return client


async def test_chat_returns_empty_when_no_choices() -> None:
    client = _client_with(_Choices(choices=[]))
    result = await client.chat("m", "s", "u", json_mode=True)
    assert result.content == ""
    assert result.usage is None


async def test_chat_with_tools_returns_completion_with_no_choices() -> None:
    # The agent loop must tolerate a completion with no choices (degrades, no crash).
    client = _client_with(_Choices(choices=[]))
    completion = await client.chat_with_tools("m", "s", [], [])
    assert not completion.choices


def test_extract_label_empty() -> None:
    # An empty router response must fall through to the fallback ("other" at the caller).
    from app.services.router import extract_label

    assert extract_label("") == ""
    assert extract_label("   ") == ""


@pytest.mark.parametrize("label", ["lookup", "analytics", "log", "docs", "smalltalk", "other"])
async def test_chat_returns_content(label: str) -> None:
    @dataclass
    class _Msg:
        content: str

    @dataclass
    class _Ch:
        message: _Msg

    @dataclass
    class _C:
        choices: list[_Ch]

    client = _client_with(_C(choices=[_Ch(message=_Msg(content=label))]))
    result = await client.chat("m", "s", "u")
    assert result.content == label
