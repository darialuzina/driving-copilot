from __future__ import annotations

import json
from typing import cast

import httpx
import pytest

from app.domain.errors import WebSearchError
from app.services.web_search import WebSearcher, serialize_web_results

_TAVILY_URL = "https://api.tavily.com/search"


def _tavily_body(answer: str | None = None, results: list[dict[str, str]] | None = None) -> bytes:
    payload: dict[str, object] = {"results": results or []}
    if answer is not None:
        payload["answer"] = answer
    return json.dumps(payload).encode()


def test_disabled_searcher_raises() -> None:
    searcher = WebSearcher("")
    assert searcher.enabled is False
    with pytest.raises(WebSearchError):
        import asyncio

        asyncio.run(searcher.search("anything"))


def test_search_returns_cbr_scoped_results(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            content=_tavily_body(
                answer="The fee is €380.",
                results=[
                    {
                        "title": "Tarieven",
                        "url": "https://www.cbr.nl/nl/tarieven",
                        "content": "Examenkosten...",
                    },
                ],
            ),
        )

    transport = httpx.MockTransport(handler)
    searcher = WebSearcher("tvly-test")
    # Inject the mock transport into the client used by search.
    import app.services.web_search as ws_mod

    real_asyncclient = ws_mod.AsyncClient

    class _MockAsyncClient(real_asyncclient):  # type: ignore[misc]
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ws_mod, "AsyncClient", _MockAsyncClient)

    import asyncio

    outcome = asyncio.run(searcher.search("praktijkexamen kosten"))
    assert outcome.source_type == "web"
    assert len(outcome.results) == 1
    assert outcome.results[0].url == "https://www.cbr.nl/nl/tarieven"
    # The request was scoped to cbr.nl.
    body = cast(dict[str, object], captured["body"])
    assert cast(list[str], body["include_domains"]) == ["cbr.nl"]


def test_search_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"boom")

    transport = httpx.MockTransport(handler)
    import app.services.web_search as ws_mod

    real_asyncclient = ws_mod.AsyncClient

    class _MockAsyncClient(real_asyncclient):  # type: ignore[misc]
        def __init__(self, *args: object, **kwargs: object) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(ws_mod, "AsyncClient", _MockAsyncClient)
    searcher = WebSearcher("tvly-test")

    import asyncio

    with pytest.raises(WebSearchError):
        asyncio.run(searcher.search("anything"))


def test_serialize_web_results_shape() -> None:
    from app.services.web_search import WebResult, WebSearchOutcome

    outcome = WebSearchOutcome(
        query="fees",
        source_type="web",
        results=[WebResult(title="T", url="https://www.cbr.nl/x", content="y" * 700)],
        answer=None,
    )
    out = serialize_web_results(outcome)
    assert out["tool"] == "web_search_cbr"
    assert out["source_type"] == "web"
    assert out["count"] == 1
    assert out["results"][0]["content"] == "y" * 600
    assert "from cbr.nl just now" in out["note"]
